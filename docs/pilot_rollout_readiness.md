# Pilot Rollout Readiness

## What is ready in MVP

- Tenant-scoped onboarding uploads for shipment, stock, and threshold files
- Refined stock-cover risk view with weighted inbound protection
- Shipment visibility, movement monitoring, and freshness/confidence signals
- Exception detection, assignment, status updates, comments, and manual evaluation
- Executive dashboard for sponsor-facing pilot review
- CSV exports for stock-cover summary, exceptions, and executive dashboard sections
- Pilot admin checklist page for tenant readiness verification

## What is intentionally not included yet

- ERP integration
- AIS enrichment
- Email ingestion
- Notification delivery
- Predictive ETA or ML-based confidence
- Advanced SLA/escalation automation

## Role definitions

- `tenant_admin`: full tenant setup and pilot administration access
- `operator`: implemented through `logistics_user` and `planner_user`; can upload onboarding files and manage workflow actions
- `sponsor_viewer`: implemented through `sponsor_user`; read-only access to executive views and drill-down pages

## Export availability

- Stock-cover summary: CSV export from the executive dashboard
- Exception list: CSV export from the exceptions page with active filters applied
- Executive dashboard: CSV export of KPI, top-risk, exception, movement, and attention sections

## Pilot setup checklist

1. Create tenant users and verify each user can access only the intended tenant.
2. Upload shipment, stock, and threshold onboarding files.
3. Confirm ingestion history counts and fix rejected rows.
4. Review stock-cover results and verify warning/critical rows make sense.
5. Run manual exception evaluation.
6. Assign owners to live exceptions before customer operating reviews.
7. Review executive dashboard freshness and attention items.
8. Check the pilot admin page before weekly steering calls.

## Recommended go-live sequence for a 10-week pilot

1. Week 1: tenant setup, access verification, and onboarding templates shared with customer.
2. Weeks 2-3: first upload cycles, stock-cover validation, and shipment state review.
3. Weeks 4-5: exception workflow adoption with named owners.
4. Weeks 6-8: executive dashboard used in sponsor and steering meetings.
5. Weeks 9-10: confirm data freshness discipline, export usage, and success criteria review.

## Operational caveats

- Sponsors are intentionally read-only; workflow actions stay with operators and tenant admins.
- Manual exception evaluation is still on-demand in MVP, so teams should run it after major upload refreshes.
- Freshness labels are deterministic and should be used as operator trust cues, not predictive guarantees.
- CSV exports reflect the current tenant context and active filters only.
