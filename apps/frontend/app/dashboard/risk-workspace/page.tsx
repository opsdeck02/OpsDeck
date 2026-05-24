import {
  Activity,
  AlertTriangle,
  Boxes,
  Clock3,
  GitBranch,
  PackageCheck,
  ShieldCheck,
  Truck,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { DailyBriefButton } from "@/components/reports/daily-brief-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getRiskWorkspace,
  getSignalRisks,
  getTenantPlan,
  type RiskWorkspaceResponse,
  type SignalInventoryContinuity,
  type SignalRelationshipGraph,
  type SignalRiskCandidate,
  type SignalShipmentContinuity,
  type SignalTimelineEntry,
} from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = {
  scenario?: string;
  walkthrough?: string;
  risk_type?: string;
  plant_reference?: string;
  material_reference?: string;
  shipment_reference?: string;
  severity?: string;
};

const PILOT_SCENARIOS = [
  {
    value: "ocean_vessel_delay",
    label: "Ocean vessel delay",
    note:
      "Shows how ETA drift weakens inbound protection even when material is physically on the way.",
  },
  {
    value: "inland_movement_failure",
    label: "Inland movement failure",
    note: "Shows why material in-country may still not protect plant continuity.",
  },
  {
    value: "false_safety",
    label: "False safety: inbound exists but weak trust",
    note: "Shows why ERP/inbound quantity alone is not enough if trust is weak.",
  },
  {
    value: "fresh_verified_inbound",
    label: "Fresh verified inbound",
    note: "Shows how verified inbound can stabilize tight cover.",
  },
  {
    value: "multi_inbound_mixed_protection",
    label: "Multi-inbound mixed protection",
    note: "Shows how different inbound rows can carry different protective value.",
  },
];

const PILOT_SCENARIOS_ENABLED =
  process.env.NEXT_PUBLIC_ENABLE_PILOT_SCENARIOS === "true";

export default async function CriticalRiskWorkspacePage({
  searchParams,
}: {
  searchParams?: SearchParams;
}) {
  const tenantPlan = await getTenantPlan();
  const demoControlsEnabled =
    PILOT_SCENARIOS_ENABLED &&
    Boolean(
      tenantPlan?.is_demo_tenant &&
        tenantPlan.capabilities?.pilot_scenarios,
    );
  const walkthroughControlsEnabled = true;
  const activeScenario = demoControlsEnabled ? searchParams?.scenario : undefined;
  const walkthroughActive =
    walkthroughControlsEnabled && isWalkthroughActive(searchParams);
  const workspace = await getRiskWorkspace({
    scenario: activeScenario,
    risk_type: searchParams?.risk_type,
    plant_reference: searchParams?.plant_reference,
    material_reference: searchParams?.material_reference,
    shipment_reference: searchParams?.shipment_reference,
    severity: searchParams?.severity,
    timeline_limit: 50,
    timeline_offset: 0,
  });
  const risks = activeScenario
    ? []
    : await getSignalRisks({ plant_reference: searchParams?.plant_reference });

  if (!workspace) {
    return <UnavailableState />;
  }

  return (
    <main className="grid w-full min-w-0 max-w-full gap-2.5 overflow-x-hidden">
      <WorkspaceFilters
        searchParams={searchParams}
        walkthroughActive={walkthroughActive}
        demoControlsEnabled={demoControlsEnabled}
        walkthroughControlsEnabled={walkthroughControlsEnabled}
      />
      {risks.length > 0 ? (
        <ExposureSelector risks={risks} selected={workspace.selected_risk} />
      ) : null}
      {workspace.is_demo_scenario ? (
        <DemoScenarioNotice
          workspace={workspace}
          walkthroughActive={walkthroughActive}
        />
      ) : null}

      {workspace.empty ? (
        <EmptyWorkspace />
      ) : (
        <WorkspaceContent
          workspace={workspace}
          walkthroughActive={walkthroughActive}
        />
      )}
    </main>
  );
}

function ExposureSelector({
  risks,
  selected,
}: {
  risks: SignalRiskCandidate[];
  selected: SignalRiskCandidate | null;
}) {
  const ordered = [...risks].sort(riskSortKey);
  return (
    <Card className="min-w-0 max-w-full overflow-hidden bg-card/90 shadow-panel">
      <CardHeader className="px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Active continuity exposures</CardTitle>
          <span className="text-xs font-semibold text-mutedForeground">
            {ordered.length} active
          </span>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid w-full min-w-0 max-w-full gap-1.5 lg:grid-cols-2 xl:grid-cols-4">
          {ordered.slice(0, 8).map((risk) => (
            <Link
              key={riskKey(risk)}
              href={riskWorkspaceHref(risk)}
              className={`block min-w-0 max-w-full overflow-hidden border-l-4 px-3 py-2 text-left ring-1 transition hover:bg-slate-50 ${
                isSelectedExposure(risk, selected)
                  ? "border-slate-950 bg-slate-50 ring-slate-300"
                  : `${severityBorder(risk.severity)} bg-white ring-slate-900/5`
              }`}
            >
              <div className="flex min-w-0 items-center justify-between gap-2">
                <SeverityBadge value={risk.severity} />
                <span className="truncate text-xs font-semibold text-mutedForeground">
                  {exposureTiming(risk)}
                </span>
              </div>
              <div className="mt-1.5 flex min-w-0 items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold">
                  {risk.material_reference ?? "Unknown material"}
                </p>
                <p className="shrink-0 text-xs text-mutedForeground">
                  {risk.plant_reference ?? "Unknown plant"}
                </p>
              </div>
              <p className="mt-1 truncate text-xs font-medium text-slate-600">
                {formatLabel(risk.risk_type)}
              </p>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function WorkspaceContent({
  workspace,
  walkthroughActive,
}: {
  workspace: RiskWorkspaceResponse;
  walkthroughActive: boolean;
}) {
  const risk = workspace.selected_risk;
  const inventory = primaryInventory(workspace);

  return (
    <>
      <section className="grid min-w-0 items-start gap-2.5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">
        <div className="grid h-fit min-w-0 content-start gap-2.5">
          {walkthroughActive ? (
            <WalkthroughNote>
              This shows the plant-material combination most likely to create
              continuity pressure.
            </WalkthroughNote>
          ) : null}
          <OperationalRiskHero workspace={workspace} inventory={inventory} />
          {walkthroughActive ? (
            <WalkthroughNote>
              This explains the operational signals causing the risk, not just a
              generic score.
            </WalkthroughNote>
          ) : null}
          <WhyThisMatters workspace={workspace} />
        </div>

        <div className="grid h-fit min-w-0 content-start gap-2.5">
          {walkthroughActive ? (
            <WalkthroughNote>
              This translates current signals into likely operational consequence.
            </WalkthroughNote>
          ) : null}
          <IfNothingChanges workspace={workspace} inventory={inventory} />
          {walkthroughActive ? (
            <WalkthroughNote>
              These are human-led operational actions, not automated procurement.
            </WalkthroughNote>
          ) : null}
          <RecommendedActions risk={risk} />
          {walkthroughActive ? (
            <WalkthroughNote>
              This separates physical inbound from trusted inbound. An inbound
              shipment only protects continuity if timing, freshness, and
              confidence are acceptable.
            </WalkthroughNote>
          ) : null}
          <InboundProtectionQuality workspace={workspace} inventory={inventory} />
        </div>
      </section>

      <details className="min-w-0 max-w-full overflow-hidden rounded-lg border bg-white/70 p-3 text-sm ring-1 ring-slate-900/5">
        <summary className="cursor-pointer font-semibold text-slate-700">
          Deep operational context
          <span className="ml-2 text-xs font-normal text-mutedForeground">
            trust, signal chain, and connected dependencies
          </span>
        </summary>
        <div className="mt-3 grid gap-2.5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <OperationalTrustSummary risk={risk} />
          <ContinuitySummary
            inventory={workspace.inventory_continuity}
            shipments={workspace.shipment_continuity}
          />
        </div>
        <div className="mt-2.5 grid gap-2.5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <TimelinePanel timeline={workspace.timeline} />
          <RelationshipPanel graph={workspace.context_graph} />
        </div>
      </details>
    </>
  );
}

function OperationalRiskHero({
  workspace,
  inventory,
}: {
  workspace: RiskWorkspaceResponse;
  inventory: SignalInventoryContinuity | null;
}) {
  const risk = workspace.selected_risk;
  const exposure = workspace.exposure;
  const breachDays = exposure?.days_until_exposure ?? risk?.days_of_cover ?? null;
  const threshold = inventory?.threshold_days ?? null;
  const trustedInbound = inventory?.trusted_inbound_protection_mt ?? inventory?.trusted_inbound_quantity;
  const physicalInbound = inventory?.physical_inbound_quantity_mt ?? inventory?.inbound_committed_quantity;
  const coverDays = risk?.days_of_cover ?? inventory?.days_of_cover;
  const usableStock = displayQuantity(inventory?.usable_quantity, inventory?.unit);
  const confidence =
    risk?.operational_trust?.operational_trust_score ??
    inventory?.visibility_confidence ??
    workspace.trust_summary?.lowest_confidence_score;

  return (
    <Card className={`h-fit min-w-0 max-w-full self-start overflow-hidden ${workspaceTone(risk?.severity)}`}>
      <CardContent className="p-4 text-white">
        <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,0.42fr)_minmax(0,0.58fr)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge value={risk?.severity ?? "unknown"} />
              {exposure ? (
                <Badge className="bg-white/12 text-white ring-1 ring-white/15">
                  {formatLabel(exposure.exposure_level)}
                </Badge>
              ) : null}
            </div>
            <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-white/55">
              Current usable cover
            </p>
            <p className="mt-1 break-words text-4xl font-semibold leading-none tracking-tight sm:text-5xl 2xl:text-6xl">
              {displayDays(coverDays)}
            </p>
            <p className="mt-2 text-sm leading-5 text-white/65">
              {usableStock} usable stock
            </p>
          </div>

          <div className="grid min-w-0 content-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="bg-white/12 text-white ring-1 ring-white/15">
                  {formatLabel(risk?.risk_type ?? "continuity risk")}
                </Badge>
                {risk?.shipment_reference ? (
                  <Badge className="bg-white/12 text-white ring-1 ring-white/15">
                    Inbound {risk.shipment_reference}
                  </Badge>
                ) : null}
              </div>
              <CardTitle className="mt-2 max-w-3xl text-2xl tracking-tight">
                {operationalHeadline(risk, exposure)}
              </CardTitle>
              <p className="mt-1 max-w-3xl text-sm leading-5 text-white/65">
                {contextTitle(risk?.material_reference, risk?.plant_reference)}
              </p>
            </div>

            <div className="grid min-w-0 gap-2 sm:grid-cols-3">
              <SignalMetric
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Safe threshold"
                value={displayDays(threshold)}
                helper={safeCoverHelper(breachDays)}
                tone="warning"
              />
              <SignalMetric
                icon={<Truck className="h-4 w-4" />}
                label="Trusted inbound"
                value={displayQuantity(trustedInbound, inventory?.unit)}
                helper={`${displayQuantity(physicalInbound, inventory?.unit)} physical`}
                tone={trustedInboundTone(inventory)}
              />
              <SignalMetric
                icon={<ShieldCheck className="h-4 w-4" />}
                label="Confidence"
                value={displayPercent(confidence)}
                helper={formatLabel(risk?.operational_trust?.risk_precision_band ?? "calibrated context")}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function IfNothingChanges({
  workspace,
  inventory,
}: {
  workspace: RiskWorkspaceResponse;
  inventory: SignalInventoryContinuity | null;
}) {
  const risk = workspace.selected_risk;
  const exposure = workspace.exposure;
  const impact = risk?.operational_interruption_impact;
  const items = [
    safeBreachStatement(workspace, inventory),
    interruptionStatement(impact),
    inboundStabilityStatement(workspace, inventory),
  ].filter(Boolean) as string[];

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Clock3 className="h-5 w-5 text-pressure-red" />
          <CardTitle>If nothing changes</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid gap-1.5">
          {items.length > 0 ? (
            items.map((item) => (
              <div
                key={item}
                className="rounded-lg bg-slate-50 px-3 py-2 text-sm font-medium leading-5 ring-1 ring-slate-900/5"
              >
                {item}
              </div>
            ))
          ) : (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              Future consequence is not available for this risk yet.
            </p>
          )}
          {exposure?.estimated_exposure_date ? (
            <ContextPill
              label="Expected breach timing"
              value={formatDate(exposure.estimated_exposure_date)}
            />
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendedActions({ risk }: { risk: SignalRiskCandidate | null }) {
  const actions = (risk?.operational_recommendations ?? []).slice(0, 4);
  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center gap-2">
          <PackageCheck className="h-5 w-5 text-primary" />
          <CardTitle>Recommended next actions</CardTitle>
        </div>
        <p className="text-xs leading-5 text-mutedForeground">
          Human-led operational checks only. OpsDeck does not create purchase orders or
          replace suppliers automatically.
        </p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid gap-1.5">
          {actions.length > 0 ? (
            actions.map((action) => (
              <div
                key={`${action.action_type}-${action.urgency}`}
                className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-900/5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{actionLabel(action.action_type)}</p>
                  <Badge variant="outline">{formatLabel(action.urgency)}</Badge>
                </div>
                <p className="mt-1.5 text-sm leading-5 text-mutedForeground">
                  {action.operational_reason}
                </p>
              </div>
            ))
          ) : (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No operational action guidance returned for this selected risk.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function WorkspaceFilters({
  searchParams,
  walkthroughActive,
  demoControlsEnabled,
  walkthroughControlsEnabled,
}: {
  searchParams?: SearchParams;
  walkthroughActive: boolean;
  demoControlsEnabled: boolean;
  walkthroughControlsEnabled: boolean;
}) {
  return (
    <Card className="min-w-0 max-w-full overflow-hidden bg-card/90 shadow-panel">
      <CardHeader className="px-4 py-3">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle>Continuity risk workspace</CardTitle>
            <p className="mt-1 text-sm text-mutedForeground">
              {searchParams?.plant_reference
                ? `Viewing continuity for ${searchParams.plant_reference}.`
                : demoControlsEnabled && searchParams?.scenario
                  ? "Viewing a controlled pilot scenario."
                : "Viewing continuity for All plants."}
            </p>
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {walkthroughControlsEnabled ? (
              <Link
                href={walkthroughHref(
                  searchParams,
                  !walkthroughActive,
                  demoControlsEnabled,
                )}
                className={`rounded-lg px-3 py-2 text-sm font-semibold ring-1 transition ${
                  walkthroughActive
                    ? "bg-slate-950 text-white ring-slate-950"
                    : "bg-white text-slate-700 ring-slate-900/10 hover:bg-slate-50"
                }`}
              >
                {walkthroughActive ? "Hide walkthrough" : "Walkthrough"}
              </Link>
            ) : null}
            <DailyBriefButton />
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <form className="flex w-full min-w-0 max-w-full flex-wrap gap-2">
          {walkthroughActive ? (
            <input type="hidden" name="walkthrough" value="1" />
          ) : null}
          {demoControlsEnabled ? (
            <div className="grid min-w-0 flex-1 basis-56 gap-1">
              <label
                htmlFor="scenario"
                className="text-xs font-semibold uppercase tracking-wide text-mutedForeground"
              >
                Pilot scenario
              </label>
              <select
                id="scenario"
                name="scenario"
                defaultValue={searchParams?.scenario ?? ""}
                className="w-full min-w-0 rounded-lg border bg-card px-3 py-2 text-sm"
              >
                <option value="">Live workspace</option>
                {PILOT_SCENARIOS.map((scenario) => (
                  <option key={scenario.value} value={scenario.value}>
                    {scenario.label}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <input
            name="plant_reference"
            defaultValue={searchParams?.plant_reference ?? ""}
            placeholder="Plant reference"
            className="min-w-0 flex-1 basis-36 rounded-lg border bg-card px-3 py-2 text-sm"
          />
          <input
            name="material_reference"
            defaultValue={searchParams?.material_reference ?? ""}
            placeholder="Material reference"
            className="min-w-0 flex-1 basis-36 rounded-lg border bg-card px-3 py-2 text-sm"
          />
          <input
            name="shipment_reference"
            defaultValue={searchParams?.shipment_reference ?? ""}
            placeholder="Inbound reference"
            className="min-w-0 flex-1 basis-36 rounded-lg border bg-card px-3 py-2 text-sm"
          />
          <input
            name="risk_type"
            defaultValue={searchParams?.risk_type ?? ""}
            placeholder="Continuity risk"
            className="min-w-0 flex-1 basis-36 rounded-lg border bg-card px-3 py-2 text-sm"
          />
          <select
            name="severity"
            defaultValue={searchParams?.severity ?? ""}
            className="min-w-0 flex-1 basis-32 rounded-lg border bg-card px-3 py-2 text-sm"
          >
            <option value="">Any severity</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <button
            type="submit"
            className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground"
          >
            Apply
          </button>
        </form>
      </CardContent>
    </Card>
  );
}

function DemoScenarioNotice({
  workspace,
  walkthroughActive,
}: {
  workspace: RiskWorkspaceResponse;
  walkthroughActive: boolean;
}) {
  const scenarioNote = scenarioWalkthroughNote(workspace.scenario_key);

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-950">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">
          {workspace.scenario_label ?? "Pilot demo scenario"}
        </span>
        <Badge className="bg-amber-100 text-amber-900 ring-1 ring-amber-200">
          Demo data
        </Badge>
      </div>
      <p className="mt-1 leading-5">
        {workspace.demo_data_notice ??
          "Pilot demo scenario - seeded demo data, not live customer operations."}
      </p>
      {walkthroughActive && scenarioNote ? (
        <p className="mt-2 rounded-md bg-white/60 px-2.5 py-1.5 text-xs leading-5 ring-1 ring-amber-200/70">
          You are viewing a controlled pilot scenario designed to demonstrate:
          {" "}
          {scenarioNote}
        </p>
      ) : null}
    </div>
  );
}

function WalkthroughNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs leading-5 text-slate-600">
      {children}
    </div>
  );
}

function WhyThisMatters({ workspace }: { workspace: RiskWorkspaceResponse }) {
  const explainability = workspace.explainability;
  const reasonChain =
    explainability?.reason_chain ?? workspace.selected_risk?.rule_reasons ?? [];
  const concreteSignals = escalatingSignals(workspace, reasonChain);

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-pressure-red" />
          <CardTitle>Why this is escalating</CardTitle>
        </div>
        <p className="text-sm leading-5 text-mutedForeground">
          Operational signals that explain why this plant-material context is becoming
          fragile.
        </p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="mb-2 grid gap-1.5 sm:grid-cols-2">
          <ContextPill
            label="Primary driver"
            value={driverLabel(explainability?.primary_driver)}
          />
          <ContextPill
            label="Continuity risk"
            value={formatLabel(workspace.selected_risk?.risk_type)}
          />
        </div>
        <div className="mb-3 grid gap-1.5 sm:grid-cols-2">
          {concreteSignals.slice(0, 6).map((signal) => (
            <div
              key={signal}
              className="rounded-lg bg-white px-3 py-2 text-sm font-medium leading-5 ring-1 ring-slate-900/5"
            >
              {signal}
            </div>
          ))}
        </div>
        <div className="relative space-y-0 pl-3">
          <div className="absolute bottom-6 left-[24px] top-6 w-px bg-gradient-to-b from-red-300 via-amber-300 to-slate-200" />
          {reasonChain.slice(0, 6).map((reason, index) => (
            <div
              key={`${reason}-${index}`}
              className="relative flex gap-2.5 pb-3"
            >
              <span
                className={`z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${causalDotClass(index, reasonChain.length)}`}
              >
                {index + 1}
              </span>
              <div className="min-w-0 rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-900/5">
                <p className="text-sm font-medium leading-5">{reason}</p>
              </div>
            </div>
          ))}
          {reasonChain.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No causal signal chain was returned for this selected exposure.
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function InboundProtectionQuality({
  workspace,
  inventory,
}: {
  workspace: RiskWorkspaceResponse;
  inventory: SignalInventoryContinuity | null;
}) {
  const shipmentQuantities = shipmentQuantityByReference(workspace);
  const aggregatePhysical =
    inventory?.physical_inbound_quantity_mt ?? inventory?.inbound_committed_quantity;
  const aggregateTrusted =
    inventory?.trusted_inbound_protection_mt ?? inventory?.trusted_inbound_quantity;
  const aggregateUncertain =
    inventory?.visibility_uncertain_quantity_mt ?? inventory?.uncertain_inbound_quantity;

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Truck className="h-5 w-5 text-pressure-amber" />
          <CardTitle>Inbound protection quality</CardTitle>
        </div>
        <p className="text-sm leading-5 text-mutedForeground">
          Separates physical inbound from the portion OpsDeck can trust for continuity
          protection.
        </p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="mb-2 grid gap-1.5 sm:grid-cols-3">
          <ContextPill
            label="Physical inbound exists"
            value={displayQuantity(aggregatePhysical, inventory?.unit)}
          />
          <ContextPill
            label="Trusted inbound"
            value={displayQuantity(aggregateTrusted, inventory?.unit)}
          />
          <ContextPill
            label="Visibility uncertainty"
            value={displayQuantity(aggregateUncertain, inventory?.unit)}
          />
        </div>
        <div className="space-y-1.5">
          {workspace.shipment_continuity.slice(0, 4).map((shipment) => (
            <InboundProtectionRow
              key={shipment.shipment_reference}
              shipment={shipment}
              inventory={inventory}
              quantity={shipmentQuantities.get(shipment.shipment_reference)}
              totalShipments={workspace.shipment_continuity.length}
            />
          ))}
          {workspace.shipment_continuity.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No linked inbound movement returned for this selected risk.
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function InboundProtectionRow({
  shipment,
  inventory,
  quantity,
  totalShipments,
}: {
  shipment: SignalShipmentContinuity;
  inventory: SignalInventoryContinuity | null;
  quantity?: string;
  totalShipments: number;
}) {
  const quality = inboundProtectionLabel(shipment);
  const physicalValue = shipment.physical_quantity ?? quantity;
  const trustedValue =
    shipment.protective_quantity ??
    shipment.trusted_quantity ??
    (totalShipments === 1
      ? inventory?.trusted_inbound_protection_mt ?? inventory?.trusted_inbound_quantity
      : null);

  return (
    <div className={`rounded-lg p-2.5 ring-1 ${quality.className}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{shipment.shipment_reference}</p>
          <p className="mt-1 text-xs text-mutedForeground">
            {formatLabel(shipment.movement_condition ?? shipment.current_milestone ?? shipment.status)}
          </p>
        </div>
        <Badge variant="outline">{quality.label}</Badge>
      </div>
      <div className="mt-2 grid gap-1.5 text-sm sm:grid-cols-3">
        <span>Trust {formatLabel(shipment.trust_level ?? "unknown")}</span>
        <span>ETA {formatLabel(shipment.eta_status ?? "unknown")}</span>
        <span>Freshness {formatLabel(shipment.freshness_status ?? shipment.tracking_freshness_status)}</span>
      </div>
      <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
        <ContextPill
          label="Physical inbound"
          value={displayQuantity(physicalValue, inventory?.unit)}
        />
        <ContextPill
          label="Protective value"
          value={
            trustedValue
              ? displayQuantity(trustedValue, inventory?.unit)
              : quality.protectiveValue
          }
        />
      </div>
      {shipment.protection_explanation ?? quality.reason ? (
        <p className="mt-2 text-sm leading-5 text-mutedForeground">
          {shipment.protection_explanation ?? quality.reason}
        </p>
      ) : null}
    </div>
  );
}

function OperationalTrustSummary({
  risk,
}: {
  risk: SignalRiskCandidate | null;
}) {
  const completeness = risk?.configuration_completeness;
  const operationalTrust = risk?.operational_trust;
  const hasTrustContext = completeness || operationalTrust;
  const missing = completeness?.missing_assumptions ?? [];
  const degraded = completeness?.degraded_reasoning_areas ?? [];
  const penalties = operationalTrust?.trust_penalties ?? [];
  const boosts = operationalTrust?.trust_boosts ?? [];

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <CardTitle>Operational Trust</CardTitle>
          </div>
          {operationalTrust ? (
            <BandBadge value={operationalTrust.risk_precision_band} />
          ) : null}
        </div>
        <p className="text-xs leading-5 text-mutedForeground">
          Shows how complete the operational assumptions are behind this risk.
          Low trust does not mean the risk is false; it means OpsDeck has less
          calibrated context.
        </p>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {hasTrustContext ? (
          <div className="grid gap-2">
            <div className="grid gap-1.5 sm:grid-cols-2">
              <ContextPill
                label="Operational Trust"
                value={
                  operationalTrust
                    ? `${formatNumber(operationalTrust.operational_trust_score)}% · ${formatLabel(operationalTrust.risk_precision_band)}`
                    : "Unknown"
                }
              />
              <ContextPill
                label="Configuration Completeness"
                value={
                  completeness
                    ? `${formatNumber(completeness.overall_completeness_score)}% · ${formatLabel(completeness.operational_confidence_band)}`
                    : "Unknown"
                }
              />
              <ContextPill
                label="Reasoning strength"
                value={formatLabel(operationalTrust?.reasoning_strength)}
              />
              <ContextPill
                label="Signal coverage"
                value={
                  operationalTrust
                    ? `${operationalTrust.trusted_signal_count} trusted · ${operationalTrust.weak_signal_count} weak · ${operationalTrust.missing_signal_count} missing`
                    : "Unknown"
                }
              />
            </div>

            <CompactSignalList
              title="Missing assumptions"
              items={missing}
              empty="No missing assumptions returned."
            />
            <CompactSignalList
              title="Trust penalties"
              items={[...penalties, ...degraded.map((area) => `${formatLabel(area)} degraded`)]}
              empty="No trust penalties returned."
            />
            <CompactSignalList
              title="Trust boosts"
              items={boosts}
              empty="No trust boosts returned."
            />
          </div>
        ) : (
          <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-mutedForeground ring-1 ring-slate-900/5">
            Operational trust context is not available for this risk yet.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CompactSignalList({
  title,
  items,
  empty,
}: {
  title: string;
  items: string[];
  empty: string;
}) {
  const visible = items.filter(Boolean).slice(0, 3);
  return (
    <div className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold text-mutedForeground">{title}</p>
      {visible.length > 0 ? (
        <ul className="mt-2 space-y-1.5 text-sm leading-5">
          {visible.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-mutedForeground">{empty}</p>
      )}
    </div>
  );
}

function ContinuitySummary({
  inventory,
  shipments,
}: {
  inventory: SignalInventoryContinuity[];
  shipments: SignalShipmentContinuity[];
}) {
  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center gap-2">
          <PackageCheck className="h-5 w-5 text-pressure-amber" />
          <CardTitle>Operational dependency context</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid gap-2">
          <div className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-900/5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Available cover</h3>
              <span className="text-xs font-semibold text-mutedForeground">
                {inventory.length} material contexts
              </span>
            </div>
            <div className="mt-2 grid gap-1.5 sm:grid-cols-3">
              {inventory.slice(0, 2).map((item) => (
                <InventoryBlock
                  key={`${item.plant_reference}-${item.material_reference}`}
                  item={item}
                />
              ))}
              {inventory.length === 0 ? (
                <p className="text-sm text-mutedForeground">
                  No plant/material cover context returned for this exposure.
                </p>
              ) : null}
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-900/5">
            <h3 className="font-semibold">Inbound continuity condition</h3>
            <div className="mt-2 space-y-1.5">
              {shipments.slice(0, 3).map((shipment) => (
                <ShipmentBlock
                  key={shipment.shipment_reference}
                  shipment={shipment}
                />
              ))}
              {shipments.length === 0 ? (
                <p className="text-sm text-mutedForeground">
                  No inbound dependency condition returned for this view.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TimelinePanel({
  timeline,
}: {
  timeline: RiskWorkspaceResponse["timeline"];
}) {
  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock3 className="h-5 w-5 text-primary" />
            <CardTitle>Continuity signal chain</CardTitle>
          </div>
          <Badge variant="outline">{timeline.total} signals</Badge>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="space-y-1.5">
          {timeline.items.map((entry) => (
            <TimelineEntry key={entry.event_id} entry={entry} />
          ))}
          {timeline.items.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No historical continuity signal chain detected.
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function RelationshipPanel({
  graph,
}: {
  graph: SignalRelationshipGraph | null;
}) {
  const nodeById = new Map((graph?.nodes ?? []).map((node) => [node.id, node]));
  const priorityNodes = [
    "shipment",
    "plant",
    "material",
    "supplier",
    "risk_candidate",
  ]
    .map((type) => ({
      type,
      nodes: (graph?.nodes ?? [])
        .filter((node) => node.type === type)
        .slice(0, 4),
    }))
    .filter((group) => group.nodes.length > 0);
  const priorityEdges = (graph?.edges ?? [])
    .filter((edge) => {
      const fromType = nodeById.get(edge.from_node_id)?.type;
      const toType = nodeById.get(edge.to_node_id)?.type;
      return [fromType, toType].some((type) =>
        [
          "shipment",
          "plant",
          "material",
          "supplier",
          "risk_candidate",
        ].includes(type ?? ""),
      );
    })
    .slice(0, 5);

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="px-4 py-3">
        <div className="flex items-center gap-2">
          <GitBranch className="h-5 w-5 text-primary" />
          <CardTitle>Connected operational context</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid gap-2">
          {priorityNodes.map((group) => (
            <div
              key={group.type}
              className="min-w-0 rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-900/5"
            >
              <p className="text-xs font-semibold text-mutedForeground">
                {formatLabel(group.type)}
              </p>
              <div className="mt-2 flex min-w-0 flex-wrap gap-2">
                {group.nodes.map((node) => (
                  <span
                    key={node.id}
                    className="max-w-full break-words rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-900/5"
                  >
                    {node.label}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {priorityNodes.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No connected operational dependency records returned.
            </p>
          ) : null}
          <div className="space-y-1.5">
            {priorityEdges.map((edge) => (
              <div
                key={`${edge.from_node_id}-${edge.relationship}-${edge.to_node_id}`}
                className="min-w-0 break-words rounded-lg bg-white px-3 py-2 text-sm ring-1 ring-slate-900/5"
              >
                <span className="font-medium">
                  {nodeById.get(edge.from_node_id)?.label ?? edge.from_node_id}
                </span>
                <span className="px-2 text-mutedForeground">
                  {formatLabel(edge.relationship)}
                </span>
                <span className="font-medium">
                  {nodeById.get(edge.to_node_id)?.label ?? edge.to_node_id}
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function InventoryBlock({ item }: { item: SignalInventoryContinuity }) {
  return (
    <>
      <ContextPill
        label="Usable quantity"
        value={`${formatNumber(item.usable_quantity)} ${item.unit}`}
      />
      <ContextPill
        label="Current usable cover"
        value={displayDays(item.days_of_cover)}
      />
      <ContextPill
        label="Trusted operating cover"
        value={displayDays(item.trusted_days_of_cover ?? item.days_of_cover)}
      />
      <ContextPill
        label="Trusted inbound protection"
        value={displayQuantity(item.trusted_inbound_protection_mt, item.unit)}
      />
      <ContextPill
        label="Visibility uncertainty"
        value={displayQuantity(item.visibility_uncertain_quantity_mt, item.unit)}
      />
      <ContextPill
        label="Cover confidence"
        value={
          item.cover_confidence_score
            ? `${formatNumber(item.cover_confidence_score)}`
            : "unknown"
        }
      />
      <ContextPill
        label="Daily consumption"
        value={`${formatNumber(item.daily_consumption_rate)} ${item.unit}`}
      />
      {item.trust_warnings.length > 0 ? (
    <div className="rounded-lg bg-amber-50 p-2.5 text-sm text-amber-900 ring-1 ring-amber-200 sm:col-span-3">
          <p className="font-semibold">Visibility weak</p>
          <ul className="mt-1 space-y-1">
            {item.trust_warnings.slice(0, 2).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

function ShipmentBlock({ shipment }: { shipment: SignalShipmentContinuity }) {
  return (
    <div
      className={`rounded-lg p-2.5 ring-1 ${shipment.status === "degraded" ? "bg-red-50 ring-red-200" : shipment.status === "watch" ? "bg-amber-50 ring-amber-200" : "bg-white ring-slate-900/5"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{shipment.shipment_reference}</p>
        <Badge variant="outline">{formatLabel(shipment.status)}</Badge>
      </div>
      <div className="mt-2 grid gap-1.5 text-sm sm:grid-cols-3">
        <span>ETA {formatDate(shipment.eta)}</span>
        <span>Slip {displayDays(shipment.eta_slip_days)}</span>
        <span>
          Visibility freshness {formatLabel(shipment.tracking_freshness_status)}
        </span>
      </div>
      <ul className="mt-2 space-y-1 text-sm text-mutedForeground">
        {shipment.continuity_reasons.slice(0, 3).map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function TimelineEntry({ entry }: { entry: SignalTimelineEntry }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-900/5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{entry.title}</p>
          <p className="mt-1 text-sm leading-5 text-mutedForeground">
            {entry.description}
          </p>
        </div>
        <span className="text-xs text-mutedForeground">
          {formatDate(entry.timestamp)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-slate-900/5">
          {formatLabel(entry.event_category)}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-slate-900/5">
          Signal reliability {displayPercent(entry.confidence_score)}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-slate-900/5">
          Freshness {formatLabel(entry.freshness_status)}
        </span>
        <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-slate-900/5">
          {formatLabel(entry.source_type)}
        </span>
      </div>
    </div>
  );
}

function SignalMetric({
  icon,
  label,
  value,
  helper,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  helper: string;
  tone?: "default" | "critical" | "warning";
}) {
  const toneClass =
    tone === "critical"
      ? "bg-red-50 text-red-950 ring-red-200"
      : tone === "warning"
        ? "bg-amber-50 text-amber-950 ring-amber-200"
        : "bg-white/95 text-slate-950 ring-white/25";
  const labelClass =
    tone === "default" ? "text-slate-600" : "text-mutedForeground";
  const helperClass =
    tone === "default" ? "text-slate-500" : "text-mutedForeground";
  return (
    <div className={`min-w-0 rounded-lg p-2.5 ring-1 ${toneClass}`}>
      <div className={`flex min-w-0 items-center gap-2 ${labelClass}`}>
        {icon}
        <p className="min-w-0 truncate text-xs font-semibold">{label}</p>
      </div>
      <p className="mt-1 break-words text-base font-semibold">{value}</p>
      <p className={`mt-1 text-xs ${helperClass}`}>{helper}</p>
    </div>
  );
}

function ContextPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-white px-3 py-1.5 ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold text-mutedForeground">{label}</p>
      <p className="mt-0.5 break-words text-sm font-semibold">{value}</p>
    </div>
  );
}

function SeverityBadge({ value }: { value: string }) {
  const className =
    value === "critical"
      ? "bg-red-500 text-white"
      : value === "high"
        ? "bg-amber-500 text-white"
        : value === "medium"
          ? "bg-blue-500 text-white"
          : "bg-slate-200 text-slate-700";
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-semibold ${className}`}
    >
      {value}
    </span>
  );
}

function BandBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const className =
    normalized === "high"
      ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
      : normalized === "moderate"
        ? "bg-blue-50 text-blue-800 ring-blue-200"
        : normalized === "low"
          ? "bg-amber-50 text-amber-900 ring-amber-200"
          : "bg-slate-100 text-slate-700 ring-slate-200";
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${className}`}>
      {formatLabel(value)}
    </span>
  );
}

function primaryInventory(workspace: RiskWorkspaceResponse) {
  const selected = workspace.selected_risk;
  return (
    workspace.inventory_continuity.find(
      (item) =>
        item.plant_reference === selected?.plant_reference &&
        item.material_reference === selected?.material_reference,
    ) ??
    workspace.context_graph?.summary.inventory_continuity ??
    workspace.inventory_continuity[0] ??
    null
  ) as SignalInventoryContinuity | null;
}

function operationalHeadline(
  risk: SignalRiskCandidate | null,
  exposure: RiskWorkspaceResponse["exposure"],
) {
  const days = exposure?.days_until_exposure ?? risk?.days_of_cover;
  const context = contextTitle(risk?.material_reference, risk?.plant_reference);
  if (risk?.risk_type === "projected_stockout") {
    return `Projected stockout risk for ${context}`;
  }
  if (risk?.risk_type === "inbound_delay_against_cover") {
    return `Inbound protection may not arrive before safe cover weakens`;
  }
  if (days) {
    return `Production continuity risk expected in ${formatNumber(days)} days`;
  }
  return `Production continuity risk for ${context}`;
}

function safeCoverHelper(value?: string | null) {
  if (!value) return "breach timing not available";
  return `safe cover breach expected in ${formatNumber(value)} days`;
}

function safeBreachStatement(
  workspace: RiskWorkspaceResponse,
  inventory: SignalInventoryContinuity | null,
) {
  const exposureDays = workspace.exposure?.days_until_exposure;
  const threshold = inventory?.threshold_days;
  if (exposureDays) {
    return `Safe threshold breach expected in ${formatNumber(exposureDays)} days.`;
  }
  if (workspace.selected_risk?.days_of_cover && threshold) {
    return `Current usable cover is ${displayDays(workspace.selected_risk.days_of_cover)} against a safe threshold of ${displayDays(threshold)}.`;
  }
  if (workspace.selected_risk?.projected_exhaustion_date) {
    return `Projected exhaustion is ${formatDate(workspace.selected_risk.projected_exhaustion_date)}.`;
  }
  return null;
}

function interruptionStatement(impact?: SignalRiskCandidate["operational_interruption_impact"]) {
  if (!impact) return null;
  if (impact.calculation_status !== "calculated") {
    return "Production interruption impact is not fully calibrated for this context.";
  }
  if (impact.estimated_interruption_hours) {
    return `If cover fails, estimated interruption window is ${formatNumber(impact.estimated_interruption_hours)} hours.`;
  }
  return "Operational interruption impact is calculated for this risk.";
}

function inboundStabilityStatement(
  workspace: RiskWorkspaceResponse,
  inventory: SignalInventoryContinuity | null,
) {
  const weakInbound =
    numberValue(inventory?.visibility_uncertain_quantity_mt) > 0 ||
    workspace.shipment_continuity.some((shipment) =>
      ["degraded", "watch"].includes(shipment.status),
    );
  if (weakInbound) {
    return "Inbound must stabilize before projected cover loss.";
  }
  if ((workspace.shipment_continuity.length ?? 0) > 0) {
    return "Inbound movement remains linked, but operations should keep timing validated.";
  }
  return null;
}

function escalatingSignals(
  workspace: RiskWorkspaceResponse,
  reasons: string[],
) {
  const signals = new Set<string>();
  const text = [
    ...reasons,
    ...workspace.shipment_continuity.flatMap((shipment) => shipment.continuity_reasons),
    ...(workspace.inventory_continuity[0]?.trust_warnings ?? []),
  ]
    .join(" ")
    .toLowerCase();
  const inventory = primaryInventory(workspace);
  if (text.includes("eta slipped") || text.includes("eta drift")) {
    signals.add("Vessel or inbound ETA slipped against plan.");
  }
  if (text.includes("inland") || text.includes("near_plant") || text.includes("gate_in")) {
    signals.add("Inland movement is not confirmed strongly enough.");
  }
  if (text.includes("supplier") && (text.includes("weak") || text.includes("insufficient"))) {
    signals.add("Supplier dispatch or reliability evidence is weak.");
  }
  if (text.includes("stale") || text.includes("critical visibility")) {
    signals.add("Last tracking update is stale for this movement context.");
  }
  if (workspace.selected_risk?.days_of_cover || inventory?.threshold_days) {
    signals.add("Usable cover is at or below the configured operating threshold.");
  }
  if (numberValue(inventory?.visibility_uncertain_quantity_mt) > 0) {
    signals.add("Inbound exists physically but is not fully trusted for protection.");
  }
  if (inventory?.daily_consumption_rate) {
    signals.add(`Consumption pressure is ${formatNumber(inventory.daily_consumption_rate)} ${inventory.unit}/day.`);
  }
  if (signals.size === 0) {
    signals.add("OpsDeck returned a continuity risk, but the causal signal detail is limited.");
  }
  return Array.from(signals);
}

function inboundProtectionLabel(shipment: SignalShipmentContinuity) {
  if (shipment.protective_value_label) {
    const label = shipment.protective_value_label;
    const level = shipment.trust_level ?? "";
    const className =
      level === "strong"
        ? "bg-emerald-50 ring-emerald-200"
        : level === "partial"
          ? "bg-amber-50 ring-amber-200"
          : level === "weak" || level === "not_protective"
            ? "bg-red-50 ring-red-200"
            : "bg-slate-100 ring-slate-200";
    return {
      label,
      protectiveValue: shipment.protective_quantity
        ? displayQuantity(shipment.protective_quantity)
        : "Not quantified",
      reason: shipment.trust_reason,
      className,
    };
  }
  const slip = numberValue(shipment.eta_slip_days);
  if (shipment.status === "degraded" || shipment.tracking_freshness_status === "critical") {
    return {
      label: "Weak protection",
      protectiveValue: "Reduced by visibility trust",
      reason: "ETA, milestone, or tracking condition is degraded.",
      className: "bg-red-50 ring-red-200",
    };
  }
  if (shipment.status === "watch" || shipment.tracking_freshness_status === "stale" || slip > 0) {
    return {
      label: "Partial protection",
      protectiveValue: "Partially trusted",
      reason: "Inbound exists, but timing or visibility needs operational validation.",
      className: "bg-amber-50 ring-amber-200",
    };
  }
  if (shipment.status === "unknown") {
    return {
      label: "Not currently protective",
      protectiveValue: "Not trusted yet",
      reason: "Shipment condition is missing enough context for trusted protection.",
      className: "bg-slate-100 ring-slate-200",
    };
  }
  return {
    label: "Strong protection",
    protectiveValue: "Trusted",
    reason: "Inbound timing and visibility are currently acceptable.",
    className: "bg-emerald-50 ring-emerald-200",
  };
}

function shipmentQuantityByReference(workspace: RiskWorkspaceResponse) {
  const quantities = new Map<string, string>();
  for (const node of workspace.context_graph?.nodes ?? []) {
    if (node.type !== "shipment") continue;
    const quantity = node.metadata.quantity_mt;
    if (quantity === null || quantity === undefined) continue;
    quantities.set(node.reference, String(quantity));
  }
  return quantities;
}

function trustedInboundTone(
  inventory: SignalInventoryContinuity | null,
): "default" | "critical" | "warning" {
  if (!inventory) return "default";
  const physical = numberValue(inventory.physical_inbound_quantity_mt);
  const trusted = numberValue(inventory.trusted_inbound_protection_mt);
  if (physical <= 0) return "default";
  const ratio = trusted / physical;
  if (ratio < 0.4) return "critical";
  if (ratio < 0.75) return "warning";
  return "default";
}

function actionLabel(value: string) {
  const labels: Record<string, string> = {
    monitor: "Monitor continuity position",
    verify_inbound: "Verify inbound status",
    validate_eta: "Validate ETA",
    expedite_inbound: "Expedite inbound recovery",
    escalate_supplier: "Escalate to supplier owner",
    review_recovery_plan: "Review recovery plan",
    activate_substitution: "Review substitution option",
    review_reserve_usage: "Review reserve usage",
    validate_tracking_visibility: "Increase tracking cadence",
    confirm_port_clearance: "Confirm port clearance",
    confirm_inland_movement: "Confirm inland movement allocation",
  };
  return labels[value] ?? formatLabel(value);
}

const severityRank: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function riskSortKey(left: SignalRiskCandidate, right: SignalRiskCandidate) {
  const severity =
    (severityRank[left.severity] ?? 99) - (severityRank[right.severity] ?? 99);
  if (severity !== 0) return severity;
  const leftDate = left.projected_exhaustion_date
    ? new Date(left.projected_exhaustion_date).getTime()
    : Number.POSITIVE_INFINITY;
  const rightDate = right.projected_exhaustion_date
    ? new Date(right.projected_exhaustion_date).getTime()
    : Number.POSITIVE_INFINITY;
  if (leftDate !== rightDate) return leftDate - rightDate;
  return riskKey(left).localeCompare(riskKey(right));
}

function riskKey(risk: SignalRiskCandidate) {
  return [
    risk.severity,
    risk.risk_type,
    risk.plant_reference ?? "",
    risk.material_reference ?? "",
    risk.shipment_reference ?? "",
  ].join("|");
}

function riskWorkspaceHref(risk: SignalRiskCandidate) {
  const params = new URLSearchParams();
  params.set("risk_type", risk.risk_type);
  params.set("severity", risk.severity);
  if (risk.plant_reference) params.set("plant_reference", risk.plant_reference);
  if (risk.material_reference)
    params.set("material_reference", risk.material_reference);
  if (risk.shipment_reference)
    params.set("shipment_reference", risk.shipment_reference);
  return `/dashboard/risk-workspace?${params.toString()}`;
}

function walkthroughHref(
  searchParams: SearchParams | undefined,
  enabled: boolean,
  includeScenario: boolean,
) {
  const params = new URLSearchParams();
  setParam(params, "scenario", includeScenario ? searchParams?.scenario : undefined);
  setParam(params, "plant_reference", searchParams?.plant_reference);
  setParam(params, "material_reference", searchParams?.material_reference);
  setParam(params, "shipment_reference", searchParams?.shipment_reference);
  setParam(params, "risk_type", searchParams?.risk_type);
  setParam(params, "severity", searchParams?.severity);
  if (enabled) params.set("walkthrough", "1");
  const query = params.toString();
  return query ? `/dashboard/risk-workspace?${query}` : "/dashboard/risk-workspace";
}

function setParam(
  params: URLSearchParams,
  key: string,
  value: string | undefined,
) {
  if (value) params.set(key, value);
}

function isWalkthroughActive(searchParams: SearchParams | undefined) {
  return PILOT_SCENARIOS_ENABLED && searchParams?.walkthrough === "1";
}

function scenarioWalkthroughNote(scenarioKey?: string | null) {
  return PILOT_SCENARIOS.find((scenario) => scenario.value === scenarioKey)?.note;
}

function isSelectedExposure(
  risk: SignalRiskCandidate,
  selected: SignalRiskCandidate | null,
) {
  if (!selected) return false;
  return riskKey(risk) === riskKey(selected);
}

function exposureTiming(risk: SignalRiskCandidate) {
  if (risk.days_of_cover !== null && risk.days_of_cover !== undefined) {
    return `${formatNumber(risk.days_of_cover)} days cover`;
  }
  if (risk.projected_exhaustion_date) {
    return formatDate(risk.projected_exhaustion_date);
  }
  return "timing unknown";
}

function workspaceTone(severity?: string | null) {
  if (severity === "critical") return "bg-slate-950 shadow-nerve";
  if (severity === "high") return "bg-slate-950 shadow-panel";
  return "bg-slate-900 shadow-panel";
}

function severityBorder(severity?: string | null) {
  if (severity === "critical") return "border-red-500";
  if (severity === "high") return "border-amber-500";
  if (severity === "medium") return "border-blue-500";
  return "border-slate-300";
}

function causalDotClass(index: number, length: number) {
  if (index === length - 1) return "bg-red-500 text-white";
  if (index > 0) return "bg-amber-400 text-slate-950";
  return "bg-blue-500 text-white";
}

function UnavailableState() {
  return (
    <Card className="min-w-0 max-w-full overflow-hidden bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Risk workspace unavailable</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-mutedForeground">
        OpsDeck could not load the risk workspace. Your signal engine data may
        still be available in other views.
      </CardContent>
    </Card>
  );
}

function EmptyWorkspace() {
  return (
    <Card className="min-w-0 max-w-full overflow-hidden bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>No active continuity risk matches this view</CardTitle>
      </CardHeader>
      <CardContent className="text-sm leading-6 text-mutedForeground">
        OpsDeck will show risks here when inventory, inbound movement, or data
        freshness signals indicate operational exposure.
      </CardContent>
    </Card>
  );
}

function contextTitle(material?: string | null, plant?: string | null) {
  if (material && plant) return `${material} at ${plant}`;
  if (material) return material;
  if (plant) return plant;
  return "Operational continuity risk";
}

function formatLabel(value?: string | null) {
  if (!value) return "Unknown";
  return value.replaceAll("_", " ");
}

function driverLabel(value?: string | null) {
  if (value === "inventory_continuity") return "Available cover";
  if (value === "shipment_continuity") return "Inbound continuity";
  if (value === "signal_trust") return "Continuity trust";
  if (value === "missing_operational_context")
    return "Missing operational context";
  return formatLabel(value);
}

function formatDate(value?: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatNumber(value?: string | null) {
  if (value === null || value === undefined) return "Unknown";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function displayDays(value?: string | null) {
  if (value === null || value === undefined) return "Unknown";
  return `${formatNumber(value)} days`;
}

function displayQuantity(value?: string | null, unit = "MT") {
  if (value === null || value === undefined) return "Unknown";
  return `${formatNumber(value)} ${unit}`;
}

function displayDaysUntil(value?: string | null) {
  if (!value) return "exposure timing unknown";
  return `${formatNumber(value)} days until exposure`;
}

function displayPercent(value?: string | null) {
  if (!value) return "Unknown";
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric <= 1) {
    return `${formatNumber(String(numeric * 100))}%`;
  }
  return `${formatNumber(value)}%`;
}

function numberValue(value?: string | null) {
  if (value === null || value === undefined) return 0;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}
