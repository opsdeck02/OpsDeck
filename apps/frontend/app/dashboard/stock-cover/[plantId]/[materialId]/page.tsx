import { notFound } from "next/navigation";
import type {
  ShipmentProtectionEvaluation,
  TimePhasedCoverResult,
} from "@steelops/contracts";

import { StockActionControls } from "@/components/stock/stock-action-controls";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getStockCoverDetail } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function StockCoverDetailPage({
  params,
}: {
  params: { plantId: string; materialId: string };
}) {
  const detail = await getStockCoverDetail(
    Number(params.plantId),
    Number(params.materialId),
  );
  if (!detail) {
    notFound();
  }

  const row = detail.row;
  const calc = row.calculation;
  const timePhasedCover =
    detail.time_phased_cover ?? calc.time_phased_cover ?? null;

  return (
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>
            {row.plant_name} / {row.material_name}
          </CardTitle>
          <p className="text-sm text-mutedForeground">
            Continuity cover, exposure timing, and signal trust for this
            operating context.
          </p>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="Latest stock snapshot"
            value={formatDate(row.latest_snapshot_time)}
          />
          <Metric
            label="Threshold used"
            value={displayDays(calc.threshold_days)}
          />
          <Metric
            label="Available cover"
            value={displayDays(calc.days_of_cover)}
          />
          <Metric label="Signal reliability" value={calc.confidence_level} />
          <Metric
            label="Urgency band"
            value={formatUrgency(calc.urgency_band)}
          />
          <Metric
            label="Risk hours remaining"
            value={displayHours(calc.risk_hours_remaining)}
          />
          <Metric
            label="Production exposure"
            value={displayTonnes(calc.estimated_production_exposure_mt)}
          />
          <Metric
            label="Value at risk"
            value={displayCurrency(calc.estimated_value_at_risk)}
          />
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Continuity calculation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Breakdown
              label="Current / total stock"
              value={displayTonnes(calc.current_stock_mt)}
            />
            <Breakdown
              label="Available usable stock"
              value={displayTonnes(calc.total_considered_mt)}
            />
            <Breakdown
              label="Raw inbound pipeline (not usable yet)"
              value={displayTonnes(calc.raw_inbound_pipeline_mt)}
            />
            <Breakdown
              label="Effective inbound visibility"
              value={displayTonnes(calc.effective_inbound_pipeline_mt)}
            />
            <Breakdown
              label="Daily consumption"
              value={displayTonnes(calc.daily_consumption_mt)}
            />
            <Breakdown
              label="Warning threshold"
              value={displayDays(calc.warning_days)}
            />
            <Breakdown
              label="Critical threshold"
              value={displayDays(calc.threshold_days)}
            />
            <Breakdown
              label="Estimated breach date"
              value={formatDate(calc.estimated_breach_date)}
            />
            <Breakdown
              label="Linked inbound dependencies"
              value={String(calc.linked_shipment_count)}
            />
            <Breakdown
              label="Weighted inbound count"
              value={calc.weighted_shipment_count}
            />
            <div className="flex items-center justify-between rounded-xl bg-muted px-4 py-3">
              <span className="text-mutedForeground">Continuity status</span>
              <Badge variant="outline">
                {formatContinuityStatus(calc.status)}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Signal reliability and assumptions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-mutedForeground">
            <div>
              <p className="font-medium text-foreground">Reliability reasons</p>
              <ul className="mt-2 space-y-2">
                {detail.confidence_reasons.map((reason) => (
                  <li key={reason} className="rounded-xl bg-muted px-4 py-3">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium text-foreground">
                Refinement assumptions
              </p>
              <ul className="mt-2 space-y-2">
                {detail.assumptions.map((assumption) => (
                  <li
                    key={assumption}
                    className="rounded-xl border border-dashed px-4 py-3"
                  >
                    {assumption}
                  </li>
                ))}
              </ul>
            </div>
            {calc.insufficient_data_reason ? (
              <div className="rounded-xl bg-muted px-4 py-3 text-primary">
                {calc.insufficient_data_reason}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Operational exposure</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Breakdown
            label="Estimated production exposure"
            value={displayTonnes(calc.estimated_production_exposure_mt)}
          />
          <Breakdown
            label="Estimated value at risk"
            value={displayCurrency(calc.estimated_value_at_risk)}
          />
          <Breakdown
            label="Base value"
            value={displayValuePerMt(calc.value_per_mt_used)}
          />
          <Breakdown
            label="Severity multiplier"
            value={displayMultiplier(calc.criticality_multiplier_used)}
          />
          <Breakdown
            label="Urgency band"
            value={formatUrgency(calc.urgency_band)}
          />
          <Breakdown
            label="Risk hours remaining"
            value={displayHours(calc.risk_hours_remaining)}
          />
          <div className="rounded-xl border border-dashed px-4 py-3 text-mutedForeground">
            {detail.impact_explanation.map((item) => (
              <p key={item} className="mt-1 first:mt-0">
                {item}
              </p>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Continuity response record</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Breakdown
            label="Response guidance"
            value={calc.recommended_action_text ?? "—"}
          />
          <Breakdown
            label="Owner role"
            value={calc.owner_role_recommended ?? "—"}
          />
          <Breakdown
            label="Response window"
            value={formatDeadline(calc.action_deadline_hours)}
          />
          <Breakdown
            label="Response status"
            value={(calc.action_status ?? "pending").replace("_", " ")}
          />
          <Breakdown
            label="SLA timer"
            value={formatCountdown(
              calc.action_deadline_hours,
              calc.action_age_hours,
              calc.action_status,
            )}
          />
          <Breakdown
            label="SLA state"
            value={calc.action_sla_breach ? "Breached" : "On track"}
          />
          <Breakdown
            label="Current owner"
            value={detail.current_owner ?? "Unassigned"}
          />
          {calc.recommended_action_text ? (
            <StockActionControls
              plantId={row.plant_id}
              materialId={row.material_id}
              actionStatus={calc.action_status}
            />
          ) : null}
          <div className="rounded-xl border border-dashed px-4 py-3 text-mutedForeground">
            {detail.recommendation_why.map((item) => (
              <p key={item} className="mt-1 first:mt-0">
                {item}
              </p>
            ))}
          </div>
        </CardContent>
      </Card>

      <TimePhasedCoverSection cover={timePhasedCover} />

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Contributing inbound dependencies</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-2xl border">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted text-mutedForeground">
                <tr>
                  <th className="px-4 py-3 font-medium">Inbound ref</th>
                  <th className="px-4 py-3 font-medium">Reliability source</th>
                  <th className="px-4 py-3 font-medium">Raw qty</th>
                  <th className="px-4 py-3 font-medium">Factor</th>
                  <th className="px-4 py-3 font-medium">Effective qty</th>
                  <th className="px-4 py-3 font-medium">ETA</th>
                  <th className="px-4 py-3 font-medium">State</th>
                  <th className="px-4 py-3 font-medium">Signal reliability</th>
                  <th className="px-4 py-3 font-medium">Freshness</th>
                  <th className="px-4 py-3 font-medium">Explanation</th>
                </tr>
              </thead>
              <tbody>
                {detail.shipments.map((shipment) => (
                  <tr key={shipment.id} className="border-t bg-card">
                    <td className="px-4 py-3 font-medium">
                      {shipment.shipment_id}
                    </td>
                    <td className="px-4 py-3">{shipment.supplier_name}</td>
                    <td className="px-4 py-3">
                      {displayTonnes(shipment.raw_quantity_mt)}
                    </td>
                    <td className="px-4 py-3">
                      {Number(shipment.contribution_factor).toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      {displayTonnes(shipment.effective_quantity_mt)}
                    </td>
                    <td className="px-4 py-3">
                      {formatDate(shipment.current_eta)}
                    </td>
                    <td className="px-4 py-3">
                      {shipment.shipment_state.replace("_", " ")}
                    </td>
                    <td className="px-4 py-3">{shipment.confidence}</td>
                    <td className="px-4 py-3">{shipment.freshness_label}</td>
                    <td className="px-4 py-3 text-mutedForeground">
                      {shipment.explanation}
                    </td>
                  </tr>
                ))}
                {detail.shipments.length === 0 ? (
                  <tr>
                    <td
                      className="px-4 py-8 text-center text-mutedForeground"
                      colSpan={10}
                    >
                      No active inbound shipments contribute to the pipeline
                      estimate.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TimePhasedCoverSection({
  cover,
}: {
  cover: TimePhasedCoverResult | null;
}) {
  const protectiveShipments =
    cover?.shipment_evaluations.filter((shipment) =>
      ["PROTECTIVE", "RESERVE_ON_ARRIVAL", "CRITICAL_ON_ARRIVAL"].includes(
        shipment.protection_status,
      ),
    ) ?? [];
  const lateShipments =
    cover?.shipment_evaluations.filter((shipment) =>
      ["LATE_AFTER_RESERVE", "TOO_LATE"].includes(shipment.protection_status),
    ) ?? [];

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Time-phased cover</CardTitle>
          {cover ? (
            <Badge variant="outline">
              {cover.calibration_status.toLowerCase()}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-5 text-sm">
        {cover ? (
          <>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <BreachMetric
                label="Warning date"
                firstDate={cover.warning_date}
                currentDate={cover.current_projected_warning_date}
              />
              <BreachMetric
                label="Reserve breach"
                firstDate={cover.reserve_breach_date}
                currentDate={cover.current_projected_reserve_breach_date}
              />
              <BreachMetric
                label="Critical breach"
                firstDate={cover.critical_breach_date}
                currentDate={cover.current_projected_critical_breach_date}
              />
              <BreachMetric
                label="Interruption"
                firstDate={cover.interruption_date}
                currentDate={cover.current_projected_interruption_date}
              />
            </div>

            {cover.assumptions_used.length > 0 ? (
              <div className="rounded-xl border border-dashed px-4 py-3 text-mutedForeground">
                {cover.assumptions_used.map((assumption) => (
                  <p key={assumption} className="mt-1 first:mt-0">
                    {assumption}
                  </p>
                ))}
              </div>
            ) : null}

            <div className="grid gap-5 lg:grid-cols-2">
              <ShipmentEvaluationList
                title="Protective shipments"
                emptyText="No inbound shipment currently protects continuity before breach."
                shipments={protectiveShipments}
              />
              <ShipmentEvaluationList
                title="Late shipments"
                emptyText="No inbound shipment is currently late against reserve or critical timing."
                shipments={lateShipments}
              />
            </div>
          </>
        ) : (
          <div className="rounded-xl bg-muted px-4 py-5 text-mutedForeground">
            Time-phased cover has not been calculated for this stock context.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function BreachMetric({
  label,
  firstDate,
  currentDate,
}: {
  label: string;
  firstDate: string | null;
  currentDate: string | null;
}) {
  return (
    <div className="rounded-xl bg-muted p-4">
      <p className="text-xs font-medium uppercase text-mutedForeground">
        {label}
      </p>
      <div className="mt-3 space-y-2">
        <div>
          <p className="text-xs text-mutedForeground">First breach</p>
          <p className="font-semibold text-foreground">
            {formatDate(firstDate)}
          </p>
        </div>
        <div>
          <p className="text-xs text-mutedForeground">Current projected</p>
          <p className="font-semibold text-foreground">
            {formatDate(currentDate)}
          </p>
        </div>
      </div>
    </div>
  );
}

function ShipmentEvaluationList({
  title,
  emptyText,
  shipments,
}: {
  title: string;
  emptyText: string;
  shipments: ShipmentProtectionEvaluation[];
}) {
  return (
    <div>
      <p className="font-medium text-foreground">{title}</p>
      <div className="mt-3 space-y-3">
        {shipments.map((shipment) => (
          <div
            key={shipment.shipment_id}
            className="rounded-xl border px-4 py-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-semibold text-foreground">
                  {shipment.shipment_id}
                </p>
                <p className="text-xs text-mutedForeground">
                  {formatDate(shipment.eta)}
                </p>
              </div>
              <Badge variant="outline">
                {formatProtectionStatus(shipment.protection_status)}
              </Badge>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-mutedForeground sm:grid-cols-2">
              <span>
                Before: {displayTonnes(shipment.stock_before_arrival_mt)}
              </span>
              <span>
                After: {displayTonnes(shipment.stock_after_arrival_mt)}
              </span>
              <span>Raw: {displayTonnes(shipment.raw_quantity_mt)}</span>
              <span>
                Effective: {displayTonnes(shipment.effective_quantity_mt)}
              </span>
            </div>
            <div className="mt-3 space-y-1 text-mutedForeground">
              {shipment.reasoning.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
            </div>
          </div>
        ))}
        {shipments.length === 0 ? (
          <div className="rounded-xl bg-muted px-4 py-5 text-mutedForeground">
            {emptyText}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-muted p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Breakdown({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-muted px-4 py-3">
      <span className="text-mutedForeground">{label}</span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  );
}

function displayTonnes(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${Number(value).toLocaleString()} MT`;
}

function displayDays(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${Number(value).toFixed(2)} d`;
}

function displayHours(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${Number(value).toFixed(2)} h`;
}

function displayCurrency(value: string | null) {
  const numeric = Number(value ?? "0");
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(numeric);
}

function displayValuePerMt(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${displayCurrency(value)}/MT`;
}

function displayMultiplier(value: string | null) {
  if (!value) {
    return "—";
  }
  return Number(value).toString();
}

function formatUrgency(value: string) {
  return value.replace("_", " ");
}

function formatContinuityStatus(value: string) {
  if (value === "safe") {
    return "Currently covered";
  }
  return value.replaceAll("_", " ");
}

function formatProtectionStatus(value: string) {
  return value.replaceAll("_", " ").toLowerCase();
}

function formatDate(value: string | null) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDeadline(value: number | null) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${value}h`;
}

function formatCountdown(
  deadlineHours: number | null,
  ageHours: string | null,
  actionStatus: string | null,
) {
  if (actionStatus === "completed") {
    return "Completed";
  }
  if (deadlineHours === null || ageHours === null) {
    return "—";
  }
  const remaining = deadlineHours - Number(ageHours);
  if (remaining >= 0) {
    return `Due in ${Math.ceil(remaining)}h`;
  }
  return `Overdue by ${Math.ceil(Math.abs(remaining))}h`;
}
