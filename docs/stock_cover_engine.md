# Stock Cover Engine

This document describes the MVP V1 stock-cover engine used by the dashboard command-center view.

## Formula

For each tenant-scoped `plant_id + material_id` combination:

1. Select the latest available `stock_snapshots` record.
2. Set:

   - `current_stock_mt = available_to_consume_mt`
   - `inbound_pipeline_mt = sum(quantity_mt)` for relevant inbound shipments
   - `total_considered_mt = current_stock_mt + inbound_pipeline_mt`
   - `daily_consumption_mt = latest stock snapshot daily_consumption_mt`
   - `days_of_cover = total_considered_mt / daily_consumption_mt`

3. Compare `days_of_cover` against threshold configuration:

   - `critical` if `days_of_cover <= threshold_days`
   - `warning` if `days_of_cover <= warning_days`
   - `safe` otherwise

4. Estimate:

   - `estimated_breach_date = latest_snapshot_time + days_of_cover`

## Shipment Assumption In MVP

Until shipment completion and inland-movement progression become richer, the engine uses a conservative temporary rule:

- Count only shipments whose state is not completed or cancelled.
- Specifically include shipment states:
  - `planned`
  - `in_transit`
  - `at_port`
  - `discharging`
  - `inland_transit`
  - `delayed`
- Sum full shipment quantity into `inbound_pipeline_mt`.

This is intentionally simple and deterministic. Later versions should phase inbound quantity by more detailed milestones such as discharge progress, inland movement status, and expected receipt windows.

## Insufficient Data Rules

The engine returns `insufficient_data` instead of a misleading estimate when:

- no stock snapshot exists for the plant/material
- `daily_consumption_mt` is missing, zero, or negative

In those cases, `days_of_cover` and `estimated_breach_date` are not calculated.

## Missing Threshold Behavior

If a threshold is missing:

- the engine still calculates `days_of_cover` if stock and consumption are available
- the record remains visible in the dashboard
- `threshold_days` and `warning_days` are `null`
- the response includes a reason noting that threshold configuration is missing

This allows onboarding progress without hiding usable stock data.

## Confidence Rules

Confidence is deterministic and explainable:

### High

- latest stock snapshot is within 24 hours
- threshold exists
- and either:
  - there are no contributing shipments, or
  - contributing shipment updates are recent (within 48 hours)

### Medium

- latest stock snapshot is within 72 hours
- but one or more support signals are weaker, such as threshold absence or older shipment updates

### Low

- latest stock snapshot is older than 72 hours
- or the estimate relies on clearly incomplete upstream data

The detail API also returns human-readable confidence reasons for the UI.

## Data Freshness

The engine exposes `data_freshness_hours` based on the age of the latest stock snapshot used in the calculation.

## Known MVP Limitations

- Inbound pipeline uses full shipment quantity and does not phase receipt timing.
- Shipment quantity is not reduced by discharge completion, partial receipt, or inland transfer completion.
- No exception workflow is triggered yet from stock-cover results.
- Missing threshold configuration does not yet create system alerts.
- Consumption validity is enforced only at calculation time, not by additional database constraints.

## Future Enrichment

When shipment state and inland movement become richer, the engine should evolve to:

- discount shipments by stage confidence and expected receipt timing
- split vessel quantity between discharged and not-yet-discharged portions
- include inland movement ETA confidence in pipeline estimates
- support time-phased cover projections instead of a single aggregate estimate
- feed downstream exception generation automatically

