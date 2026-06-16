# OpsDeck Continuity Intelligence Monorepo

OpsDeck is a continuity intelligence layer for industrial operations. It turns inventory, inbound movement, supplier, planning, source freshness, and operational event signals into explainable continuity exposure: what is vulnerable, how soon disruption can emerge, why continuity is degrading, and how trustworthy the signal is.

This repository includes:

- `apps/frontend`: Next.js continuity intelligence interface
- `apps/backend`: FastAPI API and worker
- `packages/contracts`: shared TypeScript DTOs/contracts
- `infra`: local development and container setup
- `docs`: architecture notes

## Stack

- Frontend: Next.js, TypeScript, Tailwind CSS, shadcn/ui-style component layer
- Backend: FastAPI, SQLAlchemy, Alembic, Pydantic Settings
- Database: PostgreSQL
- Background jobs: Celery with Redis broker/result backend
- Tooling: Ruff, Pytest, ESLint, Prettier, pre-commit

## Quick Start

1. Copy environment files:

```bash
cp .env.example .env
cp apps/backend/.env.example apps/backend/.env
cp apps/frontend/.env.example apps/frontend/.env.local
```

2. Start the stack:

```bash
docker compose up --build
```

3. Open the apps:

- Frontend app: `http://localhost:3000/dashboard`
- Backend API docs: `http://localhost:8000/docs`
- Backend health: `http://localhost:8000/api/v1/health/live`

Seeded demo users are created by `apps/backend/scripts/seed_demo.py`.
Set `OPSDECK_DEMO_PASSWORD` and `OPSDECK_SUPERADMIN_PASSWORD` in your local
environment before seeding if you need known local credentials.

## Useful Commands

### Root

```bash
npm install
npm run lint
npm run format
pre-commit install
```

### Frontend

```bash
cd apps/frontend
npm install
npm run dev
```

### Backend

```bash
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
python scripts/seed_demo.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

## Database Migrations

```bash
cd apps/backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Continuity Signal Ingestion

OpsDeck keeps shipment, port, inland, supplier, and tracking infrastructure as supporting
signals for continuity reasoning. These feeds do not define the product; they provide evidence
for continuity exposure, visibility degradation, and operational dependency context.

The inbound visibility layer uses a pluggable tracking provider layer in
`apps/backend/app/modules/tracking/providers.py`. The default `mock` provider returns
deterministic port, ocean, rail, truck, and delivery milestones for a container/carrier pair,
so repeated local searches and links produce the same event timestamps.

The first real-provider adapter is `dcsa`, which calls a DCSA-style Track & Trace or aggregator
events endpoint and maps shipment, transport, and equipment event payloads into the shared tracking
event shape. Configure it with `TRACKING_DCSA_BASE_URL`, `TRACKING_DCSA_API_KEY`,
`TRACKING_DCSA_EVENTS_PATH`, `TRACKING_DCSA_TIMEOUT_SECONDS`, and
`TRACKING_DCSA_MAX_RETRIES`. Keep future provider-specific fetching/parsing behind the
`TrackingProvider` interface and selected through `get_tracking_provider`. Container validation,
carrier detection, event persistence, and inbound ETA/delay signal updates live in
`apps/backend/app/modules/tracking/service.py`.

Example search request:

```json
{"container_no":"MSCU1234567","carrier_code":"MSC","tracking_source":"dcsa"}
```

Example DCSA-like provider event:

```json
{
  "equipmentEventTypeCode": "LOAD",
  "eventDateTime": "2026-05-01T10:00:00Z",
  "eventLocation": {"locationName": "Nhava Sheva", "UNLocationCode": "INNSA"},
  "transportCall": {"vessel": {"name": "MV Horizon"}, "exportVoyageNumber": "042E"}
}
```

The main APIs are:

- `POST /api/v1/tracking/containers/search`: validates the container, detects or accepts the
  carrier/source, persists the selected carrier on the container, and returns continuity signals.
- `POST /api/v1/tracking/containers/link`: links the container to an inbound dependency, upserts
  tracking events, then updates ETA, delay, milestone, current location, and last source update
  timestamps used by continuity reasoning.
- `GET /api/v1/tracking/shipments`: provides inbound dependency selector options used by the UI.

## Signal Engine

The Phase 1 Signal Engine normalizes operational events, scores data confidence, classifies
freshness, calculates inventory and inbound continuity, detects deterministic rule-based
continuity risks, builds explainability payloads, reconstructs causal signal chains, maps
operational exposure, and records escalation snapshots. The goal is not shipment monitoring or
generic supply-chain visibility. The goal is to answer whether operations can continue without
disruption and whether the current visibility is trustworthy enough to believe.

## Repository Layout

```text
apps/
  backend/      FastAPI app, models, modules, worker, migrations
  frontend/     Next.js continuity intelligence interface
packages/
  contracts/    Shared TypeScript DTOs/types used by frontend
infra/          Container and local environment notes
docs/           Architecture notes
```

## Notes

- Multi-tenancy is built in from day one through tenant-aware request context, models, and repository primitives.
- The backend modules are intentionally separated so signal ingestion, continuity calculations, rules, exposure mapping, snapshots, and read facades can evolve independently.
- See `docs/architecture.md` for the architecture note and extension points for AIS/email ingestion.
- See `docs/erd.md` for the MVP V1 entity relationship diagram and database constraints.
