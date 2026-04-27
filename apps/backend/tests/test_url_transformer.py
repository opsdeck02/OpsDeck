from __future__ import annotations

import pytest

from app.utils.url_transformer import (
    detect_platform,
    is_likely_downloadable,
    transform_url_to_downloadable,
)

FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890"


@pytest.mark.asyncio
async def test_google_drive_file_view_transforms_to_download_url() -> None:
    url, platform = await transform_url_to_downloadable(
        f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing"
    )
    assert platform == "google_drive"
    assert url == f"https://drive.google.com/uc?export=download&id={FILE_ID}"


@pytest.mark.asyncio
async def test_google_drive_file_edit_transforms_to_download_url() -> None:
    url, platform = await transform_url_to_downloadable(
        f"https://drive.google.com/file/d/{FILE_ID}/edit"
    )
    assert platform == "google_drive"
    assert url == f"https://drive.google.com/uc?export=download&id={FILE_ID}"


@pytest.mark.asyncio
async def test_google_drive_open_id_transforms_to_download_url() -> None:
    url, platform = await transform_url_to_downloadable(
        f"https://drive.google.com/open?id={FILE_ID}"
    )
    assert platform == "google_drive"
    assert url == f"https://drive.google.com/uc?export=download&id={FILE_ID}"


@pytest.mark.asyncio
async def test_google_sheets_edit_transforms_to_xlsx_export_url() -> None:
    url, platform = await transform_url_to_downloadable(
        f"https://docs.google.com/spreadsheets/d/{FILE_ID}/edit#gid=0"
    )
    assert platform == "google_sheets"
    assert url == f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"


@pytest.mark.asyncio
async def test_onedrive_live_edit_transforms_to_download_url() -> None:
    url, platform = await transform_url_to_downloadable(
        "https://onedrive.live.com/edit?resid=ABC123&cid=DEF456"
    )
    assert platform == "onedrive"
    assert url == "https://onedrive.live.com/?resid=ABC123&cid=DEF456&download=1"


@pytest.mark.asyncio
async def test_onedrive_live_view_transforms_to_download_url() -> None:
    url, platform = await transform_url_to_downloadable(
        "https://onedrive.live.com/view?resid=ABC123"
    )
    assert platform == "onedrive"
    assert url == "https://onedrive.live.com/?resid=ABC123&download=1"


@pytest.mark.asyncio
async def test_sharepoint_link_appends_download_param() -> None:
    url, platform = await transform_url_to_downloadable(
        "https://contoso.sharepoint.com/:x:/r/sites/ops/Shared%20Documents/stock.xlsx?web=1"
    )
    assert platform == "sharepoint"
    assert url.endswith("web=1&download=1")


@pytest.mark.asyncio
async def test_already_direct_url_is_unchanged() -> None:
    original = "https://example.com/files/stock.csv"
    url, platform = await transform_url_to_downloadable(original)
    assert platform == "unknown"
    assert url == original
    assert is_likely_downloadable(url)


@pytest.mark.asyncio
async def test_unknown_url_is_unchanged_with_warning(caplog) -> None:
    original = "https://example.com/report"
    url, platform = await transform_url_to_downloadable(original)
    assert platform == "unknown"
    assert url == original
    assert "may not be a direct download link" in caplog.text


def test_detect_platform() -> None:
    assert detect_platform(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/view") == "google_sheets"
    assert detect_platform(f"https://drive.google.com/file/d/{FILE_ID}/view") == "google_drive"
    assert detect_platform("https://1drv.ms/x/s!abc") == "onedrive"
    assert detect_platform("https://contoso.sharepoint.com/:x:/r/sites/ops/a.xlsx") == "sharepoint"
