# Action Recommendation V1

This layer adds deterministic next-step guidance on top of existing stock-cover and impact outputs.

## Rules

- Low confidence plus stale contributing shipment:
  recommend validating ETA with logistics or supplier immediately.
- Port or discharge activity with weak protection:
  recommend prioritizing port clearance or discharge follow-through.
- Critical status with materially weaker effective inbound than raw inbound:
  recommend validating stock position and expediting inbound recovery actions.
- Remaining weak or reduced protection:
  recommend reviewing alternate recovery options and a demand protection plan.

## Owner Mapping

- `logistics_user`:
  stale ETA validation and port/discharge follow-through.
- `planner_user`:
  stock validation and inbound recovery coordination for critical continuity gaps.
- `buyer_user`:
  recovery options and demand protection planning when protection remains weak.
- `tenant_admin`:
  fallback when no narrower operational owner is obvious.

## Deadline Mapping

- `immediate` -> `4` hours
- `next_24h` -> `12` hours
- `next_72h` -> `24` hours
- `monitor` -> `48` hours

## Examples

- Critical row, low confidence, stale shipment:
  logistics validation action with a short deadline.
- Critical row, raw inbound present but effective protection much lower:
  planner-led stock and recovery validation.
- Warning row, no strong inbound protection:
  buyer-led recovery planning.

## Known Limitations

- Recommendations are rule-based and not editable yet.
- Owner role is suggested, not auto-assigned.
- No substitute-material, scenario, or notification logic is included.
- Exception linkage only surfaces existing open-owner context; it does not change exception behavior.

## Future V2 Improvements

- Tenant-configurable rule tuning.
- Manual override and acknowledgement workflow.
- Better linkage between recommendations, exceptions, and assignment queues.
- Scenario-aware recommendations once simulation logic exists.
