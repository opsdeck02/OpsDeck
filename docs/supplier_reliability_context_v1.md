# Supplier Reliability Context V1

OpsDeck no longer treats supplier reliability as one universal score.

The same supplier can be reliable for one material and weak for another, or reliable on one plant lane and less reliable on another. V1 evaluates supplier reliability in operational context without turning OpsDeck into procurement software.

## Context Priority

When OpsDeck evaluates a shipment, it looks for recent supplier evidence in this order:

1. Same supplier, same plant, same material.
2. Same supplier, same material.
3. Same supplier globally within the tenant.
4. Unknown fallback.

V1 does not create global tenant defaults or supplier calibration tables.

## Evidence Window

V1 uses existing shipment rows only:

- up to the latest 10 shipments
- within the last 90 days
- tenant-scoped

No historical performance warehouse is added.

## Scoring

If at least three contextual shipments exist, the score is:

```text
contextual_reliability_score =
  0.65 * on_time_performance_ratio
  + 0.35 * average_visibility_confidence
```

V1 does not calculate fulfillment ratio because delivered quantity is not currently available in the shipment model. The intended fulfillment weight is redistributed across on-time performance and visibility confidence.

If fewer than three contextual shipments exist:

```text
contextual_reliability_score = 0.70
confidence_in_score = low
```

Reason:

```text
Insufficient supplier-context history; neutral reliability applied.
```

## On-Time Logic

A shipment is on-time when ETA behavior is `stable` or `recovering` under the ETA Confidence Behavior Engine.

This means ocean shipments receive wider ETA tolerance than inland shipments. A 12 hour ocean drift may remain stable, while a 12 hour inland drift can be degraded.

## Current Shipment Adjustments

After contextual history is scored, the current shipment can apply small deterministic adjustments:

- degraded ETA: `-0.10`
- repeatedly drifting ETA: `-0.15`
- volatile ETA: `-0.20`
- visibility confidence below `0.50`: `-0.10`
- abnormal shipment state: `-0.15`

The final score is clamped from `0.0` to `1.0`.

## Bands

- `>= 0.85`: strong
- `>= 0.70`: acceptable
- `>= 0.50`: watch
- `< 0.50`: weak
- missing supplier identity: unknown

## Interaction With Visibility Confidence

Supplier reliability can mildly adjust trusted inbound protection:

- strong: `+0.03`
- acceptable: `0`
- watch: `-0.05`
- weak: `-0.10`
- unknown: `0`

This modifier never changes physical inbound quantity. It only affects how much of the inbound quantity counts as trusted continuity protection.

## Examples

Same supplier, different material:

- Supplier is stable for domestic limestone into Plant A.
- The same supplier repeatedly drifts on imported coking coal into Plant A.
- OpsDeck scores those contexts separately.

Ocean versus inland:

- A 12 hour drift on an ocean shipment can remain acceptable under tolerant ETA expectations.
- A 12 hour drift on an inland truck near a plant is more operationally suspicious and can reduce reliability.

## Product Boundary

V1 does not create procurement recommendations, supplier scorecards for buying decisions, supplier calibration workflows, or vendor management features.

It provides continuity intelligence: how much supplier-context evidence should influence trusted inbound protection and risk explainability.
