# Exception Workflow

This document describes the MVP V1 exception engine and workflow layer.

## Trigger Rules

The current deterministic triggers are:

- `stock_cover_critical`
  - created when the stock-cover engine returns `critical`
- `stock_cover_warning`
  - created when the stock-cover engine returns `warning`
- `shipment_eta_delay`
  - created when `current_eta` is more than 24 hours later than `planned_eta`
- `shipment_stale_update`
  - created when shipment confidence is `low` because updates are stale or only weak source data exists
- `inland_delay_risk`
  - created when the latest inland movement is overdue against planned arrival, arrived late, or is internally inconsistent

## Deduplication And Idempotency

The engine evaluates current tenant state on demand.

- It looks for an existing active exception with the same:
  - trigger source
  - linked shipment, if shipment-scoped
  - linked plant/material, if stock-scoped
  - mapped exception category
- If the same issue still exists:
  - the open exception is updated in place
  - no duplicate open case is created
- If the issue clears:
  - the active exception is marked `resolved`

This keeps evaluation idempotent while preserving case history.

## Severity Mapping

- `stock_cover_critical` => `critical`
- `stock_cover_warning` => `high`
- `shipment_eta_delay` => `medium` when delay is 24-71 hours, `high` at 72+ hours
- `shipment_stale_update` => `medium`
- `inland_delay_risk` => `medium` for smaller delays or inconsistent completion signals, `high` for 24+ hour inland delay

## Status Flow

Supported workflow statuses in the API/UI:

- `open`
- `in_progress`
- `resolved`
- `closed`

Implementation note:

- the current database enum already includes `dismissed`
- the MVP API exposes that as `closed`

## Manual Evaluation Flow

The MVP engine is evaluated through:

- `POST /api/v1/exceptions/evaluate`

This endpoint reads the current stock-cover and shipment state, refreshes matching cases, and resolves cleared ones.

## Comments And Ownership

- Owner assignment is manual and tenant-scoped.
- Exceptions may remain unassigned.
- Comments are timestamped and stored in `exception_comments`.
- Audit entries are written for create, update, resolve, assign, status change, and comment actions.

## Known MVP Limitations

- Evaluation is on-demand only; no scheduler is added yet.
- Stock-cover exceptions depend on the current simplified inbound-pipeline assumption.
- Shipment stale-update logic is intentionally simple and based on recency plus source coverage.
- Inland delay risk uses only the latest inland movement record.
- No notifications, escalations, or AI recommendations are included yet.

## Future Integration

Later enrichment can improve this layer without replacing the workflow structure:

- AIS and richer port signals can improve ETA-delay and stale-update precision.
- Inland progression can move from latest-record checks to milestone-aware delay logic.
- Stock-cover refinement can weight shipment contribution bands before triggering continuity exceptions.
