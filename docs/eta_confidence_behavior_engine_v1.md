# ETA Confidence Behavior Engine V1

OpsDeck no longer treats ETA slip as a single raw threshold.

A 12 hour ETA movement can be acceptable for an ocean shipment but severe for an inland truck near the plant. V1 adds contextual ETA behavior reasoning inside the existing Visibility Confidence Engine.

## Purpose

ETA behavior helps OpsDeck decide how much inbound material should count as trusted continuity protection.

It does not change physical inbound quantity. It only changes the confidence applied to inbound protection.

## Contextual ETA Tolerance

The engine derives an ETA tolerance profile from the shipment visibility profile:

- `ocean` -> `tolerant`
- `port` -> `moderate`
- `rail` -> `moderate`
- `inland` -> `strict`
- `mixed` -> `moderate`
- `unknown` -> `moderate`

If the shipment appears near destination from state or milestone text such as `arriving`, `final_delivery`, `unloading`, `near_plant`, or `gate_in`, the tolerance becomes `very_strict`.

Drift tolerance thresholds:

- `tolerant`: 24 hours
- `moderate`: 12 hours
- `strict`: 4 hours
- `very_strict`: 2 hours

## ETA Behavior States

- `stable`: ETA drift remains within the contextual tolerance.
- `drifting`: ETA drift exceeds tolerance once.
- `repeatedly_drifting`: ETA keeps moving forward, or delay status and stale visibility suggest repeated drift without a full ETA history store.
- `volatile`: ETA drift, stale visibility, and abnormal shipment behavior appear together.
- `recovering`: ETA was previously beyond tolerance but current ETA has stabilized or improved and abnormal conditions are clear.
- `degraded`: ETA drift is materially beyond tolerance.
- `unknown`: current or planned ETA is missing.

V1 uses only existing shipment fields: planned ETA, latest ETA, current ETA, delay status, shipment state, milestone, and visibility freshness. It does not create a logistics event history model.

## Confidence Effects

ETA behavior adjusts visibility confidence:

- `stable`: `0`
- `drifting`: `-0.10`
- `repeatedly_drifting`: `-0.20`
- `volatile`: `-0.35`
- `recovering`: `+0.05`
- `degraded`: `-0.25`
- `unknown`: `-0.10`

Visibility confidence is still clamped between `0.0` and `1.0`.

## Examples

Ocean shipment with 12 hour ETA drift:

- Profile: `ocean`
- Tolerance: `tolerant`
- Drift threshold: 24 hours
- ETA behavior: `stable`
- Result: confidence remains high when cadence and state are normal.

Inland truck with 12 hour ETA drift:

- Profile: `inland`
- Tolerance: `strict`
- Drift threshold: 4 hours
- ETA behavior: `degraded`
- Result: confidence is reduced because inland movement is expected to be more precise.

Near-plant shipment:

- Any shipment with destination-proximity state or milestone uses `very_strict`
- Drift threshold: 2 hours
- Result: small ETA movement near the plant matters more operationally.

Recovering shipment:

- Previous ETA was outside tolerance
- Current ETA stabilizes or improves
- No abnormal state remains
- Result: confidence gets a small recovery bonus.

## Interaction With Visibility Confidence

ETA behavior does not replace visibility confidence. It is one input into the same deterministic confidence calculation, alongside update cadence, shipment profile, abnormal state, and missing visibility fields.

The output still separates:

- physical inbound quantity
- trusted inbound protection
- visibility uncertainty

This keeps OpsDeck from implying that material disappeared when the real issue is ETA uncertainty.
