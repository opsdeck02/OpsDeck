# Shipment & Inbound Trust Configuration V1

Tenant admins configure shipment visibility expectations at:

```text
Admin -> Operational Configuration -> Shipment & Inbound Trust
```

The purpose is to calibrate how OpsDeck interprets inbound visibility and ETA behavior for a specific plant-material context. This prevents normal update gaps, such as ocean shipments at sea, from being treated like suspicious inland truck silence.

## Fields

- `visibility_profile`: `ocean`, `port`, `inland`, `rail`, `mixed`, or `unknown`
- `expected_visibility_cadence_hours`
- `eta_drift_tolerance_hours`
- `weak_visibility_threshold`
- `minimum_trusted_inbound_ratio`, nullable
- `allow_unverified_inbound_protection`
- `is_active`

## Backend Consumption

For a matching tenant, plant, and material:

- Visibility Confidence uses configured `visibility_profile`.
- Visibility Confidence uses configured `expected_visibility_cadence_hours` instead of profile defaults.
- ETA behavior uses configured `eta_drift_tolerance_hours` instead of profile tolerance defaults.
- Inbound Delay vs Cover uses `weak_visibility_threshold` when deciding whether trusted inbound protection is weak.
- If `minimum_trusted_inbound_ratio` is set, Inbound Delay vs Cover also treats protection below that ratio as weak.
- If `allow_unverified_inbound_protection` is false, shipments without enough ETA/update visibility are capped at the configured weak visibility threshold.

If no active config exists, OpsDeck preserves the deterministic V1 defaults.

## Safety Boundary

This configuration never changes physical inbound quantity. It only changes how much of that physical inbound is trusted as operational protection.

Use:

- physical inbound
- trusted inbound protection
- visibility uncertainty

Avoid interpreting visibility uncertainty as missing or lost material. OpsDeck does not generate reorder recommendations from this configuration.
