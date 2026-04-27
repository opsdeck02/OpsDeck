#!/bin/bash

echo "Starting SteelOps..."

# Start backend
cd apps/backend
source .venv/bin/activate
alembic upgrade head >/dev/null

# Kill old backend if running
lsof -ti:8000 | xargs kill -9 2>/dev/null

uvicorn app.main:app --host 0.0.0.0 --port 8000 &

cd ../..

# Start frontend
cd apps/frontend

# Kill old frontend if running
lsof -ti:3000 | xargs kill -9 2>/dev/null

npm run dev &

cd ../..

echo "App running:"
echo "Frontend: http://localhost:3000"
echo "Backend: http://localhost:8000"

wait
