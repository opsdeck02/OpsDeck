# Visibility Confidence Engine V1

OpsDeck no longer treats raw shipment update age as the same thing as operational reliability.

Freshness alone is too blunt. An ocean shipment can sit at sea for several days with stable ETA and no abnormal signal. That should not be treated like an inland truck that has gone silent for 24 hours.

## Core Separation

V1 separates physical inbound material from continuity protection trust:

- `physical_inbound_quantity_mt`: the actual shipment quantity.
- `trusted_inbound_protection_mt`: the portion OpsDeck trusts for continuity protection.
- `visibility_uncertain_quantity_mt`: physical inbound quantity that exists but is not fully trusted operationally.
- `visibility_confidence`: deterministic confidence ratio from `0.0` to `1.0`.

This avoids implying that material disappeared. It also reduces duplicate procurement risk caused by misunderstanding visibility uncertainty as missing material.

## Visibility Profiles

The engine infers a profile from existing shipment fields:

- `ocean`: vessel name, IMO, or MMSI exists.
- `port`: shipment state or milestone suggests port/discharge/berth.
- `inland`: shipment state or milestone suggests inland, truck, dispatch, or en-route movement.
- `rail`: milestone or source indicates rail.
- `unknown`: insufficient context.

Default expected visibility cadence:

- `ocean`: 72 hours
- `port`: 24 hours
- `inland`: 6 hours
- `rail`: 24 hours
- `mixed`: 24 hours
- `unknown`: 24 hours

## ETA Stability

ETA stability compares current ETA against baseline ETA.

- `stable`: ETA slip is `<= 0`
- `drifting`: ETA slip is `> 0` and `<= 24 hours`
- `degraded`: ETA slip is `> 24 hours`
- `unknown`: current ETA or baseline ETA is missing

## Confidence Formula

Base confidence:

- `ocean`: `0.90`
- `port`: `0.80`
- `inland`: `0.75`
- `rail`: `0.80`
- `mixed`: `0.75`
- `unknown`: `0.60`

Update age penalties:

- Within cadence: no penalty
- Over cadence and within `2x` cadence:
  - ocean with stable ETA: `-0.05`
  - otherwise: `-0.15`
- Over `2x` cadence:
  - ocean with stable ETA: `-0.15`
  - otherwise: `-0.35`

ETA penalties:

- `stable`: no penalty
- `drifting`: `-0.10`
- `degraded`: `-0.25`
- `unknown`: `-0.10`

Abnormal shipment state or milestone such as delayed, cancelled, blocked, hold, or exception applies `-0.30`.

If both ETA and update timestamp are missing, the engine applies `-0.20`.

The final confidence is clamped to `0.0` through `1.0`.

## Impact On Cover

Inventory continuity uses `trusted_inbound_protection_mt` for trusted cover and trusted days of cover.

It does not reduce physical inbound quantity. Any difference between physical inbound and trusted protection appears as `visibility_uncertain_quantity_mt`.

## Examples

Ocean shipment with stable ETA and 48 hours since update:

- Profile: `ocean`
- Cadence: `72 hours`
- ETA: `stable`
- Confidence remains high because the update age is still within expected ocean cadence.

Inland shipment with 24 hours since update:

- Profile: `inland`
- Cadence: `6 hours`
- Update age is greater than `2x` cadence
- Confidence is significantly reduced because inland movement should update more frequently.

## V1 Limits

Profile defaults are deterministic and not admin-configurable yet.

The engine does not use machine learning, supplier calibration, procurement recommendations, or workflow logic.
