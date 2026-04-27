# SteelOps Control Tower Monorepo

Production-oriented MVP V1 monorepo for a steel-specific raw-material inbound control tower. This repository includes:

- `apps/frontend`: Next.js dashboard
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

- Frontend dashboard: `http://localhost:3000/dashboard`
- Backend API docs: `http://localhost:8000/docs`
- Backend health: `http://localhost:8000/api/v1/health/live`

Seeded demo login:

- `admin@demo.steelops.local`
- `logistics@demo.steelops.local`
- `planner@demo.steelops.local`
- `sponsor@demo.steelops.local`
- Password for all seeded users: `Password123!`

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

## Repository Layout

```text
apps/
  backend/      FastAPI app, models, modules, worker, migrations
  frontend/     Next.js dashboard
packages/
  contracts/    Shared TypeScript DTOs/types used by frontend
infra/          Container and local environment notes
docs/           Architecture notes
```

## Notes

- Multi-tenancy is built in from day one through tenant-aware request context, models, and repository primitives.
- The backend modules are intentionally separated so ingestion, stock, rules, exceptions, and dashboard logic can evolve independently.
- See `docs/architecture.md` for the architecture note and extension points for AIS/email ingestion.
- See `docs/erd.md` for the MVP V1 entity relationship diagram and database constraints.
