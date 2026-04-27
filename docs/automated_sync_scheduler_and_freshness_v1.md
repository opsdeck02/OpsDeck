# Automated Sync Scheduler And Freshness V1

## Scheduler approach

This version uses a lightweight in-process scheduler inside the backend service.

- on app startup, a background loop starts
- every minute it scans active saved data sources
- if a source is due based on `sync_frequency_minutes`, it runs the existing sync function

This keeps the implementation local-run friendly and avoids external queues or workers.

## Freshness definitions

Freshness is based on the last successful or failed sync timestamp relative to the configured frequency.

- `fresh`
  - last sync age is within the configured interval
- `aging`
  - last sync age is beyond the interval but within `1.5x` the interval
- `stale`
  - last sync age is beyond `1.5x` the interval
  - or the source has never synced

## Change signal logic

After each successful sync, SteelOps compares stock-cover state before and after ingestion.

It records simple aggregated signals:

- `new_critical_risks_count`
- `resolved_risks_count`
- `newly_breached_actions_count`

This is intentionally lightweight. It compares identifiers and counts, not a deep business diff.

## Failure handling

If a scheduled sync fails:

- `last_sync_status` becomes `failed`
- `last_error_message` is updated
- the scheduler loop keeps running
- other due sources continue to be processed

## Limitations

- in-process only
- no distributed coordination
- no dedicated worker pool
- approximate before/after diffing
- no historical sync-run timeline yet

## Future improvements

Later steps can add:

- external workers or queue-backed scheduling
- richer sync history
- per-run audit views
- event-driven refresh triggers
- stronger freshness policy controls
