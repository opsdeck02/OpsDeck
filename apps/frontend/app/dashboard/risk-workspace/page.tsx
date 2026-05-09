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
    <main className="grid min-w-0 gap-4">
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
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.55fr)]">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge value={risk?.severity ?? "unknown"} />
              <Badge variant="outline">
                {formatLabel(risk?.risk_type ?? "risk")}
              </Badge>
              {exposure ? (
                <Badge variant="outline">
                  {formatLabel(exposure.exposure_level)} exposure
                </Badge>
              ) : null}
            </div>
            <CardTitle className="text-xl tracking-tight">
              {contextTitle(risk?.material_reference, risk?.plant_reference)}
            </CardTitle>
            <p className="text-sm leading-6 text-mutedForeground">
              {exposure?.operational_reason ??
                explainability?.summary ??
                "Operational risk context is available for review."}
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
              <SignalMetric
                icon={<Boxes className="h-4 w-4" />}
                label="Available cover"
                value={displayDays(risk?.days_of_cover)}
                helper="deterministic continuity"
              />
              <SignalMetric
                icon={<Clock3 className="h-4 w-4" />}
                label="Projected exhaustion"
                value={formatDate(
                  exposure?.estimated_exposure_date ??
                    risk?.projected_exhaustion_date,
                )}
                helper={displayDaysUntil(exposure?.days_until_exposure)}
              />
              <SignalMetric
                icon={<Truck className="h-4 w-4" />}
                label="Inbound movement"
                value={
                  risk?.shipment_reference ??
                  exposure?.shipment_reference ??
                  "Not linked"
                }
                helper={formatLabel(
                  risk?.continuity_status ?? "movement context",
                )}
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

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <WhyThisMatters workspace={workspace} />
        <ContinuitySummary
          inventory={workspace.inventory_continuity}
          shipments={workspace.shipment_continuity}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
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
        <p className="text-sm text-mutedForeground">
          One tenant-scoped view of what is exposed, why it is becoming risky,
          how it formed, and how much to trust the signals.
        </p>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3 md:grid-cols-3 xl:grid-cols-[1fr_1fr_1fr_1fr_160px_auto]">
          <input
            name="plant_reference"
            defaultValue={searchParams?.plant_reference ?? ""}
            placeholder="Plant reference"
            className="rounded-xl border bg-card px-3 py-2.5 text-sm"
          />
          <input
            name="material_reference"
            defaultValue={searchParams?.material_reference ?? ""}
            placeholder="Material reference"
            className="rounded-xl border bg-card px-3 py-2.5 text-sm"
          />
          <input
            name="shipment_reference"
            defaultValue={searchParams?.shipment_reference ?? ""}
            placeholder="Shipment reference"
            className="rounded-xl border bg-card px-3 py-2.5 text-sm"
          />
          <input
            name="risk_type"
            defaultValue={searchParams?.risk_type ?? ""}
            placeholder="Risk category"
            className="rounded-xl border bg-card px-3 py-2.5 text-sm"
          />
          <select
            name="severity"
            defaultValue={searchParams?.severity ?? ""}
            className="rounded-xl border bg-card px-3 py-2.5 text-sm"
          >
            <option value="">Any severity</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <button
            type="submit"
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primaryForeground"
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
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <CardTitle>Why this is becoming risky</CardTitle>
        </div>
        <p className="text-sm leading-6 text-mutedForeground">
          {explainability?.summary ??
            "OpsDeck does not have enough signal detail to explain this risk yet."}
        </p>
      </CardHeader>
      <CardContent>
        <div className="mb-5 grid gap-3 sm:grid-cols-2">
          <ContextPill
            label="Primary driver"
            value={driverLabel(explainability?.primary_driver)}
          />
          <ContextPill
            label="Risk category"
            value={formatLabel(workspace.selected_risk?.risk_type)}
          />
        </div>
        <div className="space-y-3">
          {reasonChain.map((reason, index) => (
            <div
              key={`${reason}-${index}`}
              className="flex gap-3 rounded-xl border bg-card p-3"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-primary">
                {index + 1}
              </span>
              <p className="text-sm leading-6">{reason}</p>
            </div>
          ))}
          {reasonChain.length === 0 ? (
            <p className="rounded-2xl border bg-card px-4 py-6 text-sm text-mutedForeground">
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
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <CardTitle>Data trust</CardTitle>
        </div>
        <p className="text-sm text-mutedForeground">
          Confidence reflects how complete and reliable the signal is. Freshness
          reflects how recently the source was updated.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3">
          <SignalMetric
            icon={<ShieldCheck className="h-4 w-4" />}
            label="Signal confidence"
            value={displayPercent(confidence)}
            helper="completeness and reliability"
          />
          <SignalMetric
            icon={<Clock3 className="h-4 w-4" />}
            label="Tracking freshness"
            value={formatLabel(freshness ?? "unknown")}
            helper="most stale source in view"
          />
          <div className="rounded-xl border bg-card p-3">
            <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">
              Data trust notes
            </p>
            {warnings.length > 0 ? (
              <ul className="mt-3 space-y-2 text-sm">
                {warnings.map((warning) => (
                  <li key={warning} className="leading-6">
                    {warning}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-mutedForeground">
                No data trust warnings were returned for this workspace.
              </p>
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
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center gap-2">
          <PackageCheck className="h-5 w-5 text-primary" />
          <CardTitle>Operational exposure context</CardTitle>
        </div>
        <p className="text-sm text-mutedForeground">
          Current cover and inbound movement condition from existing operational
          records.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4">
          <div className="rounded-xl border bg-card p-3">
            <h3 className="font-semibold">Available cover</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
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
          <div className="rounded-xl border bg-card p-3">
            <h3 className="font-semibold">Inbound movement condition</h3>
            <div className="mt-4 space-y-3">
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
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock3 className="h-5 w-5 text-primary" />
            <CardTitle>How the risk formed</CardTitle>
          </div>
          <Badge variant="outline">{timeline.total} signals</Badge>
        </div>
        <p className="text-sm text-mutedForeground">
          The operational signals that led to this continuity risk, ordered by
          when they occurred.
        </p>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {timeline.items.map((entry) => (
            <TimelineEntry key={entry.event_id} entry={entry} />
          ))}
          {timeline.items.length === 0 ? (
            <p className="rounded-2xl border bg-card px-4 py-6 text-sm text-mutedForeground">
              No signal history was returned for the current timeline window.
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

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center gap-2">
          <GitBranch className="h-5 w-5 text-primary" />
          <CardTitle>Connected operational context</CardTitle>
        </div>
        <p className="text-sm text-mutedForeground">
          Linked plant, material, shipment, supplier, signal, and risk records
          for this operational context.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4">
          <div className="rounded-2xl border bg-card p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">
              Connected records
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(graph?.nodes ?? []).slice(0, 12).map((node) => (
                <span
                  key={node.id}
                  className="rounded-full border bg-muted px-3 py-1 text-xs font-medium"
                >
                  {formatLabel(node.type)}: {node.label}
                </span>
              ))}
              {(graph?.nodes ?? []).length === 0 ? (
                <span className="text-sm text-mutedForeground">
                  No connected operational records returned.
                </span>
              ) : null}
            </div>
          </div>
          <div className="space-y-2">
            {(graph?.edges ?? []).slice(0, 10).map((edge) => (
              <div
                key={`${edge.from_node_id}-${edge.relationship}-${edge.to_node_id}`}
                className="rounded-2xl border bg-card px-4 py-3 text-sm"
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
    <div className="rounded-xl border bg-muted/40 p-3">
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
    <div className="rounded-xl border bg-card p-3">
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
        <span className="rounded-full border px-3 py-1">
          {formatLabel(entry.event_category)}
        </span>
        <span className="rounded-full border px-3 py-1">
          Signal confidence {displayPercent(entry.confidence_score)}
        </span>
        <span className="rounded-full border px-3 py-1">
          Freshness {formatLabel(entry.freshness_status)}
        </span>
        <span className="rounded-full border px-3 py-1">
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
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-3">
      <div className="flex items-center gap-2 text-mutedForeground">
        {icon}
        <p className="text-xs uppercase tracking-[0.18em]">{label}</p>
      </div>
      <p className="mt-2 break-words text-base font-semibold">{value}</p>
      <p className="mt-1 text-xs text-mutedForeground">{helper}</p>
    </div>
  );
}

function ContextPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-card px-3 py-2.5">
      <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-semibold">{value}</p>
    </div>
  );
}

function SeverityBadge({ value }: { value: string }) {
  const className =
    value === "critical"
      ? "border-red-300 bg-red-50 text-red-700"
      : value === "high"
        ? "border-amber-300 bg-amber-50 text-amber-800"
        : value === "medium"
          ? "border-sky-200 bg-sky-50 text-sky-700"
          : "border bg-card text-mutedForeground";
  return (
    <span
      className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${className}`}
    >
      {value}
    </span>
  );
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
