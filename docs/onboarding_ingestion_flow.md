# Onboarding Ingestion Flow

This MVP supports tenant-scoped manual uploads for three onboarding file types:

- `shipment`: inbound shipment master/ETA data
- `stock`: point-in-time stock snapshot data
- `threshold`: plant-material stock cover thresholds

CSV and XLSX files are supported. Email ingestion, AIS enrichment, and shared-folder sync are intentionally out of scope for MVP V1.

## Required Columns

Column headers are normalized with alias mapping, so common variants such as `Shipment ID`, `shipment_id`, `shipment ref`, and `reference` are accepted where possible.

### Shipment Upload

Required:

- `shipment_id`
- `plant_code`
- `material_code`
- `supplier_name`
- `quantity_mt`
- `planned_eta`
- `current_eta`
- `current_state`
- `source_of_truth`
- `latest_update_at`

Optional enrichment:

- `vessel_name`
- `imo_number`
- `mmsi`
- `origin_port`
- `destination_port`
- `eta_confidence`

### Stock Snapshot Upload

Required:

- `plant_code`
- `material_code`
- `on_hand_mt`
- `quality_held_mt`
- `available_to_consume_mt`
- `daily_consumption_mt`
- `snapshot_time`

Important validation:

- `daily_consumption_mt` must be greater than zero. Records with missing, zero, or negative daily consumption are rejected because they are not stock-cover-ready.

### Plant-Material Threshold Upload

Required:

- `plant_code`
- `material_code`
- `threshold_days`
- `warning_days`

## Processing Flow

1. The user uploads a CSV or XLSX file from the dashboard onboarding page.
2. The backend creates an `uploaded_files` record with filename, size, checksum, uploader, tenant, and status.
3. The backend creates an `ingestion_jobs` record with source type, status, and counters.
4. The parser normalizes messy headers into canonical fields.
5. Each row is validated using the MVP data contracts.
6. Plants and materials are resolved by `tenant_id` plus `plant_code` / `material_code`.
7. Valid rows are written to tenant-scoped records.
8. The ingestion job is updated with received, accepted, rejected, and error counts.

## Idempotency Behavior

- Shipment uploads upsert by `(tenant_id, shipment_id)`.
- Re-uploading an unchanged shipment returns `unchanged` and does not create a duplicate shipment.
- If current ETA or shipment state changes, the shipment is updated and a `shipment_updates` row is created for auditability.
- Stock uploads upsert by `(tenant_id, plant_id, material_id, snapshot_time)`.
- Threshold uploads upsert by `(tenant_id, plant_id, material_id)`.
- Each upload still creates a new `uploaded_files` and `ingestion_jobs` record so the upload history remains auditable.

## API Endpoints

- `POST /api/v1/ingestion/uploads`
- `GET /api/v1/ingestion/jobs`
- `GET /api/v1/ingestion/templates/shipment`
- `GET /api/v1/ingestion/templates/stock`
- `GET /api/v1/ingestion/templates/threshold`

## Known Limitations

- There is no production mapping UI yet; backend alias mapping handles common messy headers.
- There is no async worker handoff yet; parsing runs inline for MVP onboarding.
- Uploaded file storage is local filesystem storage for local-run development.
- Cross-row validation is intentionally minimal.
- The parser resolves existing plants and materials only; uploads do not create new plant/material master data.
- XLSX support reads the first worksheet only.

