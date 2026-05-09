# Phase 1 Signal Engine Closure Audit

Date: 2026-05-09

## Scope Reviewed

This audit covers the Phase 1 Signal Engine surface:

- Operational event normalization and metadata
- Inventory continuity and available cover
- Shipment continuity and inbound movement condition
- Rule-based risk candidates
- Deterministic risk explainability payloads
- Continuity timeline
- Operational relationship graph
- Exposure mapping
- Signal Engine read API
- Critical Risk Workspace frontend

Phase 1 remains a trust and explainability layer for industrial operations. This audit did not add Phase 2 workflows, actions, recommendations, simulations, orchestration, or AI/copilot behavior.

## Product Correctness

Phase 1 now provides a coherent backend-to-frontend Signal Engine path:

- Operational events carry confidence and freshness metadata.
- Inventory continuity produces usable quantity, available cover, and projected exhaustion.
- Shipment continuity produces deterministic inbound movement condition.
- Rule-based risks are deterministic candidates, not persisted lifecycle cases.
- Explainability payloads describe why a risk exists using structured rule reasons.
- Timeline entries reconstruct how relevant operational signals formed.
- Relationship graph returns a computed context read model, not a graph database.
- Exposure mapping translates continuity risks into operational exposure context.
- The Risk Workspace consumes the backend contract and uses operational language.

No Phase 1 Signal Engine module introduces AI summaries, optimization, simulation, recovery recommendations, action workflows, or exception-case lifecycle conversion.

## Naming And UX Consistency

Reviewed terms are consistent across the workspace and Signal Engine concepts:

- `confidence` is used for signal trustworthiness and completeness.
- `freshness` is used for recency and source update currency.
- `exposure` is used for operational exposure timing and basis.
- `available cover` is used in the frontend for inventory continuity.
- `inbound movement` is used in the frontend for shipment continuity.
- `operational context` is used for connected plant, material, shipment, supplier, signal, and risk records.

The Risk Workspace avoids visible technical labels such as `RiskCandidate`, `metadata`, `JSON`, `nodes`, `edges`, and graph-object language. Backend API types still use structured names such as nodes and edges because that is the read contract from Task 9, but the frontend renders them as connected operational records.

## Product Drift Review

The Signal Engine and Risk Workspace surfaces do not contain:

- AI/copilot language
- Recommendation copy
- Next-best-action language
- Workflow/action controls
- Simulation or optimization language
- Prediction-engine claims

There are legacy recommendation and exception workflow modules elsewhere in the existing product, especially around older stock cover services. They are outside the Phase 1 Signal Engine path and were not expanded by this phase.

One naming tension remains: `recommended_owner_role` exists on `RiskCandidate` because Task 6 requested owner role inference where safe. It is currently an ownership hint only, not an action recommendation or workflow.

## API Stability

The Signal Engine read facade is intentionally thin and tenant-scoped. Current routes are:

- `GET /api/v1/signal-engine/risks`
- `GET /api/v1/signal-engine/exposure`
- `GET /api/v1/signal-engine/timeline`
- `GET /api/v1/signal-engine/context-graph`
- `GET /api/v1/signal-engine/inventory-continuity`
- `GET /api/v1/signal-engine/shipment-continuity`
- `GET /api/v1/signal-engine/risk-workspace`

The risk workspace contract includes:

- `selected_risk`
- `explainability`
- `exposure`
- `timeline`
- `context_graph`
- `inventory_continuity`
- `shipment_continuity`
- `trust_summary`
- `empty`

Backend tests cover response shape, auth behavior, tenant isolation, filters, and deterministic workspace selection. Timeline is windowed with `timeline_limit` and `timeline_offset`.

API caveat: formal contract examples are covered by tests but not yet published as static API documentation. This is acceptable for Phase 1 closure, but should be added before external integration.

## Tenant Isolation

Tenant isolation is enforced through the existing `RequestContext` and tenant-scoped queries. Reviewed services consistently filter by `context.tenant_id` or verify tenant ownership for resolved plant, material, shipment, and operational event records.

Test coverage includes tenant isolation for:

- Operational events
- Inventory continuity
- Shipment continuity
- Rule-based risk candidates
- Timeline
- Relationship graph
- Exposure mapping
- Signal Engine API
- Risk workspace contract
- Demo scenarios

No cross-tenant data access issue was found during this audit.

## Low-Severity Healthy DOC Candidates

Current behavior: the raw rule engine and `/signal-engine/risks` endpoint can return low-severity `days_of_cover_breach` candidates when days of cover is above 10. This follows the Task 6 threshold mapping where DOC greater than 10 maps to `low`.

Impact:

- This preserves auditability and deterministic rule output.
- It can make a healthy operational context appear to have a low-severity candidate if the workspace is opened without severity filters.
- Demo validation treats medium, high, and critical as active material exposure, and uses filters when validating empty critical workspace behavior.

Closure decision: keep this behavior for Phase 1 to avoid changing risk semantics during closure. Before Phase 2 UI expansion, decide whether the default workspace/API view should filter to medium-or-higher candidates while leaving the raw risks endpoint complete.

## Frontend Workspace Review

The Risk Workspace uses operational section titles:

- Critical risk workspace
- Operational exposure context
- Why this is becoming risky
- Data trust
- How the risk formed
- Connected operational context
- Available cover
- Inbound movement condition

Empty state:

> No active continuity risk matches this view. OpsDeck will show risks here when inventory, inbound movement, or data freshness signals indicate operational exposure.

Error state:

> OpsDeck could not load the risk workspace. Your signal engine data may still be available in other views.

The workspace has loading, empty, unavailable/error, and populated states. It does not expose action controls, recommendations, simulation copy, or AI-generated narrative.

## Demo Readiness

Task 15 added deterministic operational validation scenarios:

- Healthy flow
- Cover collapse
- Delayed inbound
- Visibility degradation
- Missing operational context
- Deterministic fixed-time output comparison

These scenarios validate risk generation, explainability, exposure, timeline coherence, relationship graph coherence, trust summaries, and workspace serialization.

Bug fixed during QA before this closure audit:

- Relationship graph sparse-context scenarios could produce dangling edges when event or risk references existed without matching plant/material/shipment rows. The graph now creates reference nodes before connecting those edges.

No additional code bugs were found or fixed during Task 16.

## Remaining Phase 1 Weak Spots

These are non-blocking for closure, but should be visible before Phase 2:

- Low-severity healthy DOC candidates can appear in raw risk output and unfiltered workspace selection.
- Frontend has no dedicated Risk Workspace test suite; current assurance is through lint/build and backend contract tests.
- API response examples are test-backed but not separately documented for external consumers.
- Missing shipment context is best represented through OperationalEvent records because the core shipment table requires plant/material linkage.
- Risk list pagination is not implemented; only the workspace timeline is windowed.
- Phase 1 has not been load-tested against large operational event volumes.

## Closure Decision

Phase 1 Signal Engine is closed and operationally demo-ready.

The remaining issues are documented product/scale decisions rather than correctness blockers. Phase 2 can proceed without adding workflows, recommendations, simulations, or AI behavior to Phase 1 surfaces.
