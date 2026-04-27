# Impact Engine V1

## Purpose
Translate stock-cover risk into a small, deterministic business-impact layer for leadership.

## Inputs
- `days_of_cover`
- `status`
- `threshold_days`
- `warning_days`
- `daily_consumption_mt`
- `effective_inbound_pipeline_mt`
- `confidence_level`

## Outputs
- `risk_hours_remaining = days_of_cover * 24`
- `estimated_production_exposure_mt`
- `estimated_value_at_risk`
- `urgency_band`

## Formulas
- `risk_hours_remaining = days_of_cover * 24`
- `severity_days`
  - critical: `max(threshold_days - days_of_cover, 0)`
  - warning: `max(warning_days - days_of_cover, 0)` when warning threshold exists
  - otherwise: `0`
- `estimated_production_exposure_mt = daily_consumption_mt * severity_days * criticality_multiplier * confidence_factor`
- `estimated_value_at_risk = estimated_production_exposure_mt * value_per_mt`

## Confidence Factors
- high: `1.00`
- medium: `0.90`
- low: `0.75`

## Urgency Rules
- `monitor`
  - safe
  - insufficient data
  - no usable risk horizon
- `immediate`
  - `days_of_cover <= 1`
- `next_24h`
  - `risk_hours_remaining <= 24`
- `next_72h`
  - `risk_hours_remaining <= 72`
  - or any remaining critical item outside 24h

## Config Assumptions
Config lives in `app/modules/impact/config.py`.

Supported today:
- per-material defaults
- per-plant-material overrides

Supported keys:
- `value_per_mt`
- `criticality_multiplier`

Fallback defaults:
- `value_per_mt = 250.00`
- `criticality_multiplier = 1.00`

## Value-at-Risk Assumptions
- deterministic only
- uses local config, not market feeds
- intended as leadership directional signal, not finance-grade valuation

## Known Limitations
- no substitute-material logic
- no plant operating rate simulation
- no commercial contract awareness
- no downtime conversion into revenue or margin
- no customer-editable config UI yet

## What V2 Can Improve Later
- customer-managed impact settings
- plant-material specific business value mapping
- substitution and recovery offsets
- exception-driven impact rollups
- scenario simulation
