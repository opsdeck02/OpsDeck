# OpsDeck Complete Product Audit

Date: 2026-06-15  
Scope: complete product/code audit across backend modules, frontend pages, API endpoints, engines, upload flows, reports, dashboards, admin, demo seed, auth, and tests.  
Method: static code inspection plus test execution where available. Documentation was used as context only; working code and tests were treated as proof.

## Executive Verdict

OpsDeck is a real continuity-intelligence MVP, not a mock. It has a coherent backend domain model, authenticated tenant-scoped APIs, ingestion, workbook mapping, risk generation, explainability, stock/shipment continuity, supplier reliability context, production interruption impact, Past Incident Analysis, Microsoft/URL sync, executive reports, exception workflow, and a purpose-built demo scenario layer.

It is demo-ready for a controlled pilot-style walkthrough using seeded/demo data.

It is not yet customer-pilot-ready for messy plant data without hardening. The biggest issue is not that features are absent; it is that several features are strong enough to look authoritative while still relying on deterministic defaults, static consumption, incomplete supplier calibration, limited frontend test coverage, and two partly overlapping continuity views.

Final verdict: **Demo-ready with guardrails; not pilot-ready yet.**

Guardrails for demo:

- Use a demo-enabled tenant and seeded demo data.
- Say clearly that the risk engine is deterministic/rule-based, not predictive AI.
- Avoid presenting Microsoft/OneDrive sync as proven unless it has been tested against the customer tenant.
- Do not claim production-loss numbers are calibrated unless interruption config and dependency config are populated.
- Use the Risk Workspace, time-phased cover, inbound protection, executive continuity report, and Past Incident Analysis as the main story.

Verification status:

- Frontend lint: `npm run lint` in `apps/frontend` passed with no warnings/errors.
- Backend tests: `./.venv/bin/python -m pytest` in `apps/backend` passed: 494 passed, 86 warnings in 506.10 seconds. Warnings are deprecations from FastAPI `on_event` and pytest-asyncio event-loop policy usage.

## A. Full Feature Inventory Table

| Area | Feature | Backend | Frontend | Endpoints | Tests | Demo value | Pilot readiness |
|---|---|---|---|---|---|---|---|
| Auth | Login/session/refresh | `modules/auth`, `api/dependencies.py` | `login`, middleware, auth proxies | `/auth/*`, `/api/auth/*` | `test_auth_tenancy.py` | Medium | Partial |
| Tenant | Tenant context/RBAC | `api/dependencies.py`, `modules/tenants` | shell role nav, superadmin | `/tenants/*` | tenant/superadmin tests | Medium | Mostly ready |
| Upload | Upload Center | `modules/ingestion` | onboarding upload panel | `/ingestion/uploads` | `test_ingestion_uploads.py` | High | Partial |
| Upload | Workbook/sheet mapping | `modules/ingestion/service.py` | upload panel workbook UI | `/ingestion/workbook-*` | ingestion tests | High | Partial |
| Upload | Stock upload | ingestion + stock models | upload panel | `/ingestion/uploads` | ingestion/stock tests | High | Partial |
| Upload | Shipment upload | ingestion + shipment models | upload panel | `/ingestion/uploads` | ingestion/shipment tests | High | Partial |
| Upload | Threshold/consumption upload | ingestion + threshold models | upload panel | `/ingestion/uploads` | threshold tests | High | Partial |
| Upload | Import history/rollback/reprocess | ingestion service | upload panel history | `/ingestion/jobs/*` | ingestion tests | Medium | Partial |
| Sync | Generic URL sync | `tenants/sync_service.py` | onboarding data-source UI | `/tenants/data-sources/*` | data-source tests | Medium | Partial |
| Sync | Microsoft/OneDrive sync | `modules/microsoft`, worker scheduler | Microsoft onboarding page | `/microsoft/*` | `test_microsoft_integration.py` | Medium | Partial |
| Events | Operational events | `modules/operational_events` | surfaced in timeline/workspace | indirect | event tests | High | Partial |
| Trust | Confidence/freshness | `operational_events`, `shipments`, `trust` | badges/reasons | indirect | confidence tests | High | Partial |
| Continuity | Inventory continuity | `stock/continuity.py` | Risk Workspace | `/signal-engine/inventory-continuity` | inventory tests | Very high | Partial |
| Continuity | Shipment continuity | `shipments/continuity.py` | Risk Workspace/shipments | `/signal-engine/shipment-continuity` | shipment tests | Very high | Partial |
| Continuity | Time-phased cover | `stock/time_phased_cover.py` | workspace/detail/report | `/stock/.../time-phased` | time-phased tests | Very high | Partial |
| Continuity | Stock cover detail | `stock/service.py` | stock-cover detail page | `/stock/cover/*` | stock-cover tests | High | Partial |
| Risk | Rule engine | `rules/engine.py` | Risk Workspace | `/signal-engine/risks` | rule tests | Very high | Partial |
| Risk | Risk Workspace | `signal_engine/service.py` | risk-workspace page | `/signal-engine/risk-workspace` | signal tests | Very high | Demo-ready |
| Risk | Material rollups | `signal_engine/service.py` | risk selector | `/signal-engine/material-rollups` | signal tests | Very high | Partial |
| Risk | Exposure/timeline/graph | exposure, timeline, relationships | Risk Workspace panels | `/signal-engine/exposure`, `/timeline`, `/context-graph` | exposure/timeline/graph tests | High | Partial |
| Supplier | Supplier master/linking | `suppliers/service.py` | suppliers pages | `/suppliers/*` | supplier tests | Medium | Partial |
| Supplier | Supplier reliability | `suppliers/reliability_context.py` | workspace/suppliers | indirect | reliability tests | High | Partial |
| ETA | ETA behavior | `shipments/visibility_confidence.py` | workspace/shipments | indirect | visibility tests | High | Partial |
| Inbound | Inbound protection quality | `visibility_confidence`, stock continuity | workspace | indirect | inbound protection tests | Very high | Partial |
| Tracking | Container/vessel tracking | `tracking/*`, `shipments/movement.py` | port-inland/movements pages | `/tracking/*`, `/shipments/*monitoring` | tracking/movement tests | Medium | Partial |
| Exceptions | Exception workflow | `exceptions/service.py` | exceptions pages | `/exceptions/*` | exception tests | High | Partial |
| Reports | Daily continuity brief | `reports/service.py`, `pdf.py` | daily brief button | `/reports/daily-continuity-brief` | daily brief tests | High | Partial |
| Reports | Executive continuity report | `reports/service.py` | admin executive report page | `/reports/executive-continuity` | report tests via dashboard/report tests | Very high | Partial |
| Validation | Past Incident Analysis | `line_stops/service.py` | admin Past Incident Analysis | `/line-stops/historical-validation` | Past Incident Analysis tests | High | Partial |
| Admin | Operational configuration | `impact/router.py` | admin operational config pages | `/impact/*` | impact/config tests | High | Partial |
| Admin | Notification settings | `notifications/*` | admin notifications | `/notifications/*` | notification tests | Medium | Partial |
| Admin | Users | `users/*` | users/admin pages | `/users/*` | auth/superadmin tests | Medium | Partial |
| Demo | Seed data and scenarios | `scripts/seed_demo.py`, `pilot_scenarios.py` | scenario controls | scenario query on risk workspace | demo scenario tests | Very high | Demo-only |
| Dashboard | Executive dashboard | `dashboard/service.py` | dashboard page | `/dashboard/executive` | executive dashboard tests | High | Partial |

## B. Backend Endpoint Inventory

Base prefix: `/api/v1`.

| Module | Endpoints |
|---|---|
| Health | `GET /health/live`, `GET /health/ready` |
| Auth | `GET /auth/me`, `POST /auth/login`, `POST /auth/refresh` |
| Tenants | `GET /tenants`, `POST /tenants/plants`, `GET /tenants/plan`, `GET/POST/PUT/DELETE /tenants/data-sources`, `POST /tenants/data-sources/{source_id}/sync`, superadmin `/tenants/admin/*` |
| Ingestion | `GET /ingestion/sources`, `POST /ingestion/uploads`, `POST /ingestion/workbook-upload`, `POST /ingestion/url-upload`, `GET /ingestion/jobs`, `GET/POST /ingestion/jobs/{job_id}`, rollback/reprocess, `DELETE /ingestion/uploads`, mapping previews, templates |
| Microsoft | `GET /microsoft/auth-url`, callback, connections, file browsing, sheet names, mapping preview, Microsoft data sources CRUD/sync |
| Shipments | `GET /shipments`, `GET /shipments/visibility`, port/inland monitoring, movement/detail, `POST /shipments/sync`, navigation preview |
| Stock | `GET /stock/cover`, export, detail, time-phased detail, action update |
| Suppliers | supplier list/create/detail/update/delete, link shipments, performance summary |
| Signal engine | evaluate escalation, risk workspace, rollups, risks, exposure, timeline, context graph, inventory continuity, shipment continuity |
| Rules | `GET /rules` |
| Tracking | carrier detection, container search, shipment options, vessel position, link container |
| Exceptions | list, export, detail, evaluate, owner/status/action, comments |
| Dashboard | snapshot, executive, executive export, pilot readiness |
| Impact/admin | interruption config, continuity thresholds, shipment inbound trust, configuration validation, production lines, process/product dependencies, material/process dependencies |
| Line stops | list/create incidents, Past Incident Analysis |
| Reports | daily continuity brief PDF, executive continuity report |
| Notifications | settings, test digest, test critical alert |
| Users | tenant users and admin tenant-user reads |

## C. Frontend Page Inventory

| Page | Purpose | Backend data used | Notes |
|---|---|---|---|
| `/login` | Login | `/auth/login` through proxy | Cookie/session flow exists. |
| `/dashboard` | Main continuity dashboard | current user, executive/dashboard APIs | Strong demo page if data exists. |
| `/dashboard/risk-workspace` | Material/risk deep dive | signal-engine APIs, reports button | Strongest product surface. |
| `/dashboard/shipments` | Inbound continuity list | shipment visibility | Useful but less differentiated than Risk Workspace. |
| `/dashboard/shipments/[shipmentId]` | Shipment detail/movement | shipment detail/movement | Good operational context. |
| `/dashboard/movements` | Signal trust/movement monitoring | port/inland monitoring | Label may confuse users. |
| `/dashboard/port-inland` | Port/inland and vessel map | tracking/vessel/movement data | Tracking providers are partly mock/pluggable. |
| `/dashboard/suppliers` | Supplier reliability sources | suppliers/performance | Good but depends on linking/history. |
| `/dashboard/suppliers/[supplierId]` | Supplier detail | supplier detail | Useful for reliability evidence. |
| `/dashboard/onboarding` | Upload/source health | tenant plan, Microsoft data sources, ingestion | “Source health” label hides upload center. |
| `/dashboard/onboarding/microsoft` | Microsoft 365 sync setup | Microsoft APIs | Plan-gated. |
| `/dashboard/exceptions` | Exception queue | exceptions APIs | Strong workflow story. |
| `/dashboard/exceptions/[exceptionId]` | Exception detail/actions/comments | exceptions APIs | Good for operators. |
| `/dashboard/stock-cover/[plantId]/[materialId]` | Stock cover detail | stock cover APIs | Useful but overlaps Risk Workspace. |
| `/dashboard/admin` | Admin landing | role/current user | Tenant admin only. |
| `/dashboard/admin/operational-configuration` | Config selection/summary | impact/admin APIs | Important for pilot setup. |
| `/dashboard/admin/operational-configuration/continuity-thresholds` | Threshold config | `/impact/continuity-thresholds` | Pilot-critical. |
| `/dashboard/admin/operational-configuration/interruption-impact` | Interruption economics | `/impact/interruption-config` | Calibration-heavy. |
| `/dashboard/admin/operational-configuration/shipment-inbound-trust` | Inbound trust config | `/impact/shipment-inbound-trust` | Strong concept. |
| `/dashboard/admin/operational-configuration/product-process-dependency` | Process/product dependencies | `/impact/*dependencies` | Strong but configuration burden. |
| `/dashboard/admin/past-incident-analysis` | Past Incident Analysis / Incident Replay | line-stop validation | Good demo, not rigorous backtesting yet. |
| `/dashboard/admin/executive-continuity-report` | Executive report | reports API | Strong demo. |
| `/dashboard/admin/notifications` | Notification config/tests | notifications APIs | Useful but operational reliability unknown. |
| `/dashboard/users` | Tenant user admin | users API | Admin feature. |
| `/dashboard/pilot-admin` | Pilot/admin controls | current user/admin APIs | Support feature. |
| `/dashboard/superadmin` | Global tenant admin | tenant admin APIs | Internal ops feature. |

## D. Current Demo Story Map

1. Login as demo admin/sponsor.
2. Show Dashboard: continuity KPIs, risks, movements, supplier summary, freshness.
3. Open Risk Workspace: select a material at risk or use pilot scenario controls.
4. Explain the risk: material, plant, days of cover, severity, primary drivers.
5. Show inbound protection: physical inbound versus trusted inbound versus uncertain inbound.
6. Show time-phased cover: when warning/reserve/critical/interruption dates occur, and which shipment protects or fails to protect continuity.
7. Show operational trust/calibration: what assumptions are missing and whether the assessment is trustworthy.
8. Show recommended human actions: expedite, validate, replan, refresh signals.
9. Show supplier reliability source page: how supplier history modifies trust.
10. Show exception workflow: assign owner, action status, comments, system-controlled resolution.
11. Show Past Incident Analysis: prior line-stop replay and lead-time evidence.
12. Show executive continuity report: management-readable material risks and actions.
13. End with admin configuration: thresholds, inbound trust, interruption economics, process dependencies.

## E. Gaps Before Customer Pilot

1. Frontend automated test coverage is missing for the real pilot journey.
2. Risk/cover logic is split between stock-cover service and signal-engine continuity, creating possible message drift.
3. Consumption is static and not tied to production schedules, shutdowns, campaigns, or forecast changes.
4. Supplier reliability needs stronger onboarding, matching, and confidence communication.
5. Microsoft/OneDrive integration needs live-tenant validation, better operational error recovery, and clearer sync ownership.
6. Historical validation is a useful replay, not statistically rigorous model validation.
7. Production impact numbers can look precise while being config-dependent and often uncalibrated.
8. Demo scenario reads can mutate demo data, which is acceptable for demo but risky as a pattern.
9. Broad upload-data deletion is operator-accessible and should likely be admin-only or heavily confirmed.
10. Notifications need end-to-end deliverability and escalation policy validation.
11. Report/PDF layout and export reliability should be tested against large/messy datasets.
12. Tenant switching and cookie behavior should be explicitly tested across local/production cookie names.

## F. Top 10 Fixes To Prioritize

1. Add Playwright smoke tests for login, upload, Risk Workspace, report generation, admin config, and exception workflow.
2. Unify stock-cover and signal-engine continuity rules or clearly label them as separate views.
3. Restrict destructive upload clearing to tenant admin and add confirmation/audit copy.
4. Add ETA horizon and arrival-window rules to inbound protection so late inbound cannot imply operational safety.
5. Improve supplier matching and supplier master onboarding during shipment upload.
6. Add production schedule/consumption-plan support, even as a simple daily planned consumption override.
7. Make demo scenarios non-mutating or clearly sandboxed/resettable from UI.
8. Harden Microsoft/Graph sync with integration checks, retry/backoff visibility, and per-source sync audit trails.
9. Add calibration labels beside every impact value and trusted-cover value in the UI.
10. Add frontend-visible “why this may be wrong” sections for low-trust or insufficient-config risks.

## G. Top 10 Strongest Demo Features

1. Risk Workspace material deep dive.
2. Physical inbound versus trusted inbound protection.
3. Time-phased cover and shipment protection evaluation.
4. Executive continuity report.
5. Historical validation replay.
6. Configuration validation/trust assessment.
7. Production interruption impact when configured.
8. Exception workflow with owner/action/comments.
9. Workbook upload with mapping preview.
10. Supplier reliability context and reliability-source table.

## H. Feature-By-Feature Audit

### 1. Upload Center

1. Feature name: Upload Center / Source Health.
2. Where it exists in the code:
   - Backend files: `apps/backend/app/modules/ingestion/router.py`, `service.py`, `schemas.py`, `templates.py`.
   - Frontend files: `apps/frontend/app/dashboard/onboarding/page.tsx`, `components/onboarding/upload-panel.tsx`.
   - API endpoints: `/api/v1/ingestion/uploads`, `/workbook-upload`, `/url-upload`, `/jobs`, `/mapping-preview`, `/templates/{file_type}` plus Next proxies under `apps/frontend/app/api/ingestion/*`.
   - Tests: `test_ingestion_uploads.py`, `test_data_source_sync.py`, `test_data_source_scheduler.py`.
3. What the feature is supposed to do: let plant/admin users load stock, inbound, threshold, and workbook data into OpsDeck.
4. How it currently works: files are previewed, mapped, parsed, validated, persisted, and tracked as ingestion jobs with accepted/rejected row counts.
5. What data it uses: CSV/XLSX/XLSM files, workbook sheets, mapping overrides, tenant/user context, uploaded file metadata.
6. Logic/rules/engines involved: header alias matching, required-field validation, demo-prefix guard, upsert logic, operational event emission, cache invalidation.
7. Signals/outputs: ingestion job status, validation errors, created/updated/unchanged counts, operational summary, upload warnings.
8. UI: upload mode selector, file type selector, mapping preview, workbook sheet config, history, rollback/reprocess controls.
9. Plant value: gets messy ERP/logistics/planning files into a continuity model quickly.
10. Working correctly: strong backend pipeline, validation, audit logging, partial failure reporting, test coverage.
11. Incomplete/weak/risky: “Source health” label hides the upload center; clear uploaded data is broad; rollback does not restore updated records.
12. Bugs/edge cases: updated records are preserved on rollback; workbook sheet order can affect consumption sheets that expect matching stock snapshots; public URL fetches can fail on permissions.
13. Missing tests: frontend upload UX, large file behavior, ugly workbook formats, rollback UI, concurrent uploads.
14. Suggested improvements: rename to Upload Center, add safer clear-data permissions, add “updated records not rolled back” copy, add E2E tests.
15. Demo value: strong enough to show, especially workbook mapping.

### 2. Workbook / Sheet Mapping

1. Feature name: Workbook/sheet mapping.
2. Where it exists:
   - Backend: `ingestion/service.py` functions `preview_workbook_mapping`, `process_workbook_upload`, sheet config helpers.
   - Frontend: `upload-panel.tsx`.
   - API: `/api/v1/ingestion/workbook-preview`, `/workbook-upload`.
   - Tests: ingestion upload tests.
3. Supposed to do: detect workbook sheets, infer each sheet type, map columns, and ingest multiple operational feeds from one workbook.
4. Current behavior: scans non-empty sheets, suggests file type by name/header score, generates per-type mapping previews, ignores hidden/ignored sheets, processes configured sheets.
5. Data used: sheet names, first rows, mapped headers, rows, sheet configs.
6. Logic involved: header scoring, sheet type keywords, required fields per file type, row normalization.
7. Outputs: per-sheet status, ignored sheet list, validation errors, aggregate operational summary.
8. UI: workbook preview and per-sheet selectors/mapping overrides.
9. Plant value: many plants maintain one workbook with stock/inbound/threshold tabs.
10. Working: multi-sheet processing is real and tested.
11. Weak/risky: sheet inference is heuristic; hidden sheets default ignored; consumption sheets require existing matching stock snapshot.
12. Edge cases: duplicate sheet names impossible in Excel but duplicate headers are possible; header row detection only scans first 10 rows.
13. Missing tests: messy merged-cell sheets, multi-header sheets, very large workbooks, frontend sheet override flows.
14. Improvements: show confidence for sheet inference, allow “dry run all sheets”, better duplicate header warnings.
15. Demo value: high.

### 3. Stock Upload

1. Feature name: Stock upload.
2. Where it exists:
   - Backend: `ingestion/service.py` `upsert_stock_snapshot`, stock models.
   - Frontend: upload panel.
   - API: `/ingestion/uploads` with `file_type=stock`.
   - Tests: ingestion, stock-cover, inventory continuity.
3. Supposed to do: load latest stock, quality hold, available stock, and daily consumption by plant/material.
4. Current behavior: resolves/creates plant and material, finds same snapshot time or latest snapshot, creates/updates snapshot, emits inventory stock event.
5. Data: plant/material code, on-hand, quality-held, available-to-consume, daily consumption, snapshot time.
6. Logic: required fields, decimal/date parsing, latest snapshot selection, operational event confidence/freshness downstream.
7. Outputs: stock snapshots, inventory events, cover calculations.
8. UI: upload result and downstream dashboard/workspace/stock cover.
9. Plant value: base input for days-of-cover and line-risk reasoning.
10. Working: core ingestion and calculations are well covered.
11. Weak/risky: static daily consumption; no production schedule; updating “latest” snapshot when exact timestamp absent may surprise users.
12. Edge cases: negative/impossible stock combinations, stale snapshot trust, duplicate records with different times.
13. Missing tests: frontend upload behavior, large historical stock series, invalid physical stock arithmetic.
14. Improvements: add planned consumption feed and physical plausibility warnings.
15. Demo value: high.

### 4. Shipment Upload

1. Feature name: Shipment upload.
2. Where it exists:
   - Backend: `ingestion/service.py` `upsert_shipment`, `shipments/*`.
   - Frontend: upload panel.
   - API: `/ingestion/uploads` with `file_type=shipment`.
   - Tests: ingestion, shipment visibility/continuity.
3. Supposed to do: load inbound shipments and ETA/status evidence.
4. Current behavior: resolves plant/material, creates supplier from upload, parses ETA/state/source, creates/updates shipment and update events.
5. Data: shipment id, supplier, quantity, plant/material, planned/current/latest ETA, state, ports/vessel markers, source.
6. Logic: state parsing, ETA parsing, supplier auto-create, shipment update event emission, visibility confidence downstream.
7. Outputs: shipment records, shipment updates, operational events, risk candidates.
8. UI: upload result, shipments page, Risk Workspace inbound panels.
9. Plant value: connects inbound supply to cover and continuity risk.
10. Working: core upload, state derivation, ETA behavior have tests.
11. Weak/risky: supplier auto-create can create uncalibrated reliability sources; PO is recognized in aliases but not strongly modeled.
12. Edge cases: current/planned/latest ETA semantics can be confusing; delivered/cancelled handling differs by view.
13. Missing tests: frontend mapping, duplicate shipment updates, real-world status vocabulary.
14. Improvements: stronger PO/order linkage, supplier match review, ETA field definitions in UI.
15. Demo value: high.

### 5. Threshold Upload and Continuity Thresholds

1. Feature name: Threshold upload / continuity thresholds.
2. Where:
   - Backend: `ingestion/service.py` `upsert_threshold`, `impact/router.py`, threshold model.
   - Frontend: upload panel, admin continuity thresholds page/form.
   - API: `/ingestion/uploads`, `/impact/continuity-thresholds`.
   - Tests: threshold admin/consumption tests.
3. Supposed to do: define warning, critical, reserve, and stockout horizon thresholds by plant/material.
4. Current behavior: upload/admin upsert threshold rows and invalidate signal cache.
5. Data: warning days, critical days, reserve quantities/days, quality hold quantity, stockout alert horizon.
6. Logic: warning must be >= critical on upload; validation flags contradictory settings.
7. Outputs: severity rules, time-phased cover thresholds, configuration readiness findings.
8. UI: upload mapping and admin form.
9. Plant value: makes risk bands plant/material-specific.
10. Working: backend CRUD and validation covered.
11. Weak/risky: admin endpoint should enforce warning >= critical too; threshold meaning may vary by plant.
12. Edge cases: missing thresholds fall back to defaults, which can appear authoritative.
13. Missing tests: frontend form validation, edge values, full E2E from threshold edit to changed risk.
14. Improvements: always display whether defaults or configured thresholds are used.
15. Demo value: high.

### 6. Supplier Master and Linking

1. Feature name: Supplier master/linking.
2. Where:
   - Backend: `suppliers/router.py`, `service.py`, `reliability_context.py`.
   - Frontend: suppliers pages, supplier controls.
   - API: `/suppliers/*`.
   - Tests: `test_suppliers.py`, `test_supplier_reliability_context.py`.
3. Supposed to do: manage supplier records and link shipment supplier names to supplier master data.
4. Current behavior: tenant admins create/update/deactivate suppliers; link-by-name updates shipments; uploads can auto-create supplier records.
5. Data: supplier name/code/ports/material categories/origin/contact, linked shipments.
6. Logic: reliability grades from shipment history, on-time ETA behavior, risk signal percentage, sample-size calibration.
7. Outputs: supplier performance, reliability grade/status, reliability modifier used in trusted inbound.
8. UI: supplier table, detail page, create/update controls.
9. Plant value: distinguishes credible inbound from weak supplier evidence.
10. Working: CRUD, linking, reliability logic tested.
11. Weak/risky: link-by-exact-name is brittle; sample sizes often too small; auto-created suppliers may be treated as master records.
12. Edge cases: supplier rename, aliases, duplicate vendor names, unlinked historical shipments.
13. Missing tests: frontend supplier management, fuzzy matching review, supplier alias workflows.
14. Improvements: add supplier alias table, review queue, “uncalibrated” warnings in Risk Workspace.
15. Demo value: medium-high if seeded history exists.

### 7. OneDrive / Microsoft Sync

1. Feature name: Microsoft 365 / OneDrive / SharePoint sync.
2. Where:
   - Backend: `microsoft/router.py`, `service.py`, `workers/tasks/token_refresh.py`, scheduler.
   - Frontend: `dashboard/onboarding/microsoft/page.tsx`, `MicrosoftFilePicker`.
   - API: `/microsoft/*`.
   - Tests: `test_microsoft_integration.py`.
3. Supposed to do: connect Microsoft Graph, browse files, preview mappings, save data sources, and sync files on schedule.
4. Current behavior: OAuth stores encrypted tokens, refreshes tokens, downloads files, optionally activates selected sheet, processes through ingestion.
5. Data: Graph tokens, connection, drive/item/site ids, mapping, sheet name, file content.
6. Logic: token refresh, Graph file search, content download, sheet activation, ingestion reuse.
7. Outputs: Microsoft data source status, last sync timestamps/errors, ingested rows.
8. UI: connect account, select file, configure type/sheet/frequency/mapping.
9. Plant value: reduces manual file uploads for plants using OneDrive/SharePoint.
10. Working: code path and tests exist.
11. Weak/risky: live Graph behavior/permissions are hard to guarantee; scheduled sync uses background user/context; error details may be too technical.
12. Edge cases: expired consent, large files, moved/deleted files, protected tenant policies, workbook sheet changes.
13. Missing tests: live integration, UI E2E, token refresh worker E2E, permission revocation.
14. Improvements: add source health diagnostics, retry/backoff UI, last successful imported file hash, sync audit actor.
15. Demo value: medium unless tested live beforehand.

### 8. Operational Events

1. Feature name: Operational events.
2. Where:
   - Backend: `operational_events/service.py`, `confidence.py`, `freshness.py`, `timeline.py`, model.
   - Frontend: Risk Workspace timeline and explainability.
   - API: no standalone public CRUD router; events are emitted by ingestion and tracking flows.
   - Tests: event confidence, timeline, signal engine tests.
3. Supposed to do: preserve operational signal history for explanation, trust, and timelines.
4. Current behavior: stock and shipment updates emit typed events with source, confidence, freshness, context, values.
5. Data: event type/category/source, occurred/detected time, plant/material/shipment/supplier references, previous/new values.
6. Logic: source reliability, freshness thresholds by source type, completeness validation.
7. Outputs: event confidence, freshness, timeline entries, risk explainability signals.
8. UI: timeline and contributing signals inside Risk Workspace.
9. Plant value: shows why OpsDeck changed its view.
10. Working: good foundational layer and tests.
11. Weak/risky: not all admin/config changes emit equivalent operational events; event volume/retention not addressed.
12. Edge cases: backdated uploads, source clock skew, duplicate events.
13. Missing tests: retention/performance, UI timeline pagination behavior.
14. Improvements: add event browser and source lineage filters.
15. Demo value: high as part of Risk Workspace.

### 9. Confidence and Freshness Logic

1. Feature name: Confidence/freshness logic.
2. Where:
   - Backend: `operational_events/confidence.py`, `freshness.py`, `shipments/confidence.py`, `visibility_confidence.py`, `trust/operational.py`.
   - Frontend: badges and reasons across workspace, movement, shipment pages.
   - API: indirect through signal/shipment/dashboard APIs.
   - Tests: confidence/freshness/trust tests.
3. Supposed to do: tell users whether a signal is believable and current.
4. Current behavior: scores sources by reliability, freshness, completeness, validation; shipment confidence uses ETA/supporting events/conflicts.
5. Data: timestamps, source type, fields present, conflicts, movement events.
6. Logic: deterministic thresholds and penalties.
7. Outputs: confidence score/band, freshness label, trust warnings/reasons.
8. UI: confidence badges, warning text, trust summary.
9. Plant value: prevents false safety from stale data.
10. Working: conceptually strong and tested.
11. Weak/risky: thresholds are generic; “fresh/delayed/stale/critical” varies by context; numeric confidence can look more scientific than it is.
12. Edge cases: timezone mismatch, slow but normal reporting cadence, stale stable ocean shipments.
13. Missing tests: customer-specific cadence configuration E2E.
14. Improvements: always show expected cadence and why a signal is stale.
15. Demo value: high.

### 10. Inventory Continuity

1. Feature name: Inventory continuity.
2. Where: `stock/continuity.py`, `stock/schemas.py`, signal engine service.
3. Frontend/API/tests: Risk Workspace; `/signal-engine/inventory-continuity`; `test_inventory_continuity.py`.
4. Supposed to do: calculate whether usable inventory can sustain production.
5. Current behavior: usable = on-hand minus reserved/blocked/quality-hold; days cover = usable/daily consumption; trusted cover includes confidence-adjusted inbound.
6. Data: latest stock snapshot, thresholds, inbound shipments, trust config, supplier reliability.
7. Logic: trusted inbound quantities, visibility confidence, supplier reliability modifier, time-phased cover.
8. Outputs: usable stock, physical/trusted/uncertain inbound, days cover, exhaustion date, trust warnings.
9. UI: Risk Workspace inventory panel and executive report.
10. Working: strong deterministic calculation with explanation.
11. Weak/risky: static consumption; no production plan, stockyard location, grade blending, or planned shutdown.
12. Edge cases: zero/negative consumption, negative usable stock, late inbound counted as trusted in some aggregate contexts.
13. Missing tests: production-plan variants, multi-location stock, UI E2E.
14. Improvements: add planned consumption schedule and stricter ETA horizon checks.
15. Demo value: very high.

### 11. Shipment Continuity and ETA Behavior

1. Feature name: Shipment continuity / ETA behavior.
2. Where: `shipments/service.py`, `continuity.py`, `visibility_confidence.py`, `movement.py`.
3. API/UI/tests: `/shipments/*`, `/signal-engine/shipment-continuity`, shipment pages, movement pages, shipment/visibility tests.
4. Supposed to do: decide whether inbound movement protects plant continuity.
5. Current behavior: derives shipment state from shipment master plus port/inland events; flags ETA slip, stale tracking, missing milestones/context, overdue delivery.
6. Data: current/planned/latest ETA, tracking timestamps, vessel/port/inland fields, plant/material links.
7. Logic: ETA slip, freshness by source type, visibility profile/cadence, ETA drift tolerance, abnormal behavior penalty.
8. Outputs: shipment status, ETA slip, missing/overdue milestones, trust/protection labels.
9. UI: shipment list/detail, Risk Workspace shipment continuity.
10. Working: good logic and tests.
11. Weak/risky: ETA semantics may confuse users; source-of-truth hierarchy is simple; `/shipments/sync` is only a stub.
12. Edge cases: early ETA improvements, delivered state with stale tracking, no PO context always producing missing context.
13. Missing tests: frontend detail pages, real status vocabulary.
14. Improvements: model PO/order and carrier legs explicitly; either implement or hide `/shipments/sync`.
15. Demo value: high.

### 12. Risk Engine

1. Feature name: Risk engine.
2. Where: `rules/engine.py`, `rules/inbound_delay_cover.py`, `signal_engine/service.py`.
3. API/UI/tests: `/signal-engine/risks`, `/risk-workspace`; rule/signal tests.
4. Supposed to do: produce deterministic continuity risk candidates.
5. Current behavior: evaluates inventory, shipment, inbound delay, event trust, and missing context rules.
6. Data: inventory continuity, shipment continuity, operational events, thresholds.
7. Logic: days cover breach, projected stockout horizon, protected reserve, shipment degraded/watch, inbound delay against cover, stale/low confidence signal.
8. Outputs: `RiskCandidate` with severity, reasons, owner role, explainability, escalation, impact, recommendations, trust.
9. UI: Risk Workspace and material rollups.
10. Working: broad, explainable, tested.
11. Weak/risky: deterministic rules can look predictive; some default thresholds/fallbacks are generic.
12. Edge cases: duplicate candidates for same material, stale low-confidence signals over-weighting noise.
13. Missing tests: frontend risk selection; large tenant performance.
14. Improvements: dedupe/cluster risks more visibly; add rule version and threshold provenance to UI.
15. Demo value: very high.

### 13. Risk Workspace

1. Feature name: Risk Workspace.
2. Where: `signal_engine/service.py`, `frontend/app/dashboard/risk-workspace/page.tsx`.
3. API/tests: `/signal-engine/risk-workspace`, rollups/timeline/graph endpoints; risk workspace tests.
4. Supposed to do: explain one material risk in operational language.
5. Current behavior: selects highest-priority risk, loads exposure, timeline, graph, inventory continuity, shipment continuity, calibration, trust, recommendations.
6. Data: all continuity/risk/event/config data.
7. Logic: candidate selection, risk priority sort, enrichment with impact/recommendations/trust.
8. Outputs: selected risk, explainability, exposure, timeline, context graph, continuity, trust, calibration.
9. UI: material selector, hero, why it matters, if-nothing-changes, recommendations, inbound protection, timeline/graph.
10. Working: strongest end-to-end feature.
11. Weak/risky: no detail loaded until material/scenario selected; stale search params redirect; demo scenario can mutate data.
12. Edge cases: empty risk workspace confusing for a new tenant; multiple risks for same material can be hard to compare.
13. Missing tests: Playwright walkthrough and screenshot checks.
14. Improvements: add empty-state onboarding path and risk-cluster tabs.
15. Demo value: very high; main demo surface.

### 14. Material Risk Rollups

1. Feature name: Material risk rollups.
2. Where: `signal_engine/service.py` `list_material_risk_rollups`.
3. API/UI/tests: `/signal-engine/material-rollups`, Risk Workspace selector, signal tests.
4. Supposed to do: group risk signals by plant/material.
5. Current behavior: groups candidates, picks highest severity, counts risk types, earliest exhaustion, lowest cover.
6. Data: risk candidates.
7. Logic: severity priority, count, earliest date, representative shipment.
8. Outputs: material cards/selector.
9. UI: “Materials at risk” section.
10. Working: clear demo entry point.
11. Weak/risky: `last_updated_at` is currently null; grouping may hide important different causes.
12. Edge cases: multiple plants/materials with null refs.
13. Missing tests: UI selection and stale param cleanup.
14. Improvements: add last signal time and top driver.
15. Demo value: high.

### 15. Time-Phased Cover

1. Feature name: Time-phased cover.
2. Where: `stock/time_phased_cover.py`, used by stock continuity/service/reports.
3. API/UI/tests: `/stock/cover/{plant}/{material}/time-phased`, Risk Workspace/report, `test_time_phased_cover.py`.
4. Supposed to do: sequence consumption and inbound arrivals over time.
5. Current behavior: calculates warning/reserve/critical/interruption dates, first breach dates, current projected dates, shipment protection evaluations, daily projection.
6. Data: usable stock, daily consumption, thresholds, inbounds, supplier links, interruption config status.
7. Logic: chronological inbound application; breach dates before/after each arrival; calibration assumptions.
8. Outputs: breach dates, protection status per shipment, confidence, assumptions.
9. UI: workspace and stock detail/report summaries.
10. Working: very strong engine and tests.
11. Weak/risky: daily consumption static; effective inbound depends on upstream confidence; no schedule/campaign calendar.
12. Edge cases: same-day multiple inbounds, timezone/date cutoffs, huge horizon.
13. Missing tests: frontend rendering, dense projections.
14. Improvements: add production plan and calendar shutdown support.
15. Demo value: very high.

### 16. Stock Cover Detail

1. Feature name: Stock cover detail.
2. Where: `stock/service.py`, `stock/router.py`, frontend stock-cover detail page.
3. API/tests: `/stock/cover`, `/stock/cover/export.csv`, `/stock/cover/{plant}/{material}`, stock tests.
4. Supposed to do: summarize stock risk and inbound contributions.
5. Current behavior: builds rows from latest snapshots, thresholds, weighted shipments; provides status, impact, recommendation, action state.
6. Data: snapshots, thresholds, shipments, movement, exceptions.
7. Logic: shipment weighting by state/confidence/freshness, risk status, impact, recommendation.
8. Outputs: stock cover rows, detail, CSV, action tracking.
9. UI: stock detail page and export proxies.
10. Working: mature and tested.
11. Weak/risky: overlaps newer signal-engine continuity and may disagree on trusted inbound.
12. Edge cases: missing thresholds create warning/safe fallback; action creation from stock detail can create exceptions.
13. Missing tests: frontend detail/action E2E.
14. Improvements: consolidate with signal continuity or explain differences.
15. Demo value: high, but Risk Workspace is better.

### 17. Supplier Reliability

1. Feature name: Supplier reliability.
2. Where: `suppliers/reliability_context.py`, `suppliers/service.py`.
3. API/UI/tests: supplier APIs, Risk Workspace downstream, supplier reliability tests.
4. Supposed to do: adjust inbound trust based on supplier behavior.
5. Current behavior: uses recent supplier shipments scoped by supplier+plant+material, supplier+material, or supplier global; scores on-time and visibility.
6. Data: linked shipment history and current shipment visibility.
7. Logic: minimum sample size, on-time ratio, average visibility confidence, current ETA/visibility penalties.
8. Outputs: reliability band and confidence modifier.
9. UI: supplier pages and reason chains in risk logic.
10. Working: real contextual logic exists.
11. Weak/risky: often unknown/neutral when supplier IDs missing; sample size 3 may still be thin.
12. Edge cases: recent window excludes long-cycle supplier behavior; delay cause not separated.
13. Missing tests: supplier alias/matching UI, concentration/alternate supplier reasoning.
14. Improvements: add route/material/port-specific reliability and delay-cause fields.
15. Demo value: high with seeded history.

### 18. Inbound Protection Quality

1. Feature name: Inbound protection quality.
2. Where: `visibility_confidence.py`, `stock/continuity.py`, `signal_engine/service.py`.
3. API/UI/tests: Risk Workspace; inbound protection tests.
4. Supposed to do: separate “inbound exists” from “inbound protects continuity.”
5. Current behavior: physical inbound is multiplied by visibility confidence adjusted by supplier reliability; shipment protection labels consider ETA before cover loss.
6. Data: shipments, ETA, timestamps, trust config, supplier reliability, inventory exhaustion date.
7. Logic: physical candidate states, confidence ratio, uncertainty quantity, protection label.
8. Outputs: physical/trusted/uncertain quantities, protective quantity, trust reason.
9. UI: Risk Workspace inbound protection panels and executive report.
10. Working: one of the best product ideas in the codebase.
11. Weak/risky: aggregate trusted cover and per-shipment protection need stricter alignment; late inbound must never imply safety.
12. Edge cases: inbound after exhaustion; current ETA missing; low confidence but huge quantity.
13. Missing tests: cross-screen consistency tests.
14. Improvements: make time-phased/protection logic the single source for trusted cover.
15. Demo value: very high.

### 19. Past Incident Analysis and Calibration

1. Feature name: Past Incident Analysis / Incident Replay calibration.
2. Where: `line_stops/service.py`, admin historical page, reports service.
3. API/tests: `/line-stops/historical-validation`, `test_historical_validation_report.py`.
4. Supposed to do: replay prior line-stop incidents and show whether OpsDeck would have warned in time.
5. Current behavior: finds pre-incident stock snapshot/threshold/shipments, runs time-phased cover, classifies detected/partially/missed and confidence.
6. Data: line stop incidents, stock snapshots before incident, thresholds, historical inbounds.
7. Logic: predicted warning date versus incident date; lead time; missed signal analysis.
8. Outputs: detection rate, lead time, confidence classification, markdown report.
9. UI: admin Past Incident Analysis page/screenshots.
10. Working: good deterministic replay.
11. Weak/risky: not true statistical validation; uses available recorded data, not guaranteed point-in-time data lineage.
12. Edge cases: missing pre-incident snapshots, post-facto corrected data, no historical inbounds.
13. Missing tests: frontend report, multiple incident cohorts, data leakage prevention.
14. Improvements: snapshot historical state at ingestion time and add “not model validation” language.
15. Demo value: high, with honesty.

### 20. Executive Continuity Report

1. Feature name: Executive continuity report.
2. Where: `reports/service.py`, `reports/router.py`, `reports/pdf.py`, admin report page.
3. API/tests: `/reports/executive-continuity`, daily brief tests and report paths.
4. Supposed to do: give management a readable continuity summary.
5. Current behavior: builds rollups, workspace per priority material, Past Incident Analysis evidence, recommended actions, markdown/PDF-ready content.
6. Data: material rollups, Risk Workspace outputs, Past Incident Analysis.
7. Logic: priority materials, trust/calibration averages, action aggregation.
8. Outputs: report JSON, markdown, PDF-ready content.
9. UI: admin executive report page and export routes.
10. Working: strong narrative output.
11. Weak/risky: report can inherit uncalibrated impact/trust assumptions; PDF rendering should be stress-tested.
12. Edge cases: no risks, many risks, long text overflow.
13. Missing tests: frontend/PDF visual regression and large report snapshots.
14. Improvements: add calibration disclaimer block and data freshness summary at top.
15. Demo value: very high.

### 21. Admin Configuration

1. Feature name: Admin operational configuration.
2. Where: `impact/router.py`, `configuration_validation.py`, admin components/forms.
3. API/tests: `/impact/*`, configuration/impact/admin tests.
4. Supposed to do: configure thresholds, inbound trust, interruption economics, production lines, product/process dependencies.
5. Current behavior: tenant admin CRUD with tenant validation and cache invalidation.
6. Data: plant/material/line IDs, economics, dependency ratios, trust cadence/tolerance.
7. Logic: validation findings and readiness scoring.
8. Outputs: config records, readiness score, findings, improved risk/impact results.
9. UI: operational configuration pages.
10. Working: broad backend support and tests.
11. Weak/risky: configuration burden is high; invalid ratios depend on Pydantic/model validation; business meaning needs onboarding.
12. Edge cases: conflicting configs, inactive rows, missing product mix.
13. Missing tests: frontend form workflows and validation display.
14. Improvements: guided setup wizard by material and show before/after effect.
15. Demo value: high for credibility.

### 22. Production Interruption Impact

1. Feature name: Production interruption impact.
2. Where: `impact/production_interruption.py`, `impact/router.py`.
3. API/UI/tests: interruption config API/page, `test_impact_engine.py`, seed tests.
4. Supposed to do: estimate business impact of material continuity risk.
5. Current behavior: computes gap hours, interruption hours, gross production impact, downtime/restart/cascading impact, probability, final impact.
6. Data: production rate, finished goods value, survivability, dependency, downtime/restart costs, substitution/cascading factors, product/process dependencies.
7. Logic: deterministic formula version `production_interruption_impact_v1`, probability from urgency/freshness/inbound trust unless override.
8. Outputs: impact values and reason chain.
9. UI: Risk Workspace/report/admin config.
10. Working: well structured and tested.
11. Weak/risky: numbers can appear finance-grade though assumptions are manually configured.
12. Edge cases: missing config returns insufficient config; zero values can understate impact.
13. Missing tests: finance-style validation against real plant cases.
14. Improvements: add confidence band and required-assumption checklist beside every number.
15. Demo value: very high when configured.

### 23. Demo Tenant and Demo Seed Data

1. Feature name: Demo tenant/demo seed data and pilot scenarios.
2. Where: `scripts/seed_demo.py`, `tenants/demo.py`, `signal_engine/pilot_scenarios.py`.
3. API/UI/tests: scenario query on Risk Workspace; demo scenario tests.
4. Supposed to do: provide controlled demo data and scenario walkthroughs.
5. Current behavior: seed creates demo users/plants/materials/suppliers/shipments/config/incidents; scenarios can prepare specific risk states.
6. Data: `DEMO-*` references, demo users, demo materials, seeded stock/inbound/config/history.
7. Logic: demo tenant flag, demo capability gating, scenario support checks.
8. Outputs: demo-ready risks and reports.
9. UI: scenario controls if `NEXT_PUBLIC_ENABLE_PILOT_SCENARIOS` and demo tenant capabilities are enabled.
10. Working: strong and tested.
11. Weak/risky: risk workspace scenario reads mutate database state; demo references are blocked for non-demo uploads.
12. Edge cases: scenario repeated calls change timestamps/state; demo data drift after manual edits.
13. Missing tests: frontend scenario controls, reset behavior.
14. Improvements: add reset demo tenant and make scenarios idempotent/non-mutating where possible.
15. Demo value: very high.

### 24. Dashboard Pages

1. Feature name: Dashboard pages.
2. Where: `dashboard/service.py`, frontend dashboard pages, shell.
3. API/tests: `/dashboard/executive`, `/dashboard/pilot-readiness`, executive dashboard tests.
4. Supposed to do: summarize continuity status for daily operations and management.
5. Current behavior: combines stock cover, exceptions, shipments, movement, supplier performance, automated freshness.
6. Data: stock rows, exceptions, movement, suppliers, sync sources.
7. Logic: KPI aggregation, freshness summaries, attention lists.
8. Outputs: KPIs, top risks, exception lists, movement/supplier summaries.
9. UI: main dashboard and shell nav.
10. Working: useful high-level view.
11. Weak/risky: nav labels are sometimes abstract; dashboard depends on older stock-cover service more than signal-engine workspace.
12. Edge cases: empty tenant, stale data, no automated sources.
13. Missing tests: frontend rendering and role nav.
14. Improvements: align dashboard risk cards with Risk Workspace rollups.
15. Demo value: high.

### 25. Authentication and Tenant Isolation

1. Feature name: Authentication/tenant isolation.
2. Where: `auth/*`, `api/dependencies.py`, frontend middleware/proxies.
3. API/tests: `/auth/*`, all tenant-scoped APIs; `test_auth_tenancy.py`, superadmin tests.
4. Supposed to do: isolate tenant data and enforce role access.
5. Current behavior: JWT bearer auth, active membership selection by `X-Tenant-Slug`, role guards for operator/admin/superadmin.
6. Data: users, roles, tenant memberships, JWT claims, tenant slug header.
7. Logic: membership activation, tenant access expiry, 404 on cross-tenant probes with slug.
8. Outputs: `RequestContext`, allowed/denied API access.
9. UI: middleware protects dashboard, role-based nav.
10. Working: strong backend pattern and tests.
11. Weak/risky: frontend proxy cookie naming/session behavior should be E2E-tested; active membership defaults to first membership.
12. Edge cases: multi-tenant user switching, expired tenant access, local/prod cookie differences.
13. Missing tests: Playwright auth/session refresh/tenant switching.
14. Improvements: explicit tenant switcher and session E2E tests.
15. Demo value: medium; pilot value critical.

### 26. Tests and Validation Coverage

1. Feature name: Tests and validation coverage.
2. Where: `apps/backend/tests`, frontend lint only found.
3. API/UI/tests: 494 backend tests collected; no frontend test suite found outside route names containing “test”.
4. Supposed to do: prove behavior, prevent regressions.
5. Current behavior: extensive backend pytest suite across engines, API flows, tenancy, ingestion, reports, notifications.
6. Data: test fixtures and seeded domain scenarios.
7. Logic: unit/integration-style backend validation.
8. Outputs: confidence in backend deterministic behavior.
9. UI: not covered by automated browser tests.
10. Working: backend coverage is a major strength.
11. Weak/risky: frontend pilot flows, visual layout, Graph live integration, and browser auth not covered enough.
12. Edge cases: browser-only failures, large datasets, real external APIs.
13. Missing tests: Playwright, component tests, visual regression, live sync smoke tests.
14. Improvements: add E2E smoke pack before pilot.
15. Demo value: backend confidence high; pilot confidence incomplete.

## Final Verdict

OpsDeck is **demo-ready** for a controlled, honest demo.

OpsDeck is **not yet customer-pilot-ready** because pilot users will bring messy workbooks, partial supplier masters, real OneDrive policies, missing thresholds, changing consumption plans, and expectations that impact numbers are calibrated. The product already has the right foundation. The next phase should reduce ambiguity, improve calibration, consolidate overlapping continuity logic, and add frontend E2E proof.
