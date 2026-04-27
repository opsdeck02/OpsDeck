# Stock Cover Refinement

This document describes the MVP V1 stock-cover refinement that replaces the old raw active-shipment total with a weighted inbound pipeline.

## Refined Formula

For each tenant-scoped plant/material combination:

- `current_stock_mt = available_to_consume_mt`
- `raw_inbound_pipeline_mt = sum(raw shipment quantity)` for non-delivered and non-cancelled shipments
- `effective_inbound_pipeline_mt = sum(raw quantity * contribution factor)`
- `total_considered_mt = current_stock_mt + effective_inbound_pipeline_mt`
- `days_of_cover = total_considered_mt / daily_consumption_mt`

Threshold evaluation continues to use:

- `critical` if `days_of_cover <= threshold_days`
- `warning` if `days_of_cover <= warning_days`
- `safe` otherwise

## Contribution Factor Rules

The current contribution factor is:

- `state factor * confidence factor * freshness factor`

### State Factors

- `planned` => `0.20`
- `on_water` => `0.35`
- `at_port` => `0.60`
- `discharging` => `0.80`
- `in_transit` => `0.90`
- `delivered` => `0.00`
- `cancelled` => `0.00`

Interpretation:

- on-water material protects less because receipt timing is still uncertain
- at-port and discharging material protect more
- inland-dispatched material protects the most in MVP

## Confidence / Freshness Adjustment Rules

### Confidence Factors

- `high` => `1.00`
- `medium` => `0.85`
- `low` => `0.60`

### Freshness Factors

- `fresh` => `1.00`
- `aging` => `0.90`
- `stale` => `0.70`
- `unknown` => `0.80`

The engine uses shipment visibility plus movement summaries to pick the relevant freshness source:

- port freshness for `at_port` / `discharging`
- inland freshness for `in_transit` when inland movement exists
- shipment freshness otherwise

## Examples

### Example 1: On-water vessel

- raw quantity = `400 MT`
- state = `on_water`
- confidence = `medium`
- freshness = `aging`

Contribution factor:

- `0.35 * 0.85 * 0.90 = 0.26775`

Effective quantity:

- `400 * 0.26775 = 107.10 MT`

### Example 2: Inland dispatched movement

- raw quantity = `400 MT`
- state = `in_transit`
- confidence = `high`
- freshness = `fresh`

Contribution factor:

- `0.90 * 1.00 * 1.00 = 0.90`

Effective quantity:

- `400 * 0.90 = 360 MT`

## Exception Compatibility

`stock_cover_warning` and `stock_cover_critical` now operate on the refined effective stock-cover result because the exception engine reads the current stock-cover service output.

This means:

- stale or low-confidence inbound protection can lower effective days of cover
- warning/critical continuity cases can surface earlier than with naive raw inbound totals

## Known MVP Limitations

- Partial discharge and partial inland receipt are not modeled yet.
- State factors are deterministic heuristics, not probabilistic estimates.
- No predictive ETA model is included yet.
- AIS and richer inland telemetry are not included yet.
- Weighting is shipment-level, not time-phased day by day.

## Future Improvement Path

Later enrichment can improve this model by:

- using AIS milestones to tighten on-water confidence
- using discharge progress to move from medium/high factors toward receipt-ready factors
- using inland milestone events to phase available quantity by expected plant arrival timing
- moving from static factors to milestone-aware time-phased cover projections
