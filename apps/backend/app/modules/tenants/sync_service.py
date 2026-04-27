from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
import asyncio
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExternalDataSource
from app.modules.ingestion.service import process_upload_content
from app.modules.stock.service import calculate_stock_cover_summary
from app.modules.tenants.service import (
    classify_data_freshness,
    ensure_automated_data_sources_enabled,
)
from app.schemas.context import RequestContext
from app.utils.url_transformer import transform_url_to_downloadable

DATASET_TYPE_TO_INGESTION_TYPE = {
    "shipments": "shipment",
    "stock": "stock",
    "thresholds": "threshold",
}


@dataclass
class RemoteFile:
    filename: str
    content: bytes
    content_type: str | None
    platform_detected: str = "unknown"
    transformed_url: str | None = None


def sync_data_source_now(
    db: Session,
    *,
    context: RequestContext,
    current_user_id: int,
    source_id: int,
) -> dict[str, Any]:
    ensure_automated_data_sources_enabled(db, context.tenant_id)
    source = db.scalar(
        select(ExternalDataSource).where(
            ExternalDataSource.id == source_id,
            ExternalDataSource.tenant_id == context.tenant_id,
        )
    )
    if source is None:
        raise ValueError("Saved data source not found")

    return sync_loaded_data_source(
        db,
        context=context,
        current_user_id=current_user_id,
        source=source,
    )


def sync_loaded_data_source(
    db: Session,
    *,
    context: RequestContext,
    current_user_id: int,
    source: ExternalDataSource,
) -> dict[str, Any]:

    source.last_error_message = None
    before_snapshot = snapshot_risk_state(db, context)
    try:
        remote_file = fetch_remote_file(source)
        source.platform_detected = remote_file.platform_detected
        result = process_upload_content(
            db=db,
            context=context,
            current_user_id=current_user_id,
            file_type=DATASET_TYPE_TO_INGESTION_TYPE[source.dataset_type],
            filename=remote_file.filename,
            content=remote_file.content,
            content_type=remote_file.content_type,
            source_of_truth=source.source_type,
        )
        after_snapshot = snapshot_risk_state(db, context)
        signals = compute_change_signals(before_snapshot, after_snapshot)
        source.last_synced_at = datetime.now(UTC)
        source.last_sync_status = (
            "completed_with_errors" if result.rows_rejected > 0 else "succeeded"
        )
        source.last_error_message = None
        source.new_critical_risks_count = signals["new_critical_risks_count"]
        source.resolved_risks_count = signals["resolved_risks_count"]
        source.newly_breached_actions_count = signals["newly_breached_actions_count"]
        db.commit()
        db.refresh(source)
        freshness_status, freshness_age_minutes = classify_data_freshness(
            source.last_synced_at,
            source.sync_frequency_minutes,
        )
        return {
            "source_id": source.id,
            "sync_status": source.last_sync_status,
            "rows_received": result.rows_received,
            "rows_accepted": result.rows_accepted,
            "rows_rejected": result.rows_rejected,
            "validation_summary": result.summary_counts.model_dump(),
            "validation_errors": [error.model_dump() for error in result.validation_errors],
            "last_error": None,
            "last_synced_at": source.last_synced_at,
            **signals,
            "data_freshness_status": freshness_status,
            "data_freshness_age_minutes": freshness_age_minutes,
        }
    except HTTPException as exc:
        sync_error = extract_sync_error(exc)
        return finalize_failed_sync(db, source, sync_error["last_error"], sync_error)
    except Exception as exc:
        return finalize_failed_sync(db, source, str(exc))


def fetch_remote_file(source: ExternalDataSource) -> RemoteFile:
    return fetch_remote_file_for_values(
        source_type=source.source_type,
        source_url=source.source_url,
        dataset_type=source.dataset_type,
        mapping_config_json=source.mapping_config_json,
    )


def fetch_remote_file_for_values(
    *,
    source_type: str,
    source_url: str,
    dataset_type: str,
    mapping_config_json: str | None = None,
) -> RemoteFile:
    transformed_url, platform = run_url_transform(source_url)
    if source_type == "google_sheets":
        return fetch_google_sheet_url(
            transformed_url,
            dataset_type,
            mapping_config_json,
            platform_detected=platform,
            original_url=source_url,
        )
    if source_type == "excel_online":
        return fetch_excel_online_url(
            transformed_url,
            dataset_type,
            platform_detected=platform,
            original_url=source_url,
        )
    raise ValueError("Unsupported external data source type")


def run_url_transform(source_url: str) -> tuple[str, str]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(transform_url_to_downloadable(source_url))
    raise RuntimeError("URL transformation cannot run inside an active event loop")


def fetch_google_sheet(source: ExternalDataSource) -> RemoteFile:
    return fetch_google_sheet_url(
        source.source_url,
        source.dataset_type,
        source.mapping_config_json,
    )


def fetch_google_sheet_url(
    source_url: str,
    dataset_type: str,
    mapping_config_json: str | None = None,
    *,
    platform_detected: str = "google_sheets",
    original_url: str | None = None,
) -> RemoteFile:
    parsed = urlparse(source_url)
    if not (
        "docs.google.com" in parsed.netloc
        and "/spreadsheets/d/" in parsed.path
        and parsed.path.endswith("/export")
    ):
        raise ValueError(
            "Unsupported Google Sheets URL. Use a public or shareable Google Sheets link."
        )
    parts = [part for part in parsed.path.split("/") if part]
    try:
        doc_id = parts[parts.index("d") + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("Could not determine Google Sheets document ID") from exc

    export_url = source_url
    query = parse_qs(parsed.query)
    if query.get("format", [""])[0].lower() != "xlsx":
        query["format"] = ["xlsx"]
    gid = _resolve_google_sheet_gid(original_url or source_url, mapping_config_json)
    if gid:
        query["gid"] = [gid]
    export_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode({key: value[0] for key, value in query.items()}), ""))
    content, content_type = fetch_url_bytes_for_platform(export_url, platform_detected)
    extension = ".csv" if "csv" in (content_type or "").lower() else ".xlsx"
    return RemoteFile(
        filename=f"{dataset_type}_sync{extension}",
        content=content,
        content_type=content_type,
        platform_detected=platform_detected,
        transformed_url=export_url,
    )


def fetch_excel_online_file(source: ExternalDataSource) -> RemoteFile:
    return fetch_excel_online_url(source.source_url, source.dataset_type)


def fetch_excel_online_url(
    source_url: str,
    dataset_type: str,
    *,
    platform_detected: str = "unknown",
    original_url: str | None = None,
) -> RemoteFile:
    parsed = urlparse(source_url)
    path_lower = parsed.path.lower()
    query = parse_qs(parsed.query)
    extension = ""

    if path_lower.endswith(".csv"):
        extension = ".csv"
    elif path_lower.endswith(".xlsx"):
        extension = ".xlsx"
    elif query.get("format", [""])[0].lower() in {"csv", "xlsx"}:
        extension = f".{query['format'][0].lower()}"
    elif query.get("download", [""])[0].lower() in {"1", "true", "yes"}:
        format_hint = query.get("format", [""])[0].lower()
        if format_hint in {"csv", "xlsx"}:
            extension = f".{format_hint}"

    fetch_url = source_url
    if extension not in {".csv", ".xlsx"} and platform_detected not in {"onedrive", "sharepoint", "google_drive", "unknown"}:
        raise ValueError(
            "Unsupported Excel Online link. Use a direct downloadable CSV/XLSX URL or a share link that allows download."
        )

    try:
        content, content_type = fetch_url_bytes_for_platform(fetch_url, platform_detected)
    except ValueError as exc:
        raise ValueError(download_error_message(platform_detected)) from exc
    if extension not in {".csv", ".xlsx"}:
        extension = infer_download_extension(content, content_type)

    if extension not in {".csv", ".xlsx"}:
        raise ValueError(
            "Unsupported Excel Online link. Use a direct downloadable CSV/XLSX URL or a share link that allows download."
        )

    return RemoteFile(
        filename=f"{dataset_type}_sync{extension}",
        content=content,
        content_type=content_type,
        platform_detected=platform_detected,
        transformed_url=fetch_url,
    )


def is_onedrive_share_url(parsed) -> bool:
    host = parsed.netloc.lower()
    return "1drv.ms" in host or "onedrive.live.com" in host


def force_download_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    query = parse_qs(parsed.query)
    query["download"] = ["1"]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode({key: value[0] for key, value in query.items()}),
            parsed.fragment,
        )
    )


def infer_download_extension(content: bytes, content_type: str | None) -> str:
    lowered_type = (content_type or "").lower()
    if content.startswith(b"PK"):
        return ".xlsx"
    if "spreadsheet" in lowered_type or "excel" in lowered_type:
        return ".xlsx"
    if "csv" in lowered_type or "text/plain" in lowered_type:
        return ".csv"
    sample = content[:512].decode("utf-8-sig", errors="ignore")
    if "," in sample and "<html" not in sample.lower():
        return ".csv"
    return ""


ACCEPTED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/csv",
    "application/octet-stream",
    "text/plain",
}


def fetch_url_bytes(url: str, platform: str = "unknown") -> tuple[bytes, str | None]:
    request = Request(url, headers={"User-Agent": "OpsDeck Sync/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read()
            headers: Message = response.headers
            content_type = headers.get_content_type()
            validate_download_response(content, content_type, platform)
            return content, content_type
    except HTTPError as exc:
        raise ValueError(f"Remote source returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError("Could not access remote source URL") from exc


def fetch_url_bytes_for_platform(url: str, platform: str) -> tuple[bytes, str | None]:
    try:
        return fetch_url_bytes(url, platform)
    except TypeError:
        return fetch_url_bytes(url)  # type: ignore[call-arg]


def validate_download_response(content: bytes, content_type: str | None, platform: str) -> None:
    lowered = (content_type or "").lower()
    sample = content[:512].decode("utf-8-sig", errors="ignore").lower()
    if "text/html" in lowered or "<html" in sample:
        if platform in {"google_drive", "google_sheets"}:
            raise ValueError("File is not publicly shared. Enable 'Anyone with link can view' in Google Drive.")
        if platform in {"onedrive", "sharepoint"}:
            raise ValueError("File is not publicly shared. Enable 'Anyone with link can view' before syncing.")
        raise ValueError("Remote source returned an HTML page instead of a downloadable file.")
    if lowered and not any(accepted in lowered for accepted in ACCEPTED_CONTENT_TYPES):
        raise ValueError(f"Unsupported remote file content type: {content_type}")


def download_error_message(platform: str) -> str:
    return (
        f"Could not download file from {platform}. "
        "Please ensure the link has 'Anyone with the link can view' permission enabled "
        "or use a direct downloadable CSV/XLSX URL."
    )


def extract_sync_error(exc: HTTPException) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict):
        return {
            "rows_received": int(detail.get("rows_received", 0)),
            "rows_accepted": int(detail.get("rows_accepted", 0)),
            "rows_rejected": int(detail.get("rows_rejected", 0)),
            "validation_summary": detail.get(
                "summary_counts",
                {"created": 0, "updated": 0, "unchanged": 0},
            ),
            "validation_errors": detail.get("validation_errors", []),
            "last_error": "Remote sync validation failed.",
        }
    return {
        "rows_received": 0,
        "rows_accepted": 0,
        "rows_rejected": 0,
        "validation_summary": {"created": 0, "updated": 0, "unchanged": 0},
        "validation_errors": [],
        "last_error": str(detail),
    }


def finalize_failed_sync(
    db: Session,
    source: ExternalDataSource,
    error_message: str,
    sync_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source.last_synced_at = datetime.now(UTC)
    source.last_sync_status = "failed"
    source.last_error_message = error_message
    db.commit()
    db.refresh(source)
    freshness_status, freshness_age_minutes = classify_data_freshness(
        source.last_synced_at,
        source.sync_frequency_minutes,
    )
    payload = sync_error or {
        "rows_received": 0,
        "rows_accepted": 0,
        "rows_rejected": 0,
        "validation_summary": {"created": 0, "updated": 0, "unchanged": 0},
        "validation_errors": [],
    }
    return {
        "source_id": source.id,
        "sync_status": "failed",
        "rows_received": payload["rows_received"],
        "rows_accepted": payload["rows_accepted"],
        "rows_rejected": payload["rows_rejected"],
        "validation_summary": payload["validation_summary"],
        "validation_errors": payload["validation_errors"],
        "last_error": source.last_error_message,
        "last_synced_at": source.last_synced_at,
        "new_critical_risks_count": source.new_critical_risks_count,
        "resolved_risks_count": source.resolved_risks_count,
        "newly_breached_actions_count": source.newly_breached_actions_count,
        "data_freshness_status": freshness_status,
        "data_freshness_age_minutes": freshness_age_minutes,
    }


def snapshot_risk_state(db: Session, context: RequestContext) -> dict[str, set[tuple[int, int]]]:
    summary = calculate_stock_cover_summary(db, context)
    return {
        "critical": {
            (row.plant_id, row.material_id)
            for row in summary.rows
            if row.calculation.status == "critical"
        },
        "at_risk": {
            (row.plant_id, row.material_id)
            for row in summary.rows
            if row.calculation.status in {"critical", "warning"}
        },
        "breached_actions": {
            (row.plant_id, row.material_id)
            for row in summary.rows
            if row.calculation.action_sla_breach
        },
    }


def compute_change_signals(
    before_snapshot: dict[str, set[tuple[int, int]]],
    after_snapshot: dict[str, set[tuple[int, int]]],
) -> dict[str, int]:
    return {
        "new_critical_risks_count": len(after_snapshot["critical"] - before_snapshot["critical"]),
        "resolved_risks_count": len(before_snapshot["at_risk"] - after_snapshot["at_risk"]),
        "newly_breached_actions_count": len(
            after_snapshot["breached_actions"] - before_snapshot["breached_actions"]
        ),
    }


def _resolve_google_sheet_gid(source_url: str, mapping_config_json: str | None) -> str | None:
    parsed = urlparse(source_url)
    fragment_params = parse_qs(parsed.fragment)
    if fragment_params.get("gid"):
        return fragment_params["gid"][0]
    if not mapping_config_json:
        return None
    try:
        import json

        mapping_config = json.loads(mapping_config_json)
    except Exception:
        return None
    for key in ("sheet_gid", "gid"):
        value = mapping_config.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
