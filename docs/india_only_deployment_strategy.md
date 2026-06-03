# India-Only Deployment Strategy

## Purpose

SteelOps must be deployable for Indian industrial customers with a clear data-residency promise:
customer operational data should be hosted and backed up in India, without unnecessary movement to
non-India infrastructure.

This document explains the intended deployment structure for a cost-conscious solo-founder launch,
and gives future developers the boundaries they must preserve while building infrastructure,
integrations, observability, and data flows.

## Product Intent

SteelOps is not being deployed as a generic global SaaS first. The first serious production shape is
an India-resident SaaS deployment for Indian customers.

The priority order is:

1. Keep customer data in India.
2. Keep monthly infrastructure cost low.
3. Keep operations simple enough for a small team.
4. Preserve a clean upgrade path to stronger production infrastructure.
5. Avoid expensive platform complexity before revenue justifies it.

## Data Residency Promise

The intended customer-facing promise should be:

> Customer application data, database records, uploaded files, and backups are stored in India.

Do not promise that every cloud-provider control-plane event, billing record, DNS lookup, support
ticket, or identity-provider metadata never leaves India unless that has been legally and
contractually verified.

## Approved India Regions

Primary region:

- AWS Mumbai: `ap-south-1`

Future disaster recovery region:

- AWS Hyderabad: `ap-south-2`

Do not deploy production customer workloads, databases, object storage, backups, queues, logs, or
analytics pipelines outside these India regions.

## Phase 1 Deployment: Low-Cost Production

The first production deployment should use one India-hosted server and managed object storage.

```text
AWS Mumbai / ap-south-1
├── Single Lightsail or EC2 instance
│   ├── Docker Compose
│   ├── Reverse proxy: Caddy or Nginx
│   ├── Frontend: Next.js
│   ├── Backend: FastAPI
│   ├── Worker: Celery
│   ├── Redis
│   └── PostgreSQL
│
├── S3 bucket in ap-south-1
│   ├── encrypted database backups
│   ├── uploaded customer files
│   └── private access only
│
└── Minimal logging in ap-south-1
    ├── application logs
    ├── deployment logs
    └── short retention window
```

This is intentionally simple. Do not introduce Kubernetes, service mesh, multi-account networking,
Fargate, EKS, Kafka, or a managed data warehouse at this stage.

## Phase 1 Runtime Layout

Use Docker Compose on the production server:

```text
reverse-proxy
├── routes public HTTPS traffic
├── serves frontend requests
└── proxies API requests to backend

frontend
└── Next.js application

backend
└── FastAPI application

worker
└── Celery background jobs

postgres
└── primary application database

redis
└── Celery broker/cache
```

Recommended public routes:

```text
https://app.steelops.example.com        -> frontend
https://api.steelops.example.com        -> backend
https://api.steelops.example.com/docs   -> backend API docs, disabled or protected in production
```

## Cost Discipline

The initial infrastructure should be boring and cheap.

Expected starting components:

- One small Lightsail or EC2 instance in Mumbai.
- One encrypted S3 bucket in Mumbai.
- One domain.
- Optional low-cost email provider.
- No paid observability platform unless required.
- No global CDN by default.

Only move PostgreSQL to managed RDS after there is enough customer or revenue pressure to justify
the monthly cost.

## Upgrade Path

### Stage A: Founder Production

Use this until paying usage proves the need for more.

```text
Single Mumbai VM
├── app containers
├── PostgreSQL container or local PostgreSQL
├── Redis container
└── S3 Mumbai backups
```

### Stage B: Reliable Production

Move stateful services out of the app VM.

```text
AWS Mumbai / ap-south-1
├── EC2 app server
├── RDS PostgreSQL
├── ElastiCache Redis
├── S3 uploads and backups
├── CloudWatch logs
└── AWS Backup or scheduled encrypted backups
```

### Stage C: Enterprise-Ready India Deployment

Add controls required by larger customers.

```text
AWS Mumbai / ap-south-1
├── primary app and database
├── private networking
├── WAF
├── stronger IAM boundaries
├── audit logging
└── encrypted backups copied to AWS Hyderabad / ap-south-2
```

Hyderabad should be used only as an India-resident disaster recovery target unless a customer
specifically requires a more advanced active-active design.

## Data Storage Rules

Developers must follow these rules:

1. Store relational application data only in the production PostgreSQL database in India.
2. Store uploaded files only in an India-region object store.
3. Store database backups only in India-region storage.
4. Encrypt backups before or during upload.
5. Keep object buckets private by default.
6. Do not add public-read buckets for customer data.
7. Do not send customer data to third-party analytics, session replay, error tracking, or AI APIs
   without explicit approval and a data-residency review.
8. Do not log secrets, access tokens, uploaded file contents, full request payloads, or sensitive
   customer operational data.
9. Keep log retention short in the low-cost phase.

## Network And CDN Rules

Default production traffic should terminate in India-hosted infrastructure.

Avoid by default:

- Global CDN proxying.
- Global edge workers.
- Global object replication.
- Third-party session replay.
- Browser analytics that export user or customer data outside India.

If a CDN is later required for static assets, separate static public assets from customer data. Do
not serve customer uploads through a global CDN unless the residency impact is reviewed.

## Integration Rules

External integrations are the highest risk for data leaving India.

Before adding or enabling an integration, document:

- What data is sent.
- Which vendor receives it.
- Where the vendor stores or processes it.
- Whether the customer explicitly configured the integration.
- Whether the integration is optional.
- How it can be disabled.

Microsoft Graph, email ingestion, tracking APIs, analytics APIs, AI services, and notification
providers must not silently receive customer operational data.

For local demos, mock providers are acceptable. For production, integrations must be tenant-aware,
auditable, and explicitly configured.

## Secrets And Configuration

Production secrets must not be committed to the repository.

Minimum required secrets/configuration:

```text
DATABASE_URL
REDIS_URL
SECRET_KEY
JWT_SIGNING_KEY or equivalent
S3_BUCKET
S3_REGION=ap-south-1
AWS_ACCESS_KEY_ID or instance role
AWS_SECRET_ACCESS_KEY or instance role
BACKUP_ENCRYPTION_KEY or KMS configuration
NEXT_PUBLIC_API_BASE_URL
INTERNAL_API_BASE_URL
```

Prefer instance roles over long-lived AWS access keys once the deployment moves beyond the simplest
Lightsail setup.

## Backups

Phase 1 backup policy:

- Run scheduled PostgreSQL dumps.
- Encrypt each backup.
- Upload backups to an S3 bucket in `ap-south-1`.
- Keep daily backups for a short window, for example 7 to 14 days.
- Test restore before onboarding real customers.

Future policy:

- Add point-in-time recovery with RDS.
- Copy encrypted backups to `ap-south-2` for India-resident disaster recovery.
- Add restore drills before enterprise pilots.

## Observability

Keep observability useful but lean.

Phase 1:

- Container logs on the host.
- Basic uptime checks.
- Backend health endpoint.
- Disk, CPU, and memory monitoring.
- Short log retention.

Avoid:

- Expensive APM tools.
- Session replay.
- Full payload logging.
- Exporting logs to non-India systems.

## Production Hardening Checklist

Before the first real customer:

- HTTPS is enabled.
- Production secrets are outside git.
- Database is not publicly exposed.
- Redis is not publicly exposed.
- S3 bucket blocks public access.
- Backups run automatically.
- A backup restore has been tested.
- Admin users use strong passwords.
- Demo credentials are removed or isolated.
- API docs are protected or disabled.
- CORS allows only approved frontend domains.
- Logs do not contain sensitive payloads.
- Microsoft/demo sync jobs are disabled unless configured for that tenant.
- All production storage is in `ap-south-1`.

## Developer Guardrails

When adding new infrastructure or dependencies, ask:

1. Does this store or process customer data?
2. If yes, is it in India?
3. Is this necessary for the current stage?
4. Can it be deferred until revenue justifies it?
5. Can the feature run inside the existing Docker Compose setup?
6. Does it create a hidden recurring cost?
7. Does it make deployment harder for a solo founder?

Default answer for expensive infrastructure should be no until there is a clear customer or
reliability need.

## Near-Term Implementation Tasks

1. Create a production `docker-compose.yml` or `docker-compose.prod.yml`.
2. Add Caddy or Nginx reverse proxy configuration.
3. Add production environment variable templates.
4. Add a backup script for PostgreSQL to encrypted S3 Mumbai storage.
5. Add a restore runbook.
6. Add a deployment runbook for one Mumbai VM.
7. Add a production checklist to release workflow.
8. Disable or gate background demo sync jobs in production.
9. Add documentation for India-only data handling in customer-facing security material.

## Non-Goals For The First Deployment

- Kubernetes.
- Multi-region active-active.
- Data warehouse.
- Global CDN.
- Complex event streaming.
- Enterprise SIEM.
- Expensive APM.
- Automated autoscaling.
- Multi-cloud deployment.

These can be revisited after customer demand and revenue justify the cost.
