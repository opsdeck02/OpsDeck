# Local Run Instructions Without Docker

These instructions assume you are running PostgreSQL locally without Docker.

## 1. Start Local PostgreSQL

Create a local database and user however your machine manages PostgreSQL. One common setup is:

```bash
createdb steelops
```

Set the backend database URL:

```bash
export DATABASE_URL="postgresql+psycopg://localhost:5432/steelops"
```

If your local PostgreSQL requires a username/password, use:

```bash
export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@localhost:5432/steelops"
```

## 2. Install Backend Dependencies

```bash
cd apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## 3. Migrate The Database

From `apps/backend`:

```bash
alembic upgrade head
```

## 4. Seed Demo Data

From `apps/backend`:

```bash
python scripts/seed_demo.py
```

Seeded demo users:

- `admin@demo.steelops.local`
- `logistics@demo.steelops.local`
- `planner@demo.steelops.local`
- `sponsor@demo.steelops.local`

All seeded users use:

```text
Password123!
```

## 5. Start Backend

From `apps/backend`:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Useful URLs:

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health/live`

## 6. Install Frontend Dependencies

In a second terminal, from the repo root or `apps/frontend`:

```bash
cd apps/frontend
npm install
```

## 7. Start Frontend

From `apps/frontend`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
INTERNAL_API_BASE_URL=http://localhost:8000 \
npm run dev
```

Open:

```text
http://localhost:3000/login
```

## 8. Optional Verification

Backend:

```bash
cd apps/backend
source .venv/bin/activate
ruff check .
python -m pytest
```

Frontend:

```bash
cd apps/frontend
npm run lint
npm run build
```

Contracts:

```bash
cd packages/contracts
npm run lint
npm run build
```

