from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from openpyxl import load_workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    ExceptionCase,
    ExceptionComment,
    IngestionJob,
    Material,
    Plant,
    PlantMaterialThreshold,
    Shipment,
    ShipmentUpdate,
    StockSnapshot,
    UploadedFile,
)
from app.models.enums import ShipmentState
from app.modules.exceptions.service import create_audit_log
from app.modules.ingestion.schemas import (
    HeaderMappingSuggestion,
    IngestionSummary,
    MappingPreviewOut,
    RowValidationError,
    UploadResult,
)
from app.modules.suppliers.service import find_supplier_by_name
from app.schemas.context import RequestContext

logger = logging.getLogger(__name__)

SUPPORTED_FILE_TYPES = {"shipment", "stock", "threshold"}
UPLOAD_DIR = Path("uploaded_files")

ALIASES = {
    "shipment_id": {"shipmentid", "shipment", "shipmentref", "reference", "shipmentreference"},
    "plant_code": {"plantcode", "plant", "plantid", "plantname"},
    "material_code": {"materialcode", "material", "materialid"},
    "material_name": {"materialname"},
    "supplier_name": {"suppliername", "supplier", "vendor"},
    "quantity_mt": {"quantitymt", "quantity", "qtymt", "mt", "inboundqtytons", "inboundquantitytons"},
    "planned_eta": {"plannedeta", "originaleta", "eta", "dispatchdate", "shipmentdate"},
    "current_eta": {"currenteta", "latesteta", "revisedeta", "expectedarrivaldate", "arrivaldate"},
    "delay_days": {"delaydays", "delay", "delays", "etadelaydays", "etadelay", "delayindays"},
    "current_state": {"currentstate", "state", "status", "shipmentstate", "shipmentstatus"},
    "source_of_truth": {"sourceoftruth", "source", "datasource"},
    "latest_update_at": {"latestupdateat", "lastupdatedat", "updatedat", "lastupdated", "eventtime"},
    "vessel_name": {"vesselname", "vessel", "shipname"},
    "imo_number": {"imonumber", "imo"},
    "mmsi": {"mmsi"},
    "origin_port": {"originport", "origin", "loadport"},
    "destination_port": {"destinationport", "destination", "dischargeport"},
    "eta_confidence": {"etaconfidence", "confidence"},
    "on_hand_mt": {"onhandmt", "onhand", "stockmt", "stock", "currentstocktons", "currentstock"},
    "quality_held_mt": {"qualityheldmt", "qualityheld", "heldmt", "blockedstocktons", "blockedstock", "blockedstocktons"},
    "available_to_consume_mt": {"availabletoconsumemt", "availablemt", "available", "availableunrestrictedtons"},
    "daily_consumption_mt": {"dailyconsumptionmt", "dailyconsumption", "consumptionmt", "dailyconsumptiontons"},
    "snapshot_time": {"snapshottime", "snapshotat", "asof", "asoftime", "lastupdatedat"},
    "in_transit_open_tons": {"intransitopentons"},
    "days_to_line_stop": {"daystolinestop"},
    "risk_status": {"riskstatus"},
    "next_inbound_eta_days": {"nextinboundetadays"},
    "threshold_days": {"thresholddays", "threshold", "criticaldays", "criticalcoverdays"},
    "warning_days": {"warningdays", "warning", "warningcoverdays", "mincoverdays"},
}

REQUIRED_FIELDS = {
    "shipment": {
        "shipment_id",
        "plant_code",
        "material_code",
        "supplier_name",
        "quantity_mt",
        "planned_eta",
        "current_state",
        "latest_update_at",
    },
    "stock": {
        "plant_code",
        "material_code",
        "on_hand_mt",
        "quality_held_mt",
        "available_to_consume_mt",
        "daily_consumption_mt",
        "snapshot_time",
    },
    "threshold": {"plant_code", "material_code", "threshold_days", "warning_days"},
}

HEADER_FIELDS_BY_FILE_TYPE = {
    "shipment": {
        "shipment_id",
        "plant_code",
        "material_code",
        "supplier_name",
        "quantity_mt",
        "planned_eta",
        "current_eta",
        "delay_days",
        "current_state",
        "source_of_truth",
        "latest_update_at",
        "vessel_name",
        "imo_number",
        "mmsi",
        "origin_port",
        "destination_port",
        "eta_confidence",
    },
    "stock": {
        "plant_code",
        "material_code",
        "material_name",
        "on_hand_mt",
        "quality_held_mt",
        "available_to_consume_mt",
        "daily_consumption_mt",
        "snapshot_time",
        "in_transit_open_tons",
        "days_to_line_stop",
        "risk_status",
        "next_inbound_eta_days",
    },
    "threshold": {"plant_code", "material_code", "threshold_days", "warning_days"},
}


@dataclass
class ParsedRow:
    row_number: int
    data: dict[str, str]


@dataclass
class HeaderMatch:
    field: str | None
    confidence: str
    score: float
    alternatives: list[str]


def process_upload(
    db: Session,
    context: RequestContext,
    current_user_id: int | None,
    file_type: str,
    upload: UploadFile,
    mapping_overrides: dict[str, str] | None = None,
) -> UploadResult:
    content = upload.file.read()
    return process_upload_content(
        db=db,
        context=context,
        current_user_id=current_user_id,
        file_type=file_type,
        filename=upload.filename or "upload",
        content=content,
        content_type=upload.content_type,
        mapping_overrides=mapping_overrides,
        source_of_truth="manual_upload",
    )


def process_upload_content(
    db: Session,
    context: RequestContext,
    current_user_id: int | None,
    file_type: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    mapping_overrides: dict[str, str] | None = None,
    source_of_truth: str | None = None,
) -> UploadResult:
    file_type = file_type.lower().strip()
    if file_type not in SUPPORTED_FILE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    checksum = hashlib.sha256(content).hexdigest()
    uploaded_file = UploadedFile(
        tenant_id=context.tenant_id,
        original_filename=filename,
        storage_uri=save_upload(content, filename, checksum),
        content_type=content_type,
        file_size_bytes=len(content),
        checksum_sha256=checksum,
        uploaded_by_user_id=current_user_id,
        status="uploaded",
    )
    db.add(uploaded_file)
    db.flush()
    create_audit_log(
        db,
        context,
        action="ingestion.uploaded",
        entity_type="uploaded_file",
        entity_id=str(uploaded_file.id),
        metadata={
            "file_type": file_type,
            "filename": uploaded_file.original_filename,
            "checksum_sha256": checksum,
        },
    )

    job = IngestionJob(
        tenant_id=context.tenant_id,
        uploaded_file_id=uploaded_file.id,
        source_type=file_type,
        status="running",
        started_at=datetime.now(UTC),
        records_total=0,
        records_succeeded=0,
        records_failed=0,
    )
    db.add(job)
    db.flush()

    try:
        rows = parse_upload(
            file_type,
            filename,
            content,
            mapping_overrides=mapping_overrides,
            source_of_truth=source_of_truth,
        )
        if not rows:
            raise ValueError("No data rows found in uploaded file")

        result = normalize_rows(db, context, file_type, rows)
        result = result.model_copy(
            update={"upload_id": uploaded_file.id, "ingestion_job_id": job.id}
        )
        job.status = "completed" if result.rows_rejected == 0 else "completed_with_errors"
        if result.rows_accepted == 0:
            job.status = "failed"
        job.records_total = result.rows_received
        job.records_succeeded = result.rows_accepted
        job.records_failed = result.rows_rejected
        if result.validation_errors:
            job.error_message = json.dumps(
                [error.model_dump() for error in result.validation_errors]
            )
        uploaded_file.status = "failed" if result.rows_accepted == 0 else "processed"
        create_audit_log(
            db,
            context,
            action="ingestion.processed",
            entity_type="ingestion_job",
            entity_id=str(job.id),
            metadata={
                "file_type": file_type,
                "rows_received": result.rows_received,
                "rows_accepted": result.rows_accepted,
                "rows_rejected": result.rows_rejected,
            },
        )
        job.completed_at = datetime.now(UTC)
        db.commit()

        if result.rows_accepted == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.model_dump())

        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        # Persist failed metadata in a fresh transaction.
        db.add(uploaded_file)
        db.add(job)
        uploaded_file.status = "failed"
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def save_upload(content: bytes, filename: str, checksum: str) -> str:
    UPLOAD_DIR.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    path = UPLOAD_DIR / f"{checksum[:12]}_{safe_name}"
    path.write_bytes(content)
    return str(path)


def preview_header_mapping(
    file_type: str,
    filename: str,
    content: bytes,
) -> MappingPreviewOut:
    file_type = file_type.lower().strip()
    if file_type not in SUPPORTED_FILE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    headers = extract_headers(file_type, filename, content)
    suggestions = [build_header_mapping_suggestion(file_type, header) for header in headers]
    required_fields = sorted(REQUIRED_FIELDS[file_type])
    optional_fields = sorted(field for field in ALIASES if field not in REQUIRED_FIELDS[file_type])
    return MappingPreviewOut(
        file_type=file_type,
        headers=headers,
        required_fields=required_fields,
        optional_fields=optional_fields,
        suggestions=suggestions,
    )


def delete_uploaded_data(db: Session, tenant_id: int) -> dict[str, int]:
    uploaded_files = list(
        db.scalars(select(UploadedFile).where(UploadedFile.tenant_id == tenant_id))
    )
    deleted_counts = {
        "uploaded_files": len(uploaded_files),
        "ingestion_jobs": int(
            db.scalar(
                select(func.count(IngestionJob.id)).where(IngestionJob.tenant_id == tenant_id)
            )
            or 0
        ),
        "shipments": int(
            db.scalar(select(func.count(Shipment.id)).where(Shipment.tenant_id == tenant_id)) or 0
        ),
        "stock_snapshots": int(
            db.scalar(select(func.count(StockSnapshot.id)).where(StockSnapshot.tenant_id == tenant_id))
            or 0
        ),
        "thresholds": int(
            db.scalar(
                select(func.count(PlantMaterialThreshold.id)).where(
                    PlantMaterialThreshold.tenant_id == tenant_id
                )
            )
            or 0
        ),
        "shipment_updates": int(
            db.scalar(
                select(func.count(ShipmentUpdate.id)).where(ShipmentUpdate.tenant_id == tenant_id)
            )
            or 0
        ),
        "exceptions": int(
            db.scalar(select(func.count(ExceptionCase.id)).where(ExceptionCase.tenant_id == tenant_id))
            or 0
        ),
    }

    for uploaded_file in uploaded_files:
        if uploaded_file.storage_uri:
            try:
                Path(uploaded_file.storage_uri).unlink(missing_ok=True)
            except OSError:
                pass

    db.execute(delete(ExceptionComment).where(ExceptionComment.tenant_id == tenant_id))
    db.execute(delete(ExceptionCase).where(ExceptionCase.tenant_id == tenant_id))
    db.execute(delete(ShipmentUpdate).where(ShipmentUpdate.tenant_id == tenant_id))
    db.execute(delete(Shipment).where(Shipment.tenant_id == tenant_id))
    db.execute(delete(StockSnapshot).where(StockSnapshot.tenant_id == tenant_id))
    db.execute(
        delete(PlantMaterialThreshold).where(PlantMaterialThreshold.tenant_id == tenant_id)
    )
    db.execute(delete(IngestionJob).where(IngestionJob.tenant_id == tenant_id))
    db.execute(delete(UploadedFile).where(UploadedFile.tenant_id == tenant_id))
    db.commit()
    return deleted_counts


def parse_upload(
    file_type: str,
    filename: str,
    content: bytes,
    mapping_overrides: dict[str, str] | None = None,
    source_of_truth: str | None = None,
) -> list[ParsedRow]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return parse_csv(
            file_type,
            content,
            mapping_overrides=mapping_overrides,
            source_of_truth=source_of_truth,
        )
    if suffix == ".xlsx":
        return parse_xlsx(
            file_type,
            content,
            mapping_overrides=mapping_overrides,
            source_of_truth=source_of_truth,
        )
    raise ValueError("Only CSV and XLSX uploads are supported")


def extract_headers(file_type: str, filename: str, content: bytes) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        text = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        header_index = detect_header_row(file_type, rows)
        headers = rows[header_index] if rows else []
        if not headers:
            raise ValueError("Missing header row")
        return ["" if value is None else str(value) for value in headers]
    if suffix == ".xlsx":
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            raise ValueError("Missing header row")
        header_index = detect_header_row(file_type, rows)
        return ["" if value is None else str(value) for value in rows[header_index]]
    raise ValueError("Only CSV and XLSX uploads are supported")


def parse_csv(
    file_type: str,
    content: bytes,
    mapping_overrides: dict[str, str] | None = None,
    source_of_truth: str | None = None,
) -> list[ParsedRow]:
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("Missing header row")
    header_index = detect_header_row(file_type, rows)
    headers = ["" if value is None else str(value) for value in rows[header_index]]
    log_missing_required_headers(file_type, headers, header_index)
    data_rows = (dict(zip(headers, row, strict=False)) for row in rows[header_index + 1 :])
    return normalize_records(
        file_type,
        headers,
        data_rows,
        start_row=header_index + 2,
        mapping_overrides=mapping_overrides,
        source_of_truth=source_of_truth,
    )


def parse_xlsx(
    file_type: str,
    content: bytes,
    mapping_overrides: dict[str, str] | None = None,
    source_of_truth: str | None = None,
) -> list[ParsedRow]:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Missing header row")
    header_index = detect_header_row(file_type, rows)
    headers = ["" if value is None else str(value) for value in rows[header_index]]
    log_missing_required_headers(file_type, headers, header_index)
    records = (dict(zip(headers, row, strict=False)) for row in rows[header_index + 1 :])
    return normalize_records(
        file_type,
        headers,
        records,
        start_row=header_index + 2,
        mapping_overrides=mapping_overrides,
        source_of_truth=source_of_truth,
    )


def detect_header_row(file_type: str, rows: list[Iterable[Any]]) -> int:
    best_index = 0
    best_score = -1.0
    for index, row in enumerate(rows[:10]):
        headers = ["" if value is None else str(value) for value in row]
        score = header_row_score(file_type, headers)
        if score > best_score:
            best_score = score
            best_index = index
    if best_score <= 0:
        return 0
    return best_index


def log_missing_required_headers(file_type: str, headers: Iterable[str], header_index: int) -> None:
    matched_fields = {
        match.field
        for header in headers
        if (match := best_header_match(str(header), required_fields=REQUIRED_FIELDS[file_type])).field
    }
    missing = sorted(REQUIRED_FIELDS[file_type] - matched_fields)
    if missing:
        logger.warning(
            "Parser detected header row %s for %s but required columns are missing: %s",
            header_index + 1,
            file_type,
            ", ".join(missing),
        )


def header_row_score(file_type: str, headers: Iterable[str]) -> float:
    required = REQUIRED_FIELDS[file_type]
    matched_fields = {
        match.field
        for header in headers
        if (match := best_header_match(header, required_fields=required)).field
    }
    non_empty_headers = sum(1 for header in headers if str(header).strip())
    return len(matched_fields) * 2 + min(non_empty_headers, len(required)) * 0.1


def normalize_records(
    file_type: str,
    headers: Iterable[str],
    records: Iterable[dict[str, Any]],
    start_row: int,
    mapping_overrides: dict[str, str] | None = None,
    source_of_truth: str | None = None,
) -> list[ParsedRow]:
    overrides = {str(key): str(value) for key, value in (mapping_overrides or {}).items() if value}
    header_map = {
        header: overrides.get(header) or canonical_header(header, file_type=file_type)
        for header in headers
    }
    parsed_rows: list[ParsedRow] = []
    for index, record in enumerate(records, start=start_row):
        normalized = {}
        for raw_header, value in record.items():
            canonical = header_map.get(raw_header)
            if canonical:
                normalized_value = "" if value is None else str(value).strip()
                if canonical in normalized and normalized[canonical]:
                    continue
                normalized[canonical] = normalized_value
        if not any(value for value in normalized.values()):
            continue
        if source_of_truth and not normalized.get("source_of_truth"):
            normalized["source_of_truth"] = source_of_truth
        parsed_rows.append(ParsedRow(row_number=index, data=normalized))
    return parsed_rows


def canonical_header(header: str, file_type: str | None = None) -> str | None:
    required_fields = HEADER_FIELDS_BY_FILE_TYPE.get(file_type) if file_type else None
    return best_header_match(header, required_fields=required_fields).field


def build_header_mapping_suggestion(file_type: str, header: str) -> HeaderMappingSuggestion:
    suggestion = best_header_match(header, required_fields=REQUIRED_FIELDS[file_type])
    return HeaderMappingSuggestion(
        source_header=header,
        suggested_field=suggestion.field,
        confidence=suggestion.confidence,
        alternatives=suggestion.alternatives,
    )


def best_header_match(header: str, required_fields: set[str] | None = None) -> HeaderMatch:
    compact = normalize_header_token(header)
    candidates = (
        {field: aliases for field, aliases in ALIASES.items() if field in required_fields}
        if required_fields is not None
        else ALIASES
    )
    ranked: list[tuple[float, str]] = []
    for canonical, aliases in candidates.items():
        canonical_compact = canonical.replace("_", "")
        if compact == canonical_compact or compact in aliases:
            ranked.append((1.0, canonical))
            continue

        score = similarity_score(compact, canonical, aliases)
        if score > 0:
            ranked.append((score, canonical))

    ranked.sort(key=lambda item: item[0], reverse=True)
    alternatives = [field for _, field in ranked[1:4]]
    if not ranked:
        return HeaderMatch(field=None, confidence="low", score=0.0, alternatives=[])

    best_score, best_field = ranked[0]
    confidence = "low"
    if best_score >= 0.9:
        confidence = "high"
    elif best_score >= 0.6:
        confidence = "medium"

    if best_score < 0.35:
        return HeaderMatch(field=None, confidence="low", score=best_score, alternatives=alternatives)
    return HeaderMatch(
        field=best_field,
        confidence=confidence,
        score=best_score,
        alternatives=alternatives,
    )


def normalize_header_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def similarity_score(compact: str, canonical: str, aliases: set[str]) -> float:
    canonical_compact = canonical.replace("_", "")
    candidates = {canonical_compact, *aliases}
    best = 0.0
    for candidate in candidates:
        if compact in candidate or candidate in compact:
            best = max(best, 0.72)
        compact_tokens = split_header_tokens(compact)
        candidate_tokens = split_header_tokens(candidate)
        overlap = len(compact_tokens & candidate_tokens)
        if overlap:
            token_score = overlap / max(len(candidate_tokens), 1)
            best = max(best, 0.45 + token_score * 0.4)
    return best


def split_header_tokens(value: str) -> set[str]:
    parts = re.findall(r"[a-z]+|\d+", value.lower())
    return {part for part in parts if part}


def normalize_rows(
    db: Session,
    context: RequestContext,
    file_type: str,
    rows: list[ParsedRow],
) -> UploadResult:
    validation_errors: list[RowValidationError] = []
    summary = IngestionSummary()

    for row in rows:
        errors = missing_required_errors(file_type, row.data)
        if errors:
            validation_errors.append(RowValidationError(row_number=row.row_number, errors=errors))
            continue

        try:
            if file_type == "shipment":
                outcome = upsert_shipment(db, context, row.data)
            elif file_type == "stock":
                outcome = upsert_stock_snapshot(db, context, row.data)
            else:
                outcome = upsert_threshold(db, context, row.data)
        except ValueError as exc:
            validation_errors.append(
                RowValidationError(row_number=row.row_number, errors=[str(exc)])
            )
            continue

        setattr(summary, outcome, getattr(summary, outcome) + 1)

    return UploadResult(
        upload_id=0,
        ingestion_job_id=0,
        file_type=file_type,
        rows_received=len(rows),
        rows_accepted=summary.created + summary.updated + summary.unchanged,
        rows_rejected=len(validation_errors),
        validation_errors=validation_errors,
        summary_counts=summary,
    )


def missing_required_errors(file_type: str, data: dict[str, str]) -> list[str]:
    errors = [
        f"Missing required field: {field}"
        for field in sorted(REQUIRED_FIELDS[file_type])
        if not data.get(field)
    ]
    if file_type == "shipment" and not data.get("current_eta") and not data.get("delay_days"):
        errors.append("Missing required field: current_eta or delay_days")
    return errors


def resolve_plant(db: Session, tenant_id: int, value: str) -> Plant:
    normalized_value = normalize_text_token(value)
    plants = list(db.scalars(select(Plant).where(Plant.tenant_id == tenant_id)))
    plant = next(
        (
            item
            for item in plants
            if normalize_text_token(item.code) == normalized_value
            or normalize_text_token(item.name) == normalized_value
        ),
        None,
    )
    if plant is None:
        requested_index = infer_plant_index(value)
        if requested_index is not None:
            plant = next(
                (
                    item
                    for item in plants
                    if infer_plant_index(item.code) == requested_index
                    or infer_plant_index(item.name) == requested_index
                ),
                None,
            )
            if plant is not None and should_adopt_uploaded_plant_name(plant, requested_index, value):
                plant.name = value.strip()
    if plant is None:
        raise ValueError(f"Unknown plant for tenant: {value}")
    return plant


def resolve_material(db: Session, tenant_id: int, value: str) -> Material:
    normalized_value = normalize_text_token(value)
    materials = list(db.scalars(select(Material).where(Material.tenant_id == tenant_id)))
    material = next(
        (
            item
            for item in materials
            if normalize_text_token(item.code) == normalized_value
            or normalize_text_token(item.name) == normalized_value
        ),
        None,
    )
    if material is not None:
        return material

    code = build_material_code(value)
    material = db.scalar(select(Material).where(Material.tenant_id == tenant_id, Material.code == code))
    if material is not None:
        return material

    material = Material(
        tenant_id=tenant_id,
        code=code,
        name=value.strip(),
        category=infer_material_category(value),
        uom="MT",
    )
    db.add(material)
    db.flush()
    return material


def parse_decimal(value: str, field: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Invalid decimal for {field}: {value}") from exc
    if positive and parsed <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return parsed


def parse_datetime(value: str, field: str) -> datetime:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime for {field}: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def resolve_current_eta(data: dict[str, str], planned_eta: datetime) -> datetime:
    if data.get("current_eta"):
        return parse_datetime(data["current_eta"], "current_eta")
    delay_days = parse_decimal(data["delay_days"], "delay_days")
    return planned_eta + timedelta(days=float(delay_days))


def parse_state(value: str) -> ShipmentState:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    state_aliases = {
        "dispatched": ShipmentState.IN_TRANSIT,
        "dispatch": ShipmentState.IN_TRANSIT,
        "intransit": ShipmentState.IN_TRANSIT,
        "in_transit": ShipmentState.IN_TRANSIT,
        "arrived": ShipmentState.AT_PORT,
        "received": ShipmentState.DELIVERED,
        "complete": ShipmentState.DELIVERED,
        "completed": ShipmentState.DELIVERED,
    }
    if normalized in state_aliases:
        return state_aliases[normalized]
    try:
        return ShipmentState(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid shipment state: {value}") from exc


def values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        return normalize_datetime(left) == normalize_datetime(right)
    return left == right


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_text_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def infer_plant_index(value: str) -> int | None:
    normalized = value.strip().lower()
    number_match = re.search(r"([0-9]+)\s*$", normalized)
    if number_match:
        return int(number_match.group(1))

    letter_match = re.search(r"([a-z])\s*$", normalized)
    if letter_match:
        return ord(letter_match.group(1)) - ord("a") + 1

    return None


def build_material_code(value: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().upper()).strip("_")
    return compact[:40] or "MATERIAL"


def infer_material_category(value: str) -> str:
    normalized = value.strip().lower()
    if "coal" in normalized:
        return "coal"
    if "ore" in normalized:
        return "ore"
    if "lime" in normalized or "flux" in normalized:
        return "flux"
    return "raw"


def should_adopt_uploaded_plant_name(plant: Plant, requested_index: int, uploaded_value: str) -> bool:
    normalized_uploaded = uploaded_value.strip()
    if not normalized_uploaded:
        return False
    return plant.name.strip().lower() == f"plant {requested_index}".lower()


def upsert_shipment(db: Session, context: RequestContext, data: dict[str, str]) -> str:
    plant = resolve_plant(db, context.tenant_id, data["plant_code"])
    material = resolve_material(db, context.tenant_id, data["material_code"])
    state = parse_state(data["current_state"])
    planned_eta = parse_datetime(data["planned_eta"], "planned_eta")
    current_eta = resolve_current_eta(data, planned_eta)
    latest_update_at = parse_datetime(data["latest_update_at"], "latest_update_at")
    eta_confidence = (
        parse_decimal(data["eta_confidence"], "eta_confidence")
        if data.get("eta_confidence")
        else None
    )
    supplier = find_supplier_by_name(db, context.tenant_id, data["supplier_name"])

    shipment = db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.shipment_id == data["shipment_id"],
        )
    )
    attrs = {
        "material_id": material.id,
        "plant_id": plant.id,
        "supplier_id": supplier.id if supplier else None,
        "supplier_name": data["supplier_name"],
        "quantity_mt": parse_decimal(data["quantity_mt"], "quantity_mt", positive=True),
        "vessel_name": data.get("vessel_name") or None,
        "imo_number": data.get("imo_number") or None,
        "mmsi": data.get("mmsi") or None,
        "origin_port": data.get("origin_port") or None,
        "destination_port": data.get("destination_port") or None,
        "planned_eta": planned_eta,
        "current_eta": current_eta,
        "eta_confidence": eta_confidence,
        "current_state": state,
        "source_of_truth": data["source_of_truth"],
        "latest_update_at": latest_update_at,
    }

    if shipment is None:
        db.add(Shipment(tenant_id=context.tenant_id, shipment_id=data["shipment_id"], **attrs))
        return "created"

    changed_eta_or_state = (
        not values_equal(shipment.current_eta, current_eta) or shipment.current_state != state
    )
    changed = any(not values_equal(getattr(shipment, key), value) for key, value in attrs.items())
    if not changed:
        return "unchanged"

    for key, value in attrs.items():
        setattr(shipment, key, value)
    if changed_eta_or_state:
        db.add(
            ShipmentUpdate(
                tenant_id=context.tenant_id,
                shipment_id=shipment.id,
                source=data["source_of_truth"],
                event_type="shipment_eta_or_state_changed",
                event_time=latest_update_at,
                payload_json=json.dumps(
                    {"current_eta": current_eta.isoformat(), "current_state": state.value}
                ),
                notes="Created by onboarding upload",
            )
        )
    return "updated"


def upsert_stock_snapshot(db: Session, context: RequestContext, data: dict[str, str]) -> str:
    plant = resolve_plant(db, context.tenant_id, data["plant_code"])
    material = resolve_material(db, context.tenant_id, data["material_code"])
    daily_consumption = parse_decimal(
        data["daily_consumption_mt"],
        "daily_consumption_mt",
        positive=True,
    )
    snapshot_time = parse_datetime(data["snapshot_time"], "snapshot_time")
    attrs = {
        "on_hand_mt": parse_decimal(data["on_hand_mt"], "on_hand_mt"),
        "quality_held_mt": parse_decimal(data["quality_held_mt"], "quality_held_mt"),
        "available_to_consume_mt": parse_decimal(
            data["available_to_consume_mt"],
            "available_to_consume_mt",
        ),
        "daily_consumption_mt": daily_consumption,
    }
    snapshot = db.scalar(
        select(StockSnapshot).where(
            StockSnapshot.tenant_id == context.tenant_id,
            StockSnapshot.plant_id == plant.id,
            StockSnapshot.material_id == material.id,
            StockSnapshot.snapshot_time == snapshot_time,
        )
    )
    if snapshot is None:
        db.add(
            StockSnapshot(
                tenant_id=context.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                snapshot_time=snapshot_time,
                **attrs,
            )
        )
        return "created"

    changed = any(not values_equal(getattr(snapshot, key), value) for key, value in attrs.items())
    if not changed:
        return "unchanged"
    for key, value in attrs.items():
        setattr(snapshot, key, value)
    return "updated"


def upsert_threshold(db: Session, context: RequestContext, data: dict[str, str]) -> str:
    plant = resolve_plant(db, context.tenant_id, data["plant_code"])
    material = resolve_material(db, context.tenant_id, data["material_code"])
    attrs = {
        "threshold_days": parse_decimal(data["threshold_days"], "threshold_days", positive=True),
        "warning_days": parse_decimal(data["warning_days"], "warning_days", positive=True),
    }
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == context.tenant_id,
            PlantMaterialThreshold.plant_id == plant.id,
            PlantMaterialThreshold.material_id == material.id,
        )
    )
    if threshold is None:
        db.add(
            PlantMaterialThreshold(
                tenant_id=context.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                **attrs,
            )
        )
        return "created"

    changed = any(not values_equal(getattr(threshold, key), value) for key, value in attrs.items())
    if not changed:
        return "unchanged"
    for key, value in attrs.items():
        setattr(threshold, key, value)
    return "updated"
