# Production Interruption Impact V1

OpsDeck now keeps two impact concepts separate:

- **Material Exposure Value** is the existing material-based estimate. It uses exposed material quantity and configured material value assumptions.
- **Operational Interruption Impact** estimates production interruption exposure for a plant/material continuity risk when production economics are configured.

The operational calculation is deterministic. It is not machine learning, a recommendation, or a workflow.

## Required Config

Operational interruption impact requires an active config for the tenant, plant, and material. A config can optionally point at a backend-only production line.

V1 lookup priority is intentionally narrow:

1. Exact tenant, plant, material, and production line match when a `production_line_id` is available.
2. Tenant, plant, and material config where `production_line_id` is null.
3. Otherwise return `insufficient_config`.

Material-level defaults and tenant/global defaults are not supported by the V1 data model. OpsDeck does not infer wider defaults silently.

Required fields:

- `plant_id`
- `material_id`
- `production_line_id`, nullable
- `production_rate_mt_per_hour`
- `finished_goods_value_per_mt`
- `survivable_hours_without_material`
- `line_dependency_ratio`
- `downtime_cost_per_hour`
- `restart_cost`
- `restart_time_hours`
- `substitution_factor`
- `cascading_impact_factor`
- `interruption_probability_override`, nullable
- `currency`, default `INR`
- `is_active`

Ratios are constrained so `line_dependency_ratio`, `substitution_factor`, and probability override stay between `0.0` and `1.0`. Economic and hour fields must be non-negative.

## Formula

Risk hours remaining uses the existing value when present. If it is unavailable and days of cover exists:

```text
risk_hours_remaining = max(0, days_of_cover * 24)
```

Supply gap:

```text
if projected_exhaustion_date and next_trusted_inbound_eta:
  supply_gap_hours = max(0, next_trusted_inbound_eta - projected_exhaustion_date)
  gap_source = "observed_inbound_eta"
else if risk_hours_remaining <= 72:
  supply_gap_hours = max(0, 72 - risk_hours_remaining)
  gap_source = "estimated_fallback"
else:
  supply_gap_hours = 0
  gap_source = "none"
```

When projected exhaustion and next trusted inbound ETA are missing, the `72 - risk_hours_remaining` value is an estimated fallback gap. It is not treated as a real observed supply gap.

Restart survivability gap:

```text
raw_gap_hours = max(0, restart_time_hours - survivable_hours_without_material)
```

Estimated interruption:

```text
estimated_interruption_hours =
  max(supply_gap_hours, raw_gap_hours)
  * line_dependency_ratio
  * (1 - substitution_factor)
```

Impact:

```text
gross_production_impact =
  production_rate_mt_per_hour
  * finished_goods_value_per_mt
  * estimated_interruption_hours

downtime_impact =
  downtime_cost_per_hour
  * estimated_interruption_hours

restart_impact =
  restart_cost if estimated_interruption_hours > 0 else 0

gross_operational_impact =
  (gross_production_impact + downtime_impact + restart_impact)
  * cascading_impact_factor

estimated_operational_interruption_impact =
  gross_operational_impact
  * interruption_probability
```

## Probability

If `interruption_probability_override` is configured, OpsDeck uses it directly.

Otherwise OpsDeck starts with a conservative base probability:

- `immediate`: `0.75`
- `next_24h`: `0.65`
- `next_72h`: `0.45`
- `near_term`: `0.35`
- `watch`: `0.20`
- `monitor`, `unknown`, or `safe`: `0.10`

Then it adjusts for severity, inbound visibility, freshness, substitutability, and line dependency. The final value is clamped to `0.0` through `0.95`.

## Fallback Behavior

If config is missing, OpsDeck returns the old Material Exposure Value and marks operational interruption impact as `insufficient_config`.

If cover timing is missing, OpsDeck marks operational interruption impact as `insufficient_data`.

This prevents false financial precision when production economics or cover timing are not available.

## API Exposure

Stock cover calculations now include an `operational_interruption_impact` object alongside existing `estimated_value_at_risk`. Signal Engine risk candidates can also include the same object when plant/material context is available.
