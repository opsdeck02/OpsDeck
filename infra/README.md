# Infra Notes

Local development uses `docker-compose.yml` at the repository root.

- PostgreSQL stores tenant, user, and operational domain data
- Redis backs Celery for asynchronous jobs
- FastAPI serves the backend API
- Next.js serves the dashboard frontend

For production, this folder can later hold deployment manifests, Terraform, Helm charts, or environment-specific overrides.

