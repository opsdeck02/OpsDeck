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

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getRiskWorkspace,
  type RiskWorkspaceResponse,
  type SignalInventoryContinuity,
  type SignalRelationshipGraph,
  type SignalShipmentContinuity,
  type SignalTimelineEntry,
} from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = {
  risk_type?: string;
  plant_reference?: string;
  material_reference?: string;
  shipment_reference?: string;
  severity?: string;
};

export default async function CriticalRiskWorkspacePage({
  searchParams,
}: {
  searchParams?: SearchParams;
}) {
  const workspace = await getRiskWorkspace({
    risk_type: searchParams?.risk_type,
    plant_reference: searchParams?.plant_reference,
    material_reference: searchParams?.material_reference,
    shipment_reference: searchParams?.shipment_reference,
    severity: searchParams?.severity,
    timeline_limit: 50,
    timeline_offset: 0,
  });

  if (!workspace) {
    return <UnavailableState />;
  }

  return (
    <main className="grid min-w-0 gap-3">
      <WorkspaceFilters searchParams={searchParams} />

      {workspace.empty ? (
        <EmptyWorkspace />
      ) : (
        <WorkspaceContent workspace={workspace} />
      )}
    </main>
  );
}

function WorkspaceContent({ workspace }: { workspace: RiskWorkspaceResponse }) {
  const risk = workspace.selected_risk;
  const exposure = workspace.exposure;
  const explainability = workspace.explainability;

  return (
    <>
      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.55fr)]">
        <Card className={`overflow-hidden ${workspaceTone(risk?.severity)}`}>
          <CardHeader className="text-white">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge value={risk?.severity ?? "unknown"} />
              <Badge className="bg-white/12 text-white ring-1 ring-white/15">
                {formatLabel(risk?.risk_type ?? "risk")}
              </Badge>
              {exposure ? (
                <Badge className="bg-white/12 text-white ring-1 ring-white/15">
                  {formatLabel(exposure.exposure_level)} exposure
                </Badge>
              ) : null}
            </div>
            <CardTitle className="mt-2 text-2xl tracking-tight">
              {contextTitle(risk?.material_reference, risk?.plant_reference)}
            </CardTitle>
            <p className="max-w-3xl text-sm leading-5 text-white/68">
              {exposure?.operational_reason ??
                explainability?.summary ??
                "Operational risk context is available for review."}
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2.5 md:grid-cols-2 2xl:grid-cols-4">
              <SignalMetric
                icon={<Boxes className="h-4 w-4" />}
                label="Cover"
                value={displayDays(risk?.days_of_cover)}
                helper="available"
              />
              <SignalMetric
                icon={<Clock3 className="h-4 w-4" />}
                label="Failure window"
                value={formatDate(
                  exposure?.estimated_exposure_date ??
                    risk?.projected_exhaustion_date,
                )}
                helper={displayDaysUntil(exposure?.days_until_exposure)}
                tone="critical"
              />
              <SignalMetric
                icon={<Truck className="h-4 w-4" />}
                label="Movement"
                value={
                  risk?.shipment_reference ??
                  exposure?.shipment_reference ??
                  "Not linked"
                }
                helper={formatLabel(
                  risk?.continuity_status ?? "movement context",
                )}
                tone={risk?.continuity_status === "degraded" ? "warning" : "default"}
              />
              <SignalMetric
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Why exposed"
                value={formatLabel(exposure?.exposure_basis ?? "unknown")}
                helper="operational exposure"
              />
            </div>
          </CardContent>
        </Card>

        <TrustSummary workspace={workspace} />
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <WhyThisMatters workspace={workspace} />
        <ContinuitySummary
          inventory={workspace.inventory_continuity}
          shipments={workspace.shipment_continuity}
        />
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <TimelinePanel timeline={workspace.timeline} />
        <RelationshipPanel graph={workspace.context_graph} />
      </section>
    </>
  );
}

function WorkspaceFilters({ searchParams }: { searchParams?: SearchParams }) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Critical risk workspace</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3 md:grid-cols-3 xl:grid-cols-[1fr_1fr_1fr_1fr_160px_auto]">
          <input
            name="plant_reference"
            defaultValue={searchParams?.plant_reference ?? ""}
            placeholder="Plant reference"
            className="rounded-xl border bg-card px-3 py-2 text-sm"
          />
          <input
            name="material_reference"
            defaultValue={searchParams?.material_reference ?? ""}
            placeholder="Material reference"
            className="rounded-xl border bg-card px-3 py-2 text-sm"
          />
          <input
            name="shipment_reference"
            defaultValue={searchParams?.shipment_reference ?? ""}
            placeholder="Shipment reference"
            className="rounded-xl border bg-card px-3 py-2 text-sm"
          />
          <input
            name="risk_type"
            defaultValue={searchParams?.risk_type ?? ""}
            placeholder="Risk category"
            className="rounded-xl border bg-card px-3 py-2 text-sm"
          />
          <select
            name="severity"
            defaultValue={searchParams?.severity ?? ""}
            className="rounded-xl border bg-card px-3 py-2 text-sm"
          >
            <option value="">Any severity</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <button
            type="submit"
            className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground"
          >
            Apply
          </button>
        </form>
      </CardContent>
    </Card>
  );
}

function WhyThisMatters({ workspace }: { workspace: RiskWorkspaceResponse }) {
  const explainability = workspace.explainability;
  const reasonChain =
    explainability?.reason_chain ?? workspace.selected_risk?.rule_reasons ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-pressure-red" />
          <CardTitle>Why this is becoming risky</CardTitle>
        </div>
        <p className="text-sm leading-5 text-mutedForeground">
          {explainability?.summary ??
            "OpsDeck does not have enough signal detail to explain this risk yet."}
        </p>
      </CardHeader>
      <CardContent>
        <div className="mb-3 grid gap-2 sm:grid-cols-2">
          <ContextPill
            label="Primary driver"
            value={driverLabel(explainability?.primary_driver)}
          />
          <ContextPill
            label="Risk category"
            value={formatLabel(workspace.selected_risk?.risk_type)}
          />
        </div>
        <div className="relative space-y-0 pl-3">
          <div className="absolute bottom-6 left-[24px] top-6 w-px bg-gradient-to-b from-red-300 via-amber-300 to-slate-200" />
          {reasonChain.map((reason, index) => (
            <div
              key={`${reason}-${index}`}
              className="relative flex gap-3 pb-4"
            >
              <span className={`z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${causalDotClass(index, reasonChain.length)}`}>
                {index + 1}
              </span>
              <div className="min-w-0 rounded-xl bg-slate-50 px-3 py-2.5 ring-1 ring-slate-900/5">
                <p className="text-sm font-medium leading-5">{reason}</p>
              </div>
            </div>
          ))}
          {reasonChain.length === 0 ? (
            <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No risk formation details were returned for this workspace.
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function TrustSummary({ workspace }: { workspace: RiskWorkspaceResponse }) {
  const trust = workspace.trust_summary;
  const warnings = trust?.warnings ?? [];
  const confidence =
    trust?.lowest_confidence_score ??
    workspace.explainability?.trust_context.lowest_confidence_score;
  const freshness =
    trust?.worst_freshness_status ??
    workspace.explainability?.trust_context.worst_freshness_status;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <CardTitle>Data trust</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-2.5">
          <SignalMetric
            icon={<ShieldCheck className="h-4 w-4" />}
            label="Signal confidence"
            value={displayPercent(confidence)}
            helper="reliability"
          />
          <SignalMetric
            icon={<Clock3 className="h-4 w-4" />}
            label="Tracking freshness"
            value={formatLabel(freshness ?? "unknown")}
            helper="latest source"
          />
          <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
            <p className="text-xs font-semibold text-mutedForeground">Trust warnings</p>
            {warnings.length > 0 ? (
              <ul className="mt-3 space-y-2 text-sm">
                {warnings.map((warning) => (
                  <li key={warning} className="leading-6">
                    {warning}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-mutedForeground">No trust warnings.</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <PackageCheck className="h-5 w-5 text-pressure-amber" />
          <CardTitle>Operational exposure context</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-2.5">
          <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Available cover</h3>
              <span className="text-xs font-semibold text-mutedForeground">{inventory.length} material contexts</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {inventory.slice(0, 2).map((item) => (
                <InventoryBlock
                  key={`${item.plant_reference}-${item.material_reference}`}
                  item={item}
                />
              ))}
              {inventory.length === 0 ? (
                <p className="text-sm text-mutedForeground">
                  No available cover context returned for this view.
                </p>
              ) : null}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
            <h3 className="font-semibold">Inbound movement condition</h3>
            <div className="mt-3 space-y-2">
              {shipments.slice(0, 3).map((shipment) => (
                <ShipmentBlock
                  key={shipment.shipment_reference}
                  shipment={shipment}
                />
              ))}
              {shipments.length === 0 ? (
                <p className="text-sm text-mutedForeground">
                  No inbound movement condition returned for this view.
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
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock3 className="h-5 w-5 text-primary" />
            <CardTitle>Exposure timeline</CardTitle>
          </div>
          <Badge variant="outline">{timeline.total} signals</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {timeline.items.map((entry) => (
            <TimelineEntry key={entry.event_id} entry={entry} />
          ))}
          {timeline.items.length === 0 ? (
            <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No historical signal chain detected.
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
  const priorityNodes = ["shipment", "plant", "material", "supplier", "risk_candidate"]
    .map((type) => ({
      type,
      nodes: (graph?.nodes ?? []).filter((node) => node.type === type).slice(0, 4),
    }))
    .filter((group) => group.nodes.length > 0);
  const priorityEdges = (graph?.edges ?? [])
    .filter((edge) => {
      const fromType = nodeById.get(edge.from_node_id)?.type;
      const toType = nodeById.get(edge.to_node_id)?.type;
      return [fromType, toType].some((type) =>
        ["shipment", "plant", "material", "supplier", "risk_candidate"].includes(type ?? ""),
      );
    })
    .slice(0, 5);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <GitBranch className="h-5 w-5 text-primary" />
          <CardTitle>Connected operational context</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-2.5">
          {priorityNodes.map((group) => (
            <div key={group.type} className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
              <p className="text-xs font-semibold text-mutedForeground">{formatLabel(group.type)}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {group.nodes.map((node) => (
                  <span key={node.id} className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-900/5">
                    {node.label}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {priorityNodes.length === 0 ? (
            <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-mutedForeground ring-1 ring-slate-900/5">
              No connected operational records returned.
            </p>
          ) : null}
          <div className="space-y-1.5">
            {priorityEdges.map((edge) => (
              <div
                key={`${edge.from_node_id}-${edge.relationship}-${edge.to_node_id}`}
                className="rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-slate-900/5"
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
        label="Available cover"
        value={displayDays(item.days_of_cover)}
      />
      <ContextPill
        label="Daily consumption"
        value={`${formatNumber(item.daily_consumption_rate)} ${item.unit}`}
      />
    </>
  );
}

function ShipmentBlock({ shipment }: { shipment: SignalShipmentContinuity }) {
  return (
    <div className={`rounded-xl p-3 ring-1 ${shipment.status === "degraded" ? "bg-red-50 ring-red-200" : shipment.status === "watch" ? "bg-amber-50 ring-amber-200" : "bg-white ring-slate-900/5"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{shipment.shipment_reference}</p>
        <Badge variant="outline">{formatLabel(shipment.status)}</Badge>
      </div>
      <div className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
        <span>ETA {formatDate(shipment.eta)}</span>
        <span>Slip {displayDays(shipment.eta_slip_days)}</span>
        <span>
          Tracking freshness {formatLabel(shipment.tracking_freshness_status)}
        </span>
      </div>
      <ul className="mt-3 space-y-1 text-sm text-mutedForeground">
        {shipment.continuity_reasons.slice(0, 3).map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function TimelineEntry({ entry }: { entry: SignalTimelineEntry }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{entry.title}</p>
          <p className="mt-1 text-sm leading-6 text-mutedForeground">
            {entry.description}
          </p>
        </div>
        <span className="text-xs text-mutedForeground">
          {formatDate(entry.timestamp)}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-slate-900/5">
          {formatLabel(entry.event_category)}
        </span>
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-slate-900/5">
          Signal confidence {displayPercent(entry.confidence_score)}
        </span>
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-slate-900/5">
          Freshness {formatLabel(entry.freshness_status)}
        </span>
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-slate-900/5">
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
  icon: React.ReactNode;
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
        : "bg-white/84 text-foreground ring-slate-900/5";
  return (
    <div className={`rounded-xl p-2.5 ring-1 ${toneClass}`}>
      <div className="flex items-center gap-2 text-mutedForeground">
        {icon}
        <p className="text-xs font-semibold">{label}</p>
      </div>
      <p className="mt-1.5 break-words text-lg font-semibold">{value}</p>
      <p className="mt-1 text-xs text-mutedForeground">{helper}</p>
    </div>
  );
}

function ContextPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold text-mutedForeground">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-semibold">{value}</p>
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

function workspaceTone(severity?: string | null) {
  if (severity === "critical") return "bg-slate-950 shadow-nerve";
  if (severity === "high") return "bg-slate-950 shadow-panel";
  return "bg-slate-900 shadow-panel";
}

function causalDotClass(index: number, length: number) {
  if (index === length - 1) return "bg-red-500 text-white";
  if (index > 0) return "bg-amber-400 text-slate-950";
  return "bg-blue-500 text-white";
}

function UnavailableState() {
  return (
    <Card className="bg-card/90 shadow-panel">
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
    <Card className="bg-card/90 shadow-panel">
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
  if (value === "shipment_continuity") return "Inbound movement";
  if (value === "signal_trust") return "Data trust";
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

function displayDaysUntil(value?: string | null) {
  if (!value) return "exposure timing unknown";
  return `${formatNumber(value)} days until exposure`;
}

function displayPercent(value?: string | null) {
  if (!value) return "Unknown";
  return `${formatNumber(value)}%`;
}
