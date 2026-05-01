FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/backend /app

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e .

EXPOSE 8000

CMD alembic upgrade head && if [ "$SEED_DEMO_ON_STARTUP" = "true" ]; then python scripts/seed_demo.py; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
