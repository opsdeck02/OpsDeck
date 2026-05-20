# Action Recommendation Engine V1

OpsDeck now generates deterministic operational action recommendations for continuity risks.

The engine supports human judgement. It does not automate procurement, create purchase orders, approve suppliers, change inventory, or route workflow approvals.

## Product Boundary

Recommendations are operational prompts, not autonomous actions.

Allowed language focuses on:

- monitoring
- validating inbound status
- validating ETA
- expediting existing inbound recovery
- escalating supplier context for human review
- reviewing recovery plans
- activating configured substitution
- reviewing reserve usage
- validating tracking visibility
- confirming port clearance
- confirming inland movement

The engine never recommends placing an order, buying material, approving a purchase order, or automatically replacing a supplier.

## Human In The Loop

Every recommendation includes:

- `requires_human_validation = true`
- an operational reason
- supporting signals
- a reason chain explaining why the action was generated

OpsDeck distinguishes visibility uncertainty from actual shortage. Physical inbound quantity is not treated as missing material.

## Action Types

- `monitor`: cover, ETA, and trusted protection remain acceptable.
- `verify_inbound`: physical inbound exists, but trusted protection or visibility confidence is weak.
- `validate_eta`: ETA is drifting and should be confirmed before escalation.
- `expedite_inbound`: timing threatens configured continuity thresholds.
- `escalate_supplier`: supplier-context reliability weakens inbound confidence.
- `review_recovery_plan`: high interruption impact combines with low survivability and weak inbound protection.
- `activate_substitution`: configured substitution flexibility may reduce exposure.
- `review_reserve_usage`: protected reserve threshold is breached while trusted protection is weak.
- `validate_tracking_visibility`: ocean or port shipment has stale visibility but stable ETA.
- `confirm_port_clearance`: port or ocean context has hold/discharge/clearance signals while timing matters.
- `confirm_inland_movement`: inland movement near plant has stale visibility and degraded ETA.

## Inputs

V1 uses existing backend outputs:

- risk severity
- days of cover and continuity thresholds
- interruption impact
- trusted inbound protection
- visibility uncertainty
- ETA behavior
- visibility confidence
- supplier reliability band
- protected reserve reasons
- substitution factor and survivability when present in interruption impact explainability

No new data model, admin UI, workflow engine, or machine learning model is added.

## Priority Score

Action priority is deterministic and clamped to `0.0` through `100.0`.

The score combines:

- risk severity
- exposure level inferred from severity and cover timing
- ETA behavior severity
- weak trusted inbound protection
- meaningful or high operational interruption impact
- action urgency

## Explainability

Each action explains why it exists and why human validation is required.

Examples:

- “Inbound quantity exists physically but operational visibility confidence is reduced.”
- “ETA movement should be operationally validated before escalation.”
- “Inbound timing threatens continuity threshold protection.”
- “Configured operational substitution flexibility may reduce continuity exposure.”

## Why No Procurement Automation Exists

OpsDeck is a continuity intelligence layer. V1 recommends operational validation and escalation paths, but it does not decide commercial action. That boundary prevents visibility uncertainty from being misread as missing material and avoids duplicate procurement behavior.
