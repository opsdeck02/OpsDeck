# Inbound Delay vs Cover Intelligence V1

OpsDeck no longer treats every delayed shipment as an automatic high continuity risk.

Raw delay versus raw days of cover is too blunt. A five day cover position can be acceptable for a fast local material and dangerous for an imported or strategically constrained material. V1 evaluates whether a delay threatens operational cover protection.

## Inputs

Inbound Delay vs Cover Intelligence uses:

- days of cover
- trusted days of cover
- trusted inbound protection
- visibility uncertainty
- ETA behavior
- visibility confidence
- supplier reliability context
- configured continuity thresholds
- projected exhaustion date when available

It does not create procurement recommendations or reorder actions.

## Cover Pressure

OpsDeck first determines cover pressure:

```text
if days_of_cover <= threshold_days:
  cover_pressure = critical
else if days_of_cover <= warning_days:
  cover_pressure = warning
else:
  cover_pressure = normal
```

Configured plant-material thresholds are used when present. If no configuration exists, V1 preserves the existing fallback boundaries:

- critical threshold: 2 days
- warning threshold: 5 days

## Trusted Inbound Protection

The engine separates physical inbound from trusted protection:

```text
trusted_inbound_ratio =
  trusted_inbound_protection_mt / physical_inbound_quantity_mt
```

If the ratio is below `0.50`, trusted protection is considered weak.

Physical inbound quantity is never reduced. The risk is about confidence and timing, not missing material.

## ETA Threat

ETA behavior comes from the ETA Confidence Behavior Engine:

- `stable` or `recovering`: low threat
- `drifting`: medium threat
- `degraded` or `repeatedly_drifting`: high threat
- `volatile`: critical threat
- `unknown`: watch threat

This means an ocean ETA drift can be treated differently from an inland drift near plant.

## Delay Against Cover

V1 calculates:

```text
delay_exceeds_cover =
  eta_delay_hours / 24 >= days_of_cover

delay_exceeds_threshold_window =
  eta_delay_hours / 24 >= max(0, days_of_cover - threshold_days)
```

The second condition catches delays that may not consume all cover but can push the material into its critical threshold window.

## Severity

Critical if:

- cover pressure is critical
- ETA threat is high or critical
- trusted protection is weak

High if:

- cover pressure is warning or critical and ETA threat is medium, high, or critical
- or delay can push the material into the critical threshold window and trusted protection is weak

Medium if:

- cover pressure is warning
- or trusted protection is weak
- or ETA threat is medium

Low if:

- there is delay or uncertainty but cover pressure is normal

None if:

- ETA is stable or recovering
- trusted protection is strong
- cover pressure is normal

Weak supplier reliability can increase concern slightly only when a delay is already risky.

## Examples

Ocean shipment with stable ETA:

- Cover pressure is normal
- ETA behavior is stable under ocean tolerance
- Trusted protection is strong
- Result: no inbound delay risk

Inland delay with weak trusted protection:

- Inland ETA behavior is degraded
- Visibility confidence is weak
- Trusted protection ratio falls below `0.50`
- Result: risk escalates based on cover pressure and timing

Delay pushing material into critical threshold:

- Days of cover is above the critical threshold
- ETA delay does not exceed full cover
- But delay can push the material into the configured critical threshold window
- Result: high risk when trusted protection is weak

## Product Boundary

This engine does not say material disappeared.

It does not recommend ordering more material. It supports operational continuity reasoning by explaining whether inbound delay threatens cover protection.
