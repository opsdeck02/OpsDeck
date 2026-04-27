# Shipment State Model

This document describes the MVP shipment visibility model used by the control tower dashboard.

## Supported Visible States

The dashboard exposes these derived shipment states:

- `planned`
- `on_water`
- `at_port`
- `discharging`
- `in_transit`
- `delivered`
- `cancelled`

These are derived from the existing shipment, shipment update, port event, and inland movement records. The database shipment enum remains the underlying source of truth.

## Existing Base Shipment States

The persisted shipment enum currently contains:

- `planned`
- `in_transit`
- `at_port`
- `discharging`
- `inland_transit`
- `delivered`
- `delayed`
- `cancelled`

The visibility layer maps those into the operator-facing state model instead of redesigning the schema.

## Precedence Rules

The MVP precedence order is:

1. If shipment base state is `cancelled`, visible state is `cancelled`
2. If shipment base state is `delivered`, visible state is `delivered`
3. If inland movement exists:
   - delivered/completed/arrived or actual arrival => `delivered`
   - cancelled => `cancelled`
   - otherwise => `in_transit`
4. Else if port event exists:
   - discharge started or berth status indicates unloading => `discharging`
   - waiting/berthed/anchored/arrived => `at_port`
5. Else fall back to shipment base state mapping:
   - `discharging` => `discharging`
   - `at_port` => `at_port`
   - `inland_transit` => `in_transit`
   - `in_transit` or `delayed` with vessel markers => `on_water`
   - `in_transit` or `delayed` without vessel markers => `in_transit`
   - otherwise => `planned`

## Fallback Behavior

When upstream data is incomplete:

- No port events means the model cannot refine a shipment into `at_port` or `discharging` from port evidence.
- No inland movements means post-discharge progress falls back to shipment base state.
- Vessel identifiers or vessel name make `in_transit` more likely to be interpreted as `on_water`.

This is intentionally deterministic and conservative for MVP V1.

## Latest Status Source

Latest status source is resolved with this priority:

1. inland movement
2. port event
3. shipment update source
4. shipment `source_of_truth`

## Confidence Rules

Shipment confidence is deterministic:

### High

- data updated within 48 hours
- ETA present
- supporting shipment update, port event, or inland movement exists

### Medium

- data updated within 7 days
- ETA present
- but supporting evidence is limited or aging

### Low

- ETA missing
- or data is stale
- or event-derived state conflicts with base shipment state

The detail API returns human-readable confidence reasons for the dashboard.

## Shipment Contribution Helper

To support later stock-cover refinement, the visibility layer classifies shipment usefulness:

- `on_water` => `low`
- `at_port` / `discharging` => `medium`
- `in_transit` => `high`
- `planned`, `delivered`, `cancelled` => `excluded`

The stock-cover engine does not fully consume these bands yet. They are included now so future pipeline weighting can evolve without reworking shipment visibility.

## Known MVP Limitations

- No AIS enrichment yet
- No email ingestion yet
- No partial discharge or quantity depletion logic yet
- No full inland milestone weighting yet
- Port and inland records influence visible state, but do not yet rewrite persisted shipment master state

## Later Integration

Later versions should:

- incorporate AIS-based marine truth for `on_water`
- use port event sequences to estimate partial availability
- use inland movement milestones to weight pipeline confidence
- feed shipment contribution bands into stock-cover pipeline calculations
- align exception generation with delayed or low-confidence shipments

