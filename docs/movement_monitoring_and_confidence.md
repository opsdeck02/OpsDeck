# Movement Monitoring And Confidence

This document describes the MVP V1 port and inland monitoring layer.

## Port Summary Rules

Port summaries are derived from the latest `port_events` record for a shipment.

- `discharging`
  - when `discharge_started_at` is present, or berth status maps to a discharge state
- `waiting`
  - when berth status maps to `waiting` or `anchored`
- `arrived_at_port`
  - when berth status maps to `arrived`, `at_port`, or `berthed`

The summary exposes:

- latest berth state
- waiting time in days
- latest discharge-related timestamp
- freshness
- confidence

## Inland Summary Rules

Inland summaries are derived from the latest `inland_movements` record for a shipment.

- `delivered`
  - when actual arrival is present, or inland state indicates arrival/completion
- `inland_dispatched`
  - when actual departure is present, or inland state is an active in-transit state
- `planned_dispatch`
  - when a planned departure exists but dispatch is not yet confirmed
- `movement_recorded`
  - fallback when a record exists but milestones are incomplete

The summary exposes:

- transporter name when present
- expected arrival
- actual arrival
- inland delay flag
- freshness
- confidence

## Freshness Rules

Freshness is deterministic and reused across shipment, port, and inland views.

- `fresh`
  - last update within 24 hours
- `aging`
  - last update between 24 and 72 hours
- `stale`
  - last update older than 72 hours
- `unknown`
  - no usable timestamp available

The API returns both the freshness label and the exact last-updated timestamp.

## Confidence Rules

Confidence is deterministic and based on:

- source recency
- completeness of milestone fields
- conflict between shipment and movement signals
- missing ETA / expected-arrival fields

Current categories:

- `high`
  - fresh data and key milestone fields are present
- `medium`
  - data is fresh or aging, but some milestone fields are missing
- `low`
  - data is stale, heavily incomplete, or conflicts with other signals

## Delay Heuristics

### Likely Port Delay

The port layer flags delay when:

- the latest port status is `waiting` and `waiting_days >= 2`
- or the port feed is stale while the shipment still appears to be in port operations

### Likely Inland Delay

The inland layer flags delay when:

- actual arrival is later than planned arrival
- or planned arrival has passed and actual arrival is still missing

### Stale Movement Record

Any port or inland summary with freshness label `stale` is treated as a degraded-trust signal.

### Missing Supporting Movement Signal

The system highlights missing support when:

- port discharge fields are incomplete during discharge-like states
- inland expected-arrival or departure milestones are absent for active inland moves
- discharge appears to have started but no inland movement feed is present yet

## Exception Compatibility

The current exception engine can consume these summaries without redesign:

- `shipment_stale_update`
  - can rely on the shared freshness/confidence helper now used by shipment visibility
- `inland_delay_risk`
  - can rely on the inland summary delay heuristic instead of maintaining a separate rule path

This keeps future exception refinement aligned with the movement-monitoring truth.

## Known MVP Limitations

- No AIS feed is used yet.
- No external transporter GPS feed is used yet.
- Port and inland summaries use the latest record, not a full event timeline model.
- No receipt-availability projection is applied yet for stock-cover timing.
- Delay heuristics are rule-based and intentionally conservative.

## Preparation For Later Stock-Cover Refinement

This layer prepares later refinement by exposing:

- whether material is still waiting at port
- whether discharge has started
- whether inland dispatch is confirmed
- whether inland movement is delayed
- how fresh and trustworthy those movement signals are

Later stock-cover versions can use these fields to weight pipeline confidence and receipt timing instead of counting all active shipments equally.
