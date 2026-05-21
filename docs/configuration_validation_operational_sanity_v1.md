# Configuration Validation & Operational Sanity V1

OpsDeck now validates operational configuration quality for each plant-material context.

The goal is pilot-readiness: detect missing, contradictory, or unrealistic assumptions before users treat risk output as fully calibrated.

This is deterministic validation. It is not machine learning, workflow automation, procurement automation, or auto-remediation.

## Validation Status

Each validation response returns:

- `ready`: no blocking errors and readiness score is at least `85`.
- `usable_with_warnings`: no blocking errors, but readiness score is below `85`.
- `incomplete`: readiness score is below `50`.
- `invalid`: at least one blocking error exists.

## Severity Levels

- `error`: impossible or contradictory configuration that can make reasoning invalid.
- `warning`: risky, incomplete, or unrealistic configuration that can weaken risk precision.
- `info`: useful calibration improvement that should not block pilot usage.

Most findings are warnings or info. OpsDeck should not make pilot onboarding painful, but it should not silently accept dangerous operational assumptions.

## Readiness Score

Readiness starts at `100`.

Penalties:

- Each error: `-25`
- Each warning: `-8`
- Each info: `-2`

The score is clamped from `0` to `100`.

## Areas Checked

V1 validates:

- `continuity_thresholds`
- `interruption_impact`
- `product_process_dependency`
- `shipment_inbound_trust`
- `supplier_context`
- `inventory_visibility`
- `shipment_visibility`
- `data_mapping`
- `general`

## Example Findings

Product mix missing:

- Description: material is linked to a process, but the process has no product mix configured.
- Operational impact: interruption impact may fall back to blended output value or lose product-level precision.
- Suggested fix: add product mix rows under Product & Process Dependency.

Shipment trust cadence too strict:

- Description: ocean/import profile uses an expected update cadence below 12 hours.
- Operational impact: normal import update gaps may be treated as weak visibility.
- Suggested fix: use a cadence that reflects ocean or port update rhythm.

Daily consumption not positive:

- Description: daily consumption is zero or negative for a monitored material.
- Operational impact: days-of-cover cannot be calculated reliably.
- Suggested fix: upload or configure a positive daily consumption rate.

## API

Tenant admins can inspect validation for a plant-material context:

```text
GET /api/v1/impact/configuration-validation?plant_id=&material_id=
```

The frontend proxies this through:

```text
GET /api/impact/configuration-validation?plant_id=&material_id=
```

## Frontend Visibility

Operational configuration pages show a compact Configuration Readiness panel after plant/material selection. The panel shows:

- readiness score
- validation status
- count of errors, warnings, and info findings
- top findings

The UI does not invent values. If validation cannot be loaded, it shows a compact unavailable state.

## Product Boundary

This layer does not change risk formulas, suppress risks, create tasks, trigger procurement, or automatically repair configuration. It only explains whether current operational assumptions are complete and sane enough to trust the precision of the resulting continuity intelligence.
