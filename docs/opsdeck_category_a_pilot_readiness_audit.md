# OpsDeck Category A Pilot Readiness Execution Audit

Date: June 15, 2026  
Pilot target: one paid, guided steel/heavy manufacturing pilot by July 31, 2026  
Scope: Upload Experience, Past Incident Analysis / Incident Replay, Risk Workspace, Trusted Inbound Logic / Inbound Protection Quality, Pilot Onboarding Process

This is not a broad product audit. It is a pilot-readiness execution audit: what must be true for one guided customer pilot to feel credible, understandable, and operationally useful.

## 1. Executive Verdict

OpsDeck is not yet July-pilot-ready in these five Category A areas, but it is close enough to become ready with a focused two-week sprint.

The strongest foundation is already present: uploads work, workbook mapping exists, historical incident replay exists, the Risk Workspace is real, inbound confidence is modeled, and there are meaningful backend tests. The weak points are not “missing product”; they are trust boundaries, customer-facing language, and a few logic mismatches that could make a plant/procurement user doubt the system.

Verdict: conditionally pilot-ready after fixes. Without the fixes below, OpsDeck should not be shown as a paid pilot decision-support system. It can still be shown as a guided demo.

## 2. Critical Blockers

1. Trusted inbound can overstate operational safety.
   - `apps/backend/app/modules/stock/continuity.py` adds trusted inbound into cover before checking whether that inbound arrives before cover loss.
   - `apps/backend/app/modules/signal_engine/service.py` then checks shipment ETA against an already-extended projected exhaustion date.
   - Pilot risk: a late inbound shipment may make a material look safer than it is.

2. Risk Workspace can hide the at-risk material list in demo scenario mode.
   - `apps/frontend/app/dashboard/risk-workspace/page.tsx` returns `Promise.resolve([])` for rollups when `activeScenario` is set.
   - Pilot risk: when a user clicks a critical item or scenario, the surrounding risk list can disappear instead of staying visible.

3. Upload Center has too much destructive power for normal operators.
   - `DELETE /api/v1/ingestion/uploads` currently uses `require_operator_access`.
   - The UI exposes “Clear uploaded data” from `apps/frontend/components/onboarding/upload-panel.tsx`.
   - Pilot risk: a normal user can wipe tenant operational data during a guided pilot.

4. Past Incident Analysis is credible internally but not customer-proof in presentation.
   - The frontend uses “Incident replay” in one place but previously exported the old dashed validation report filename.
   - It does not first-class show incident date, stock position, inbound position, threshold, warning date, and lead time in one plain operational view.
   - Pilot risk: customers may misunderstand it as statistical ML validation or distrust the replay because assumptions are not visible.

5. There is no single guided pilot onboarding path.
   - Uploads, configuration, incident replay, Risk Workspace, and executive report exist as separate areas.
   - Pilot risk: a new pilot cannot confidently follow stock upload -> shipment upload -> thresholds -> impact config -> incident replay -> risk workspace -> executive report without Codex/developer guidance.

## 3. Fix-Before-July List

1. Fix trusted inbound cover logic so late or low-confidence inbound cannot make a material look safe.
2. Keep the Risk Workspace material risk list visible after selecting one critical/high item and during demo scenarios.
3. Rename customer-facing upload navigation from “Source health” to “Upload Center” or “Pilot Data Setup”.
4. Restrict tenant-wide upload clearing to admin/superadmin, and add a typed confirmation.
5. Add upload summaries that explicitly show received rows, accepted rows, rejected rows, updated rows, new plants/materials/suppliers, duplicate rows, and next action.
6. Add warnings when uploads silently create new plant/material/supplier records from unrecognized names.
7. Rename customer-facing replay analysis to “Past Incident Analysis” or “Incident Replay”.
8. Add replay cards for incident date, stock position, inbound position, threshold, OpsDeck warning date, lead time, and missing-data limitations.
9. Add a pilot onboarding checklist page or first-run panel with mandatory and optional setup steps.
10. Add backend tests for late inbound, low-confidence inbound, duplicate uploads, destructive upload permissions, and historical replay limitation display.

## 4. Can-Wait-Until-After-Pilot List

1. Fully automated OneDrive production sync.
2. Broad supplier master deduplication workflow.
3. Advanced ML/statistical validation language or model benchmarking.
4. Self-serve multi-tenant enterprise onboarding.
5. Notification routing and escalation workflows.
6. Complex production-line dependency modeling beyond the few pilot materials.
7. Deep admin UI for every continuity threshold and trust parameter.
8. Full browser automation coverage for all dashboards.
9. Long-term calibration dashboards.
10. Rich role-based onboarding for every department.

## 5. Feature-by-Feature Detailed Audit

## Upload Experience

### A. Current State

Upload functionality is implemented across:

- Backend files:
  - `apps/backend/app/modules/ingestion/router.py`
  - `apps/backend/app/modules/ingestion/service.py`
  - ingestion models/schemas under `apps/backend/app/modules/ingestion/`
- Frontend files:
  - `apps/frontend/app/dashboard/onboarding/page.tsx`
  - `apps/frontend/components/onboarding/upload-panel.tsx`
  - dashboard shell navigation references “Source health”
- API endpoints:
  - `POST /api/v1/ingestion/upload`
  - `POST /api/v1/ingestion/workbook-upload`
  - `GET /api/v1/ingestion/uploads`
  - `GET /api/v1/ingestion/jobs/{job_id}`
  - `POST /api/v1/ingestion/jobs/{job_id}/rollback`
  - `POST /api/v1/ingestion/jobs/{job_id}/reprocess`
  - `DELETE /api/v1/ingestion/uploads`
  - `POST /api/v1/ingestion/mapping-preview`
  - `POST /api/v1/ingestion/workbook-mapping-preview`
  - `POST /api/v1/ingestion/url-mapping-preview`
- Tests:
  - backend ingestion tests exist, but pilot-specific upload trust/UX cases need to be added.

The code supports shipment, stock, threshold, consumption, event, and workbook uploads. It previews mappings, accepts overrides, stores ingestion jobs, tracks accepted/rejected rows, supports rollback/reprocess, and records history.

### B. What Works Today

- A normal guided user can upload CSV/XLSX-like operational files through the UI.
- Workbook/sheet mapping exists and can process multi-sheet workbooks.
- Required mapping failures are blocked before processing.
- Missing row-level fields are explained in more human language than raw schema errors.
- Accepted/rejected row counts are shown.
- Rejected row samples are visible.
- Rollback and reprocess exist.
- Unknown plants/materials/suppliers can be created automatically, which helps during early pilot setup.

### C. What Can Break In A Real Steel/Heavy Manufacturing Pilot

- Indian plant files may use headers such as `Rake No`, `GRN`, `Vendor Code`, `Yard Stock`, `Unrestricted Stock`, `ETA at Plant`, `ETA Port`, `PO No`, `LR No`, `Gate Entry`, or `Material Grade`; aliases are useful but not broad enough for messy plant exports.
- Duplicate shipment IDs can update the same shipment because shipment upsert is keyed by `shipment_id` within tenant. Duplicate IDs across plant/material contexts could corrupt continuity.
- Unknown/misspelled plant or material names are created automatically. That is convenient but risky: `Dolvi` vs `Dovli` could become two plants.
- Stock snapshot upsert can fall back to latest plant/material snapshot when exact timestamp is not found, which may surprise a user who expects a new snapshot.
- Missing ETA is rejected for shipments, but the UI should explain this as “OpsDeck cannot judge protection timing without ETA.”
- Missing consumption makes cover math impossible or weak; this needs to be surfaced as a pilot blocker, not buried in rejected rows.
- Missing thresholds make severity ambiguous; this should become a setup checklist failure.
- `DELETE /uploads` is available to operators and can wipe shipments, stock snapshots, thresholds, ingestion history, and exceptions.

### D. What Will Confuse A Plant User

- “Source health” sounds like integration monitoring, not the place to upload stock/shipment/threshold files.
- “Mapping overrides” and “required mappings” are developer-ish terms.
- Rollback status like “deleted, preserved, skipped” is accurate but not enough. A plant user needs “what changed in my risk picture?”
- Reprocess is understandable to a developer, but a plant user may not know whether it replaces, duplicates, or audits prior data.
- The upload result does not consistently answer: “Is OpsDeck now safe to use for this material/plant?”

### E. What Could Make The Customer Lose Trust

- A pilot user accidentally clearing all uploaded data.
- A misspelled material silently creating a new material and making a real risk disappear.
- A duplicate shipment replacing another shipment without a clear warning.
- Accepted row counts looking successful while critical thresholds or consumption are missing.
- Rollback preserving updated records without a clear “not a full undo” warning.

### F. Missing Tests

- Duplicate shipment ID within same upload and across plants/materials.
- Unknown plant/material/supplier warning behavior.
- Operator cannot clear all uploaded tenant data.
- Missing consumption produces clear setup limitation.
- Missing threshold blocks strong risk conclusions.
- Workbook with Indian-style plant/export headers maps correctly.
- Rollback/reprocess does not duplicate or erase unrelated data.

### G. Exact Fixes Needed

1. Rename UI nav and page copy from “Source health” to “Upload Center” or “Pilot Data Setup”.
2. Restrict `DELETE /api/v1/ingestion/uploads` to admin/superadmin.
3. Replace single browser confirm with typed confirmation: `CLEAR PILOT DATA`.
4. Add upload summary after every upload:
   - rows received
   - accepted rows
   - rejected rows
   - updated records
   - new plants/materials/suppliers
   - duplicate rows
   - missing ETA/consumption/threshold count
   - top rejection reasons
   - next action
5. Add warning banners for auto-created plant/material/supplier records.
6. Extend aliases for Indian plant-style files.
7. Add duplicate detection before upsert and show duplicate handling in the result.
8. Make rollback copy explicit: “This only removes records created by this import. Records updated by this import are preserved.”

### H. Severity

High. The upload system works, but pilot trust can break quickly if a non-technical user cannot tell what changed or accidentally clears data.

### I. Effort

Medium.

### J. Before July Or Later

Must fix before July pilot.

## Past Incident Analysis / Incident Replay

### A. Current State

Past Incident Analysis exists across:

- Backend files:
  - `apps/backend/app/modules/line_stops/service.py`
  - `apps/backend/app/modules/line_stops/router.py`
  - line stop schemas/models
- Frontend files:
  - `apps/frontend/app/dashboard/admin/past-incident-analysis/page.tsx`
- API endpoints:
  - `GET /api/v1/line-stops/historical-validation`
- Tests:
  - `apps/backend/tests/test_historical_validation_report.py`

The backend replays line-stop incidents against prior stock snapshots, thresholds, and inbound shipments. It calculates detected/partial/missed outcomes, warning lead time, confidence rationale, missed signals, and recommended replay actions.

### B. What Works Today

- It answers a meaningful pilot question: “Would OpsDeck have warned us before this past interruption?”
- It calculates warning lead time.
- It distinguishes detected, partially detected, and missed incidents.
- It records missing-data limitations such as no stock snapshot, missing thresholds, or no linked inbound.
- It is tenant-scoped and tested.
- The UI already uses “Incident replay” in the page title.

### C. What Can Break In A Real Pilot

- Historical inbounds use raw shipment quantity in replay and do not clearly expose whether those shipments were trusted, stale, late, or uncertain.
- Customers may provide incomplete historical stock snapshots and expect a strong answer.
- Incident dates may not align with upload snapshot times.
- Thresholds may have changed historically, but the replay may use available configured thresholds rather than a complete historical threshold timeline.
- Lead time can look precise even when underlying data was sparse.

### D. What Will Confuse A Plant User

- Old “Historical validation” language sounds like ML/statistical model validation.
- The UI does not immediately show the operational evidence chain in one row: incident date, stock, inbound, threshold, warning date, lead time.
- Export filename previously used the old dashed validation report name.
- Confidence rationale exists but is not framed as “what data was available at the time.”

### E. What Could Make The Customer Lose Trust

- Claiming “OpsDeck would have caught this” without showing the stock/inbound/threshold state used.
- Showing a warning lead time without exposing missing data.
- Letting a customer interpret the feature as statistically validated prediction accuracy.
- Counting an inbound shipment as context when that shipment had poor tracking or arrived too late.

### F. Missing Tests

- Replay with late inbound should not imply protection.
- Replay with missing threshold should show limitation and avoid strong conclusion.
- Replay with stale/missing shipment tracking should show lower confidence.
- Frontend display should include incident date, stock position, inbound position, threshold, warning date, and lead time.
- Export should use customer-facing naming.

### G. Exact Fixes Needed

1. Rename customer-facing feature to “Past Incident Analysis” with subtitle “Incident Replay”.
2. Add explicit copy: “This is a replay using available historical records, not statistical ML validation.”
3. Add backend result fields:
   - stock snapshot time
   - available stock at incident
   - daily consumption
   - threshold days
   - warning days
   - inbound quantity due before incident
   - first inbound ETA
   - missing-data limitations
4. Add a replay evidence card per incident:
   - Incident date
   - Stock position
   - Inbound position
   - Threshold
   - OpsDeck warning date
   - Lead time available
5. Rename export to `incident-replay-report.md`.
6. Keep “detected/partial/missed” but explain them in plain plant language.

### H. Severity

High.

### I. Effort

Medium.

### J. Before July Or Later

Must fix before July pilot if this feature will be used in sales/pilot proof. Can wait only if incident replay is hidden from the pilot.

## Risk Workspace

### A. Current State

Risk Workspace exists across:

- Backend files:
  - `apps/backend/app/modules/signal_engine/service.py`
  - `apps/backend/app/modules/signal_engine/router.py`
  - risk signal schemas/models
- Frontend files:
  - `apps/frontend/app/dashboard/risk-workspace/page.tsx`
- API endpoints:
  - risk workspace detail endpoint
  - material risk rollups endpoint
- Tests:
  - risk workspace and inbound protection backend tests exist, but UI persistence and empty-state tests are missing.

The page shows material risk rollups, filters, selected risk detail, inventory continuity, inbound protection, timeline, recommended actions, and demo scenarios.

### B. What Works Today

- It has the right core content for plant/procurement users: plant, material, severity, days cover, inbound context, recommended action, and signal history.
- Rollups group risk by plant/material.
- Selected risk detail pulls in multiple engines: stock cover, shipment continuity, supplier reliability, confidence/freshness, and calibration.
- Demo scenario controls are gated by demo tenant capability.
- Inbound protection quality is visible.

### C. What Can Break In A Real Pilot

- In demo scenario mode, rollups are forced empty, so the risk list disappears.
- The user specifically expects that clicking one critical item should not make other critical/high items vanish.
- Multiple risks for the same material can feel duplicated unless rollups are the primary object and individual signals are secondary.
- If no risk exists, empty states may read as unavailable instead of “no current continuity risks detected; here is what data was checked.”
- Demo scenario reads mutate/prepare data through `prepare_pilot_scenario`, which is acceptable for controlled demos but risky if mixed with live pilot data.

### D. What Will Confuse A Plant User

- The top of the page does not aggressively answer: “What should I worry about today?”
- Some labels are still system-centric: “contributing signals”, “material rollups”, “selected risk”.
- If no item is selected, “open one material to load focused continuity intelligence” is less natural than “Select a material to see why it is at risk and what to do next.”
- Demo scenario controls can look like real filters unless strongly marked as demo-only.

### E. What Could Make The Customer Lose Trust

- Clicking a critical material and seeing the rest of the list disappear.
- A critical severity without a plain explanation of why.
- Recommended actions that do not mention the affected shipment, ETA, or stock breach date.
- Empty state that looks like data failed to load.
- Scenario controls altering visible data without clear demo boundaries.

### F. Missing Tests

- UI/Playwright test: risk list remains visible after selecting a material.
- UI/Playwright test: demo scenario still shows material rollups or a clearly labeled scenario risk list.
- Empty state test for “no risks” vs “data unavailable”.
- Backend test for rollup freshness timestamp.
- Test that multiple signals for the same material are grouped without hiding other materials.

### G. Exact Fixes Needed

1. Always fetch material rollups in `apps/frontend/app/dashboard/risk-workspace/page.tsx`, even when `activeScenario` is set.
2. Keep an “All at-risk materials” panel visible above or beside selected risk detail.
3. Highlight the selected material instead of replacing the list.
4. Add a top summary:
   - “Today’s main continuity risk: {material} at {plant}.”
   - “Cover: {days} days.”
   - “Projected breach: {date}.”
   - “Recommended action: {plain action}.”
5. Rename internal labels:
   - “Material rollups” -> “At-risk materials”
   - “Contributing signals” -> “Reasons”
   - “Selected risk” -> “Current focus”
6. Improve no-risk state:
   - “No current material continuity risks found from uploaded stock, threshold, and inbound data.”
   - Show last upload time and missing setup items.
7. Keep demo scenario controls behind a clear “Demo-only scenario” banner.

### H. Severity

High.

### I. Effort

Small to Medium.

### J. Before July Or Later

Must fix before July pilot.

## Trusted Inbound Logic / Inbound Protection Quality

### A. Current State

Trusted inbound logic exists across:

- Backend files:
  - `apps/backend/app/modules/stock/continuity.py`
  - `apps/backend/app/modules/stock/time_phased_cover.py`
  - `apps/backend/app/modules/stock/visibility_confidence.py`
  - `apps/backend/app/modules/signal_engine/service.py`
  - `apps/backend/app/modules/suppliers/reliability_context.py`
- Frontend files:
  - `apps/frontend/app/dashboard/risk-workspace/page.tsx`
- API outputs:
  - inventory continuity result
  - shipment continuity result
  - shipment protection evaluation
  - risk workspace response
- Tests:
  - `apps/backend/tests/test_inventory_continuity.py`
  - `apps/backend/tests/test_risk_workspace_inbound_protection.py`
  - `apps/backend/tests/test_inbound_delay_cover_intelligence.py`
  - `apps/backend/tests/test_time_phased_cover.py`
  - `apps/backend/tests/test_visibility_confidence.py`
  - `apps/backend/tests/test_supplier_reliability_context.py`

The system separates physical inbound, trusted inbound, visibility uncertainty, supplier reliability, ETA behavior, stale tracking, and per-shipment protection labels.

### B. What Works Today

- Physical inbound and trusted inbound are distinct concepts.
- Low confidence reduces trusted quantity.
- Stale tracking and ETA deterioration are considered.
- Supplier reliability can modify trust.
- Per-shipment protection labels exist: strong, partial, weak, not protective, unknown.
- The UI shows inbound protection quality and shipment-level reasoning.

### C. What Can Break In A Real Pilot

- Aggregate trusted inbound can extend projected exhaustion even when ETA is after the true stockout/breach date.
- Per-shipment protection can disagree with aggregate cover.
- `arrives_before_projected_exhaustion` checks against `inventory.projected_exhaustion_date`, which may already include trusted inbound. That can create circular optimism.
- A large low/medium-confidence shipment can make the aggregate situation look safer than operations should treat it.
- If ETA is missing, stale, or deteriorating, the shipment should not create a strong safety impression.

### D. What Will Confuse A Plant User

- “Physical inbound”, “trusted inbound”, and “visibility uncertain” need plain copy.
- A user needs to see why each protected quantity is trusted: quantity, ETA, confidence, supplier reliability, tracking freshness, and ETA change.
- If top-level cover says safe but shipment card says weak/not protective, trust will drop immediately.
- “Trusted inbound” may be interpreted as material guaranteed to arrive, not probabilistic operational protection.

### E. What Could Make The Customer Lose Trust

- A late rake/truck/ship makes cover look safe, then the plant still runs short.
- A supplier with poor reliability still protects cover without an obvious warning.
- Stale tracking is buried below the fold.
- A shipment with missing ETA contributes to confidence.
- Aggregated numbers do not reconcile with shipment cards.

### F. Missing Tests

- Late inbound should not extend aggregate trusted days of cover beyond raw cover.
- Shipment ETA after raw projected cover loss should be `not_protective`.
- Low-confidence inbound should remain uncertain and should not make severity safe.
- Aggregate trusted inbound should reconcile with per-shipment protective quantities.
- Missing ETA shipment should not count as protective.
- Stale tracking should reduce protection and show a reason.
- Supplier reliability downgrade should be visible in reason chain.

### G. Exact Fixes Needed

1. Compute baseline/raw exhaustion date from usable stock only.
2. Treat inbound as protective only if ETA is before raw exhaustion or before the configured breach/warning horizon.
3. Use baseline exhaustion for `arrives_before_cover_loss`, not exhaustion already extended by trusted inbound.
4. Split aggregate quantities in the API/UI:
   - physical inbound
   - ETA-protective trusted inbound
   - trusted but late inbound
   - uncertain inbound
5. Ensure top-level cover uses only ETA-protective trusted inbound.
6. Add reason strings:
   - “ETA arrives after projected cover loss”
   - “Tracking update is stale”
   - “Supplier reliability reduces confidence”
   - “ETA has slipped by X days”
   - “ETA missing, cannot protect cover”
7. In UI, show every protected shipment with quantity, ETA, confidence, stale/missing tracking, supplier reliability, ETA deterioration, and protection status.

### H. Severity

Critical.

### I. Effort

Medium.

### J. Before July Or Later

Must fix before July pilot. This is the most important credibility fix.

## Pilot Onboarding Process

### A. Current State

Pilot onboarding is distributed across existing areas:

- Upload/source setup:
  - `apps/frontend/app/dashboard/onboarding/page.tsx`
  - `apps/frontend/components/onboarding/upload-panel.tsx`
- Admin configuration:
  - `apps/frontend/app/dashboard/admin/operational-configuration/page.tsx`
- Historical validation:
  - `apps/frontend/app/dashboard/admin/past-incident-analysis/page.tsx`
- Risk Workspace:
  - `apps/frontend/app/dashboard/risk-workspace/page.tsx`
- Reports:
  - executive continuity report routes/pages
- Backend readiness:
  - dashboard/pilot readiness logic exists, but it is not a full guided onboarding flow.
- Docs:
  - `docs/pilot_demo_walkthrough.md`
  - `docs/pilot_rollout_readiness.md`
  - `docs/onboarding_ingestion_flow.md`

There is documentation and enough product surface, but no single guided pilot path.

### B. What Works Today

- A guided internal operator can upload data, configure operational settings, open incident replay, view risk workspace, and export reports.
- Demo tenant/seed flows exist.
- There are docs that can support a guided demo.

### C. What Can Break In A Real Pilot

- Customer uploads shipments before thresholds and expects risk severity.
- Customer uploads stock without daily consumption and expects days cover.
- Customer skips impact configuration and expects production interruption impact numbers.
- Customer runs incident replay before line-stop incidents or historical snapshots exist.
- Customer opens Risk Workspace before enough data exists and sees an empty/unavailable state.

### D. What Will Confuse A Plant User

- There is no “start here” flow.
- Mandatory vs optional data is unclear.
- They may not know when OpsDeck has enough data to make strong conclusions.
- Admin configuration feels separate from pilot setup.
- Reports may appear before data quality is ready.

### E. What Could Make The Customer Lose Trust

- Strong conclusions from incomplete data.
- Empty dashboards after upload because thresholds or consumption are missing.
- Incident replay with missing historical data but no up-front limitation.
- Executive report exported before the data is pilot-ready.

### F. Missing Tests

- Pilot checklist state calculation.
- Setup blocks strong conclusion until stock, shipments, thresholds, and consumption are present.
- Incident replay disabled or caveated when historical data is missing.
- Executive report warns when mandatory setup is incomplete.
- UI smoke test for full guided pilot path.

### G. Exact Fixes Needed

1. Add “Pilot Setup Checklist” to Upload Center or as `/dashboard/onboarding/pilot`.
2. Checklist steps:
   - Upload stock snapshot
   - Upload inbound shipments
   - Upload thresholds
   - Confirm daily consumption
   - Review rejected rows and auto-created master data
   - Configure production interruption impact
   - Run Past Incident Analysis
   - Open Risk Workspace
   - Export Executive Continuity Report
3. Mark mandatory before strong conclusions:
   - stock snapshot
   - daily consumption
   - thresholds
   - shipment ETA/latest update/source
   - at least one successful upload per required feed
   - no unresolved critical rejected rows
4. Mark optional:
   - production impact values
   - supplier reliability history
   - historical incident replay
   - OneDrive sync
5. Hide or de-emphasize until after pilot:
   - complex sync configuration
   - superadmin setup
   - broad calibration dashboards
   - advanced tenant governance
6. Add downloadable pilot data templates for stock, shipments, thresholds, and incident history.

### H. Severity

High.

### I. Effort

Medium.

### J. Before July Or Later

Must fix before July pilot in lightweight form. It does not need to be enterprise self-serve; it needs to guide one paid pilot.

## 6. Exact Codex Implementation Plan

### Phase 1: Trust And Navigation Fixes

1. Rename “Source health” to “Upload Center” in frontend navigation and page headings.
2. Keep Risk Workspace rollups visible when a material or demo scenario is selected.
3. Add clearer Risk Workspace top summary and no-risk copy.
4. Rename “Historical validation” customer-facing copy to “Past Incident Analysis / Incident Replay”.
5. Change incident replay export filename.

### Phase 2: Trusted Inbound Correction

1. Add baseline exhaustion date to inventory continuity calculation.
2. Exclude late inbound from trusted cover used for projected exhaustion.
3. Make per-shipment protection evaluate ETA against baseline/raw cover loss.
4. Add aggregate reconciliation fields so UI numbers match shipment protection cards.
5. Add backend tests for late inbound, missing ETA, stale tracking, and low confidence.

### Phase 3: Upload Hardening

1. Change clear upload endpoint to admin-only.
2. Add typed confirmation in the UI.
3. Add duplicate and auto-created entity summaries to upload results.
4. Extend aliases for Indian plant-style exports.
5. Add tests for duplicates, auto-created entity warnings, destructive permission, and missing mandatory setup fields.

### Phase 4: Incident Replay Evidence

1. Add evidence fields to the Past Incident Analysis response.
2. Show stock/inbound/threshold/warning/lead-time cards for each incident.
3. Add limitation copy to every incident replay result.
4. Add backend tests for replay limitations.

### Phase 5: Pilot Onboarding

1. Add pilot checklist panel/page.
2. Wire checklist state from uploads, thresholds, consumption, impact config, replay availability, and risk readiness.
3. Add pilot data templates or documented CSV schemas.
4. Add one Playwright smoke test for the guided pilot path.

## 7. Suggested File Changes

- `apps/frontend/components/shell/dashboard-shell.tsx`
  - Rename nav label “Source health” to “Upload Center”.

- `apps/frontend/app/dashboard/onboarding/page.tsx`
  - Rename page heading.
  - Add pilot setup checklist entry panel.

- `apps/frontend/components/onboarding/upload-panel.tsx`
  - Add improved upload summary.
  - Add typed destructive confirmation.
  - Add duplicate/unknown entity warnings.
  - Improve rollback/reprocess copy.

- `apps/backend/app/modules/ingestion/router.py`
  - Change `clear_uploaded_data` dependency from `require_operator_access` to admin-level access.

- `apps/backend/app/modules/ingestion/service.py`
  - Extend aliases.
  - Add duplicate detection.
  - Return auto-created plant/material/supplier counts and warnings.
  - Avoid surprising stock snapshot fallback or report it explicitly.

- `apps/frontend/app/dashboard/admin/past-incident-analysis/page.tsx`
  - Rename to Past Incident Analysis / Incident Replay.
  - Add evidence cards and limitation copy.

- `apps/backend/app/modules/line_stops/service.py`
  - Add replay evidence fields.
  - Caveat missing historical threshold/inbound/tracking data.

- `apps/frontend/app/dashboard/risk-workspace/page.tsx`
  - Always fetch rollups.
  - Keep risk list visible.
  - Add “what should I worry about today?” summary.
  - Improve empty/no-risk state.

- `apps/backend/app/modules/stock/continuity.py`
  - Separate baseline exhaustion from ETA-protective trusted inbound.

- `apps/backend/app/modules/signal_engine/service.py`
  - Evaluate shipment protection against baseline cover loss.
  - Reconcile aggregate and per-shipment trusted inbound.

- New or updated docs:
  - `docs/pilot_onboarding_runbook.md`
  - `docs/pilot_data_templates.md`

## 8. Suggested Tests To Add

1. `test_late_inbound_does_not_extend_trusted_cover`
2. `test_missing_eta_shipment_is_not_protective`
3. `test_low_confidence_inbound_does_not_make_material_safe`
4. `test_aggregate_trusted_inbound_matches_protective_shipments`
5. `test_operator_cannot_clear_uploaded_data`
6. `test_upload_duplicate_shipment_id_is_reported`
7. `test_upload_auto_created_material_is_reported`
8. `test_indian_style_workbook_headers_map_to_required_fields`
9. `test_incident_replay_shows_missing_threshold_limitation`
10. `test_incident_replay_includes_stock_inbound_threshold_warning_evidence`
11. Playwright: selected Risk Workspace item does not hide other risks.
12. Playwright: pilot setup checklist moves from incomplete to ready after required fixtures.

## 9. Suggested Frontend Copy Changes

- Replace “Source health” with “Upload Center”.
- Replace “Historical validation” with “Past Incident Analysis”.
- Subtitle: “Incident Replay”.
- Incident replay caveat:
  - “This replay uses the historical stock, threshold, and inbound records available to OpsDeck. It is not statistical ML validation.”
- Upload summary:
  - “OpsDeck processed this file. Review accepted rows, rejected rows, new master data, and next actions before relying on the dashboard.”
- Missing ETA:
  - “ETA is required because OpsDeck cannot judge whether inbound protects production without arrival timing.”
- Missing consumption:
  - “Daily consumption is required to calculate days of cover.”
- Missing threshold:
  - “Thresholds are required before OpsDeck can classify material risk as Critical, High, Medium, or Low.”
- Trusted inbound:
  - “Physical inbound is material recorded as on the way. Trusted inbound is the portion OpsDeck believes can protect cover before a breach. Uncertain inbound should not be treated as safe cover.”
- Risk Workspace top line:
  - “What to worry about today”
  - “{Material} at {Plant} has {days} days of cover. Breach expected around {date}. Recommended action: {action}.”
- No-risk state:
  - “No current continuity risks found from uploaded stock, threshold, and inbound data. Check setup completeness before treating this as all-clear.”
- Rollback:
  - “Rollback removes records created by this import. Records that were updated from earlier imports are preserved.”

## 10. Final Two-Week Sprint Plan

### Days 1-2: Customer-Facing Clarity

- Rename Upload Center and Past Incident Analysis copy.
- Fix Risk Workspace selected item behavior so other risks remain visible.
- Add no-risk and missing-data copy.
- Hide or strongly label demo-only scenario controls.

### Days 3-5: Trusted Inbound Logic

- Implement baseline exhaustion.
- Exclude late inbound from trusted cover.
- Reconcile aggregate trusted inbound with shipment protection cards.
- Add backend tests for late, missing ETA, stale, and low-confidence shipments.

### Days 6-7: Upload Pilot Hardening

- Restrict clear uploaded data to admin/superadmin.
- Add typed confirmation.
- Add duplicate and auto-created entity warnings.
- Extend Indian-style aliases.
- Add upload tests.

### Days 8-9: Incident Replay Proof

- Add replay evidence fields.
- Add incident replay cards in UI.
- Rename export.
- Add limitation tests.

### Days 10-11: Pilot Onboarding

- Add lightweight Pilot Setup Checklist.
- Define mandatory vs optional setup.
- Add pilot data template docs.

### Days 12-14: Dry Run And Polish

- Run backend tests.
- Run frontend lint.
- Add one guided Playwright smoke test if test infrastructure is stable.
- Perform a seeded pilot dry run:
  - stock upload
  - shipment upload
  - threshold upload
  - impact config
  - Past Incident Analysis
  - Risk Workspace
  - Executive report

Final July readiness condition: OpsDeck can be used for one guided paid pilot only if trusted inbound no longer overstates safety, the Risk Workspace keeps context visible, uploads clearly summarize what changed, and the pilot onboarding path prevents strong conclusions from incomplete data.
