# Premium Plan And Data Source Foundation V1

## What this adds

- A tenant-scoped `plan_tier` with `pilot`, `paid`, and `enterprise`
- A premium feature gate for `automated_data_sources`
- In-place tenant upgrades without changing `tenant_id`
- A saved external data source registry for future Google Sheets and Excel Online sync

## Why the plan is tenant-scoped

Automation unlocks at the tenant level because the setup, data ownership, mappings, and sync behavior belong to the tenant, not to one individual user. This keeps the upgrade path simple:

- same tenant
- same users
- same data
- same history

## Plan behavior

- `pilot`
  - manual uploads remain available
  - automated data source setup is blocked
- `paid`
  - automated data source setup is enabled
- `enterprise`
  - automated data source setup is enabled

Existing tenants default safely to `pilot`.

## Upgrade path

Superadmin can update a tenant plan in place:

- `pilot -> paid`
- `paid -> enterprise`
- `enterprise -> paid`

The upgrade does not recreate the tenant and does not migrate data to a new tenant. It preserves:

- `tenant_id`
- memberships and users
- uploaded data
- shipments
- stock snapshots
- thresholds
- exceptions
- historical records tied to the tenant

## Data source registry foundation

Saved registry fields:

- `tenant_id`
- `source_type`
- `source_url`
- `source_name`
- `dataset_type`
- `mapping_config_json`
- `sync_frequency_minutes`
- `is_active`
- `last_sync_status`
- `last_synced_at`
- `last_error_message`
- `created_at`
- `updated_at`

Supported source types in this foundation:

- `google_sheets`
- `excel_online`

Supported dataset types in this foundation:

- `shipments`
- `stock`
- `thresholds`

## What is intentionally not implemented yet

- remote fetch from Google Sheets
- remote fetch from Excel Online
- OAuth or credential exchange
- background scheduler
- sync execution pipeline
- billing provider integration
- automated retries or notifications

## Next steps

Later prompts can build on this by adding:

- connector authentication
- actual fetch and parse logic
- scheduled sync execution
- sync run history
- field mapping validation and preview
