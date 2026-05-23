# OpsDeck Pilot Demo Walkthrough

## Demo Objective

Show a COO, procurement head, or plant operations leader how OpsDeck turns messy operational files into continuity intelligence without replacing ERP or automating procurement.

The demo should prove:

- OpsDeck can ingest existing operational files.
- OpsDeck explains what it accepted, rejected, and understood.
- OpsDeck identifies plant-material continuity pressure.
- OpsDeck separates physical inbound from trusted inbound protection.
- OpsDeck recommends human-led operational checks.

## Audience

Best fit for:

- Plant operations leaders
- Procurement heads
- Supply chain continuity owners
- COO or business-unit leadership

Frame OpsDeck as a continuity intelligence layer above fragmented data, not a control tower and not an ERP replacement.

## First 30 Seconds

Use this opening:

“OpsDeck reads the operational files teams already use: stock snapshots, inbound shipment trackers, and continuity thresholds. It does not replace SAP or procurement workflows. It checks whether current stock and inbound movement actually protect production continuity, then explains where confidence is weak and what operations should verify next.”

Avoid:

- “AI predicts everything”
- “Autonomous procurement”
- “Replacement for SAP”
- “Control tower operating system”

## Demo Files

Use the CSV files in `docs/demo-data/`:

- `demo_stock_snapshots.csv`
- `demo_inbound_shipments.csv`
- `demo_continuity_thresholds.csv`

All demo rows use explicit `DEMO-` prefixes to avoid collision with customer data.

The sample story includes:

- Ocean vessel delay with declining coking coal cover.
- Inland movement stale after port arrival for pellet fines.
- ERP-style inbound exists but trusted protection is weak for limestone.
- Fresh verified inbound stabilizes ferro manganese cover.
- Multiple coking coal inbound rows with mixed protection.

## Setup

Use these environment flags for the Risk Workspace pilot scenario selector:

```text
ENABLE_PILOT_SCENARIOS=true
NEXT_PUBLIC_ENABLE_PILOT_SCENARIOS=true
```

The active tenant must also be explicitly marked as a demo tenant. Environment
flags alone are not enough. Set `tenants.is_demo_tenant = true` only for the
tenant used in controlled pilot demos; leave it `false` for customer/live
tenants.

DEMO-prefixed sample files are intended for demo tenants. Non-demo tenants
reject rows containing `DEMO-` plant, material, supplier, or inbound references
so sample data cannot quietly mix into live customer operations.

Run migrations:

```bash
cd apps/backend
PYTHONPATH=. .venv/bin/alembic upgrade head
```

Start the app using the normal local run flow documented in `docs/local_run_instructions.md`.

## Upload Flow

Go to:

```text
/dashboard/onboarding
```

Upload in this order:

1. Inventory continuity feed: `docs/demo-data/demo_stock_snapshots.csv`
2. Inbound continuity feed: `docs/demo-data/demo_inbound_shipments.csv`
3. Continuity threshold feed: `docs/demo-data/demo_continuity_thresholds.csv`

After each upload, pause on the result panel and say:

“This is the trust checkpoint. OpsDeck is not silently importing rows. It shows rows detected, accepted, rejected, records created or updated, plants, materials, inbound references, supplier names, and warnings.”

Point out:

- Rows detected
- Accepted/rejected rows
- Plants detected
- Materials detected
- Inbound rows detected
- Reliability sources
- Next recommended action

If a reliability source warning appears, explain:

“The shipment row is accepted, but OpsDeck is telling us the supplier text is not linked to a supplier master record yet. That weakens supplier-context reliability but does not block continuity visibility.”

## Risk Workspace Flow

Go to:

```text
/dashboard/risk-workspace
```

Use the Pilot scenario selector if enabled.

Recommended scenario order:

1. Ocean vessel delay
2. Inland movement failure
3. False safety: inbound exists but weak trust
4. Fresh verified inbound
5. Multi-inbound mixed protection

Explain the page in this order:

1. “What plant-material is under pressure?”
2. “How many days of usable cover remain?”
3. “When does safe cover breach?”
4. “Why is this escalating?”
5. “Which inbound exists physically?”
6. “Which inbound actually protects continuity?”
7. “What happens if nothing changes?”
8. “What should a human verify next?”

## Trusted Inbound Explanation

Use this language:

“OpsDeck does not make inbound quantity disappear. It separates physical inbound from trusted inbound protection. A shipment can exist physically but provide weak protection if ETA, freshness, tracking, or supplier-context confidence is weak.”

Good customer-friendly phrasing:

- “Physical inbound exists.”
- “Trusted protection is partial.”
- “Visibility is stale.”
- “This inbound should be verified before operations rely on it.”

Avoid:

- “Material is missing.”
- “Order more now.”
- “Replace supplier automatically.”

## Why This Is Not ERP Replacement

Say:

“ERP is the system of record. OpsDeck is the continuity reasoning layer. It reads ERP exports, shipment trackers, stock files, and threshold assumptions, then explains whether operations can trust current cover and inbound protection.”

The point is not to create purchase orders. The point is to catch continuity fragility before firefighting starts.

## Rollback And Reprocess

From the onboarding upload history:

- Use “View import detail” to show what a job touched.
- Use “Rollback this import” only for demo cleanup or a deliberate correction.
- Explain that rollback is job-specific and only deletes records created by that import where safe.
- Use “Reprocess” to show the same stored file can be loaded again without duplicate explosion.

Tenant-wide clear still exists for local reset, but job-specific rollback is the safer pilot path.

## Objections

**“We already have SAP.”**

“Good. OpsDeck is not replacing it. It sits above SAP exports, shipment trackers, and plant files to explain continuity risk and weak inbound protection.”

**“Is this AI?”**

“No. The pilot logic shown here is deterministic and explainable. The value is trustable operational reasoning, not black-box prediction.”

**“Will this auto-order material?”**

“No. Recommendations are human-led checks: validate ETA, confirm inland movement, verify supplier dispatch, review reserve usage.”

**“What if the file is messy?”**

“OpsDeck shows mapping confidence, row rejection reasons, accepted/rejected counts, and what it understood. It should never silently fail.”

## Success Signals To Listen For

The demo is landing if the customer says:

- “This is exactly where our tracker lies to us.”
- “We need to know which inbound is actually protective.”
- “Can we upload our real stock and inbound file?”
- “This would help our morning operating review.”

## Known Demo Limits

- Demo CSVs do not create supplier master records; supplier names are accepted as reliability-source text.
- Product/process dependency configuration is separate and not included in these CSV files.
- Risk generation timing depends on the currently loaded tenant state and selected pilot scenario.
- Exact update rollback is intentionally conservative: created records are deleted where safe, updated pre-existing records are preserved.
