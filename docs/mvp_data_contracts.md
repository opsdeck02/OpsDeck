# MVP Data Contracts

This document defines the onboarding-stage minimum data contract for MVP V1. The SQLAlchemy models and Alembic migration remain the source of truth; this file clarifies which fields are required at initial ingestion versus fields that can be enriched later.

## Validation Summary

- Stock-cover calculation is supported by `stock_snapshots.available_to_consume_mt`, `stock_snapshots.daily_consumption_mt`, and `plant_material_thresholds.threshold_days` / `warning_days` by `(tenant_id, plant_id, material_id)`.
- Exception workflow is supported by `exception_cases` status, severity, type, owner, linked shipment/plant/material, trigger time, due date, next action, and `exception_comments`.
- Inland movement tracking is supported by `inland_movements.shipment_id`, `mode`, `current_state`, and optional planned/actual milestone timestamps.
- All business tables include `tenant_id`.
- Tenant-scoped query indexes are present for the expected MVP access paths: shipments by tenant/plant/state, shipments by tenant/material/ETA, stock snapshots by tenant/plant/material/time, exceptions by tenant/status/severity/due date/owner, and ingestion jobs/files by tenant/status/source.

## Core Tables

| Table | Purpose | Minimum required during onboarding | Can be enriched later |
| --- | --- | --- | --- |
| `tenants` | Company/customer isolation boundary. | `name`, `slug` | Billing metadata, legal entity details, region, tenant settings |
| `users` | Global user identity for email/password auth and future SSO mapping. | `email`, `full_name`, `password_hash`, `is_active` | SSO subject, phone, avatar, notification preferences |
| `roles` | Global RBAC role catalog. | `name`, `description` | Fine-grained permissions, role metadata |
| `tenant_memberships` | Links users to tenants and roles. | `tenant_id`, `user_id`, `role_id`, `is_active` | Invitation state, expiry, plant-level scopes |
| `plants` | Steel plant, yard, or receiving location. | `tenant_id`, `code`, `name` | `location`, timezone, coordinates, ERP location IDs |
| `materials` | Tenant-specific raw material catalog. | `tenant_id`, `code`, `name`, `category`, `uom` | Grade/specification, quality parameters, supplier aliases |
| `plant_material_thresholds` | Stock-cover thresholds by plant/material. | `tenant_id`, `plant_id`, `material_id`, `threshold_days`, `warning_days` | Seasonal thresholds, safety stock tonnes, escalation policy |
| `shipments` | Main inbound raw-material shipment record. | `tenant_id`, `shipment_id`, `material_id`, `plant_id`, `supplier_name`, `quantity_mt`, `planned_eta`, `current_eta`, `current_state`, `source_of_truth`, `latest_update_at` | `vessel_name`, `imo_number`, `mmsi`, `origin_port`, `destination_port`, `eta_confidence`, richer supplier/PO references |
| `shipment_updates` | Timeline/history of shipment changes from ingestion/manual updates. | `tenant_id`, `shipment_id`, `source`, `event_type`, `event_time` | `payload_json`, `notes`, normalized diff fields |
| `stock_snapshots` | Point-in-time plant/material stock and consumption facts. | `tenant_id`, `plant_id`, `material_id`, `on_hand_mt`, `quality_held_mt`, `available_to_consume_mt`, `daily_consumption_mt`, `snapshot_time` | Quality breakdown, storage location, ERP batch/source document |
| `port_events` | Port/berth/discharge status for vessel-linked shipments. | `tenant_id`, `shipment_id`, `berth_status`, `waiting_days` | `discharge_started_at`, `discharge_rate_mt_per_day`, `estimated_demurrage_exposure`, berth name, agent notes |
| `inland_movements` | Rail/truck/barge movement after port or mine dispatch. | `tenant_id`, `shipment_id`, `mode`, `current_state` | `carrier_name`, `origin_location`, `destination_location`, planned/actual departure and arrival timestamps |
| `exception_cases` | Operational exception work queue. | `tenant_id`, `type`, `severity`, `status`, `title`, `triggered_at` | `summary`, linked shipment/plant/material, `owner_user_id`, `due_at`, `next_action`, root cause |
| `exception_comments` | Collaboration log for exception cases. | `tenant_id`, `exception_case_id`, `comment` | `author_user_id`, attachments, mentions |
| `audit_logs` | Tenant-scoped audit trail for business actions. | `tenant_id`, `action`, `entity_type`, `entity_id` | `actor_user_id`, `metadata_json`, request/source correlation IDs |
| `uploaded_files` | Tracks uploaded onboarding and ingestion files. | `tenant_id`, `original_filename`, `storage_uri`, `file_size_bytes`, `status` | `content_type`, `checksum_sha256`, `uploaded_by_user_id`, scan/validation metadata |
| `ingestion_jobs` | Tracks parsing/import jobs for files and future sources. | `tenant_id`, `source_type`, `status`, `records_total`, `records_succeeded`, `records_failed` | `uploaded_file_id`, `started_at`, `completed_at`, `error_message`, detailed validation summary |

## Workflow Notes

- Stock cover can be calculated as `available_to_consume_mt / daily_consumption_mt`, then compared against `warning_days` and `threshold_days`.
- `daily_consumption_mt` must be non-zero in application validation before calculating cover. The database stores the required field but does not enforce positive-only values yet.
- Shipment onboarding can start without vessel identifiers for rail/truck/mine-origin movements because `vessel_name`, `imo_number`, and `mmsi` are optional.
- Port events require an existing shipment. For non-port movements, create an `inland_movements` row instead of a placeholder port event.
- Exception cases can be created before ownership assignment because `owner_user_id` is optional.
- Every ingestion path should write `source_of_truth` or `source_type` values consistently so later conflict resolution can be added without reworking the schema.

## Relationship And Index Confirmation

- Foreign keys are present from each tenant-scoped business table to `tenants`.
- `shipments` references `materials` and `plants`.
- `shipment_updates`, `port_events`, and `inland_movements` reference `shipments`.
- `stock_snapshots` and `plant_material_thresholds` reference `plants` and `materials`.
- `exception_cases` can reference `shipments`, `plants`, `materials`, and `users`.
- `exception_comments` reference `exception_cases` and optionally `users`.
- `uploaded_files` optionally reference upload users, and `ingestion_jobs` optionally reference uploaded files.
- Tenant-first indexes are present for expected list/detail workflows. The only intentionally global lookup indexes are vessel identity helpers on `shipments.imo_number` and `shipments.mmsi`.

