# Automated Data Source Sync V1

## What this supports

Manual `Sync now` for saved premium data sources:

- `google_sheets`
- `excel_online`

The sync uses the existing ingestion pipeline, so fetched files go through the same parsing, validation, normalization, and upsert behavior as manual uploads.

## Supported URL types

### Google Sheets

Supported:

- public/shareable Google Sheets URLs like `https://docs.google.com/spreadsheets/d/<id>/edit`

How it works:

- SteelOps converts the saved Sheets URL into a Google export URL
- the file is fetched as CSV
- optional tab selection can be passed with `sheet_gid` in `mapping_config`

Limitations in this mode:

- no Google OAuth
- no private-sheet access
- no sheet-name lookup through Google APIs

### Excel Online / OneDrive / SharePoint

Supported:

- direct downloadable `.csv` URLs
- direct downloadable `.xlsx` URLs
- URLs with an explicit download-style format hint

Not supported:

- browser-only sharing links that do not resolve to a direct file download
- Microsoft Graph / authenticated workbook access

If the saved link is not directly downloadable, sync fails with a clear error message.

## What happens on Sync Now

1. SteelOps reads the saved data source entry
2. It fetches the remote file
3. It determines CSV or XLSX
4. It sends the content into the existing ingestion flow
5. It updates the registry entry with:
   - `last_sync_status`
   - `last_synced_at`
   - `last_error_message`

## Failure modes

Handled safely:

- inaccessible URL
- unsupported link format
- malformed CSV or XLSX
- unreadable spreadsheet content
- ingestion validation failure

On failure:

- the app does not crash
- tenant isolation is preserved
- the data source entry records the failure status and error message

## No-OAuth limitations

This version is intentionally simple:

- no OAuth
- no Microsoft Graph
- no Google API client
- no background scheduler

That means sync only works for links that are already publicly reachable or directly downloadable.

## Next step

The next prompt can add:

- scheduled recurring sync
- stronger connector auth
- better SharePoint / OneDrive compatibility
- richer sync history and retry behavior
