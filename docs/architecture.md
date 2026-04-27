# Architecture Note

## Why this shape

This MVP is structured as a monorepo because the dashboard, API, contracts, and local infra need to evolve together while staying easy to run and easy to refactor.

- `apps/frontend`: the operator dashboard for plant, logistics, and control tower teams
- `apps/backend`: the source of truth for tenancy, inbound workflows, rules, and exception orchestration
- `packages/contracts`: shared frontend-facing DTOs and enums to keep dashboard code aligned with API response shapes
- `infra`: reserved for deeper deployment and environment automation beyond the initial Docker setup
- `docs`: operational notes, architecture decisions, and feature extension planning

## Backend modules

- `auth`: authentication boundaries and future identity provider integration
- `tenants`: tenant lifecycle, tenant scoping, and plant/company-level isolation
- `users`: user profile, role, and membership management
- `ingestion`: entry point for raw inbound signals such as AIS, email, ERP drops, portals, or CSV uploads
- `shipments`: purchase-order-linked shipment records, ETAs, vessel/truck/rail legs, and milestones
- `stock`: yard inventory, expected receipts, and stock position snapshots
- `rules`: configurable operational rules such as ETA drift thresholds, demurrage warnings, or documentation mismatches
- `exceptions`: generated alerts and work queues when inbound events violate rules
- `dashboard`: aggregated read models and KPI endpoints for the operator UI

## Multi-tenancy

Multi-tenancy exists from day one in three places:

- Request context carries a tenant identifier through the API layer
- Shared SQLAlchemy mixins enforce `tenant_id` on tenant-scoped tables
- Service and repository patterns are ready for tenant filtering to stay centralized
- `TenantMembership` links global users to tenant-scoped roles so the same identity can later belong to multiple tenants
- RBAC dependencies enforce role access at the endpoint boundary before business logic runs

This keeps future tenant isolation work incremental instead of requiring a rewrite later.

## Authentication and authorization

MVP authentication uses email/password and a signed bearer token. Password hashing and token creation are isolated in the `auth` module so an SSO provider can later replace login while preserving the same `CurrentUser`, membership, and tenant-context dependencies.

## Future ingestion plug-in points

AIS and email ingestion should plug into the `ingestion` module.

- AIS connector: poll or subscribe to vessel events, normalize them into ingestion events, and fan out shipment updates
- Email connector: parse supplier, broker, or carrier emails into structured events and route them through the same validation path
- File/EDI connector: import ERP exports, ASN files, or spreadsheets using the same normalized event contract

All of those sources should end up producing a common inbound event shape, after which `shipments`, `rules`, and `exceptions` can react consistently.
