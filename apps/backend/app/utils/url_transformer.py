from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

GOOGLE_ID_RE = re.compile(r"[-\w]{25,}")


def detect_platform(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "docs.google.com" in host and "/spreadsheets/" in path:
        return "google_sheets"
    if "drive.google.com" in host or "docs.google.com" in host:
        return "google_drive"
    if "sharepoint.com" in host:
        return "sharepoint"
    if any(marker in host for marker in ("onedrive.live.com", "1drv.ms", "onedrive.com")):
        return "onedrive"
    return "unknown"


def is_likely_downloadable(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    if path.endswith((".xlsx", ".xls", ".csv")):
        return True
    if query.get("download", [""])[0].lower() in {"1", "true", "yes"}:
        return True
    if query.get("export", [""])[0].lower() == "download":
        return True
    if path.endswith("/export") and query.get("format", [""])[0].lower() in {"xlsx", "csv"}:
        return True
    return False


async def transform_url_to_downloadable(url: str) -> tuple[str, str]:
    platform = detect_platform(url)
    transformed = url
    if platform == "google_sheets":
        transformed = transform_google_sheets_url(url)
    elif platform == "google_drive":
        transformed = transform_google_drive_url(url)
    elif platform == "onedrive":
        transformed = await transform_onedrive_url(url)
    elif platform == "sharepoint":
        transformed = transform_sharepoint_url(url)
    elif not is_likely_downloadable(url):
        logger.warning("URL may not be a direct download link: %s", url)

    logger.debug(
        "Transformed external data source URL",
        extra={"original_url": url, "transformed_url": transformed, "platform": platform},
    )
    return transformed, platform


def transform_google_drive_url(url: str) -> str:
    file_id = extract_google_file_id(url)
    if not file_id:
        return url
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def transform_google_sheets_url(url: str) -> str:
    file_id = extract_google_file_id(url)
    if not file_id:
        return url
    return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"


def extract_google_file_id(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if "d" in parts:
        try:
            candidate = parts[parts.index("d") + 1]
        except IndexError:
            candidate = ""
        if candidate:
            return candidate
    query_id = parse_qs(parsed.query).get("id", [""])[0]
    if query_id:
        return query_id
    match = GOOGLE_ID_RE.search(url)
    return match.group(0) if match else None


async def transform_onedrive_url(url: str) -> str:
    parsed = urlparse(url)
    if "1drv.ms" in parsed.netloc.lower():
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                response = await client.head(url)
                url = str(response.url)
                parsed = urlparse(url)
        except httpx.HTTPError:
            logger.warning("Could not resolve OneDrive short link: %s", url)
            return url
    if "onedrive.live.com" in parsed.netloc.lower():
        query = parse_qs(parsed.query)
        query["download"] = ["1"]
        return urlunparse(
            (
                parsed.scheme or "https",
                parsed.netloc,
                "/",
                "",
                urlencode({key: value[0] for key, value in query.items()}),
                "",
            )
        )
    return append_download_param(url)


def transform_sharepoint_url(url: str) -> str:
    return append_download_param(url)


def sharepoint_download_fallback(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            "/_layouts/15/download.aspx",
            "",
            urlencode({"SourceUrl": url}),
            "",
        )
    )


def append_download_param(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("download", [""])[0] == "1":
        return url
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
