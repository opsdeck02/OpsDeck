import { notFound } from "next/navigation";

import { ExceptionDetailActions } from "@/components/exceptions/exception-detail-actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getExceptionDetail, getTenantUsers } from "@/lib/api";
import { canManageOperationalWorkflow } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function ExceptionDetailPage({
  params,
}: {
  params: { exceptionId: string };
}) {
  const exceptionId = Number(params.exceptionId);
  const [detail, user] = await Promise.all([getExceptionDetail(exceptionId), getCurrentUser()]);
  if (!detail) {
    notFound();
  }
  const canManage = canManageOperationalWorkflow(user?.memberships[0]?.role);
  const users = canManage ? await getTenantUsers() : [];

  const item = detail.exception;

  return (
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>{item.title}</CardTitle>
          <div className="flex flex-wrap items-center gap-3 text-sm text-mutedForeground">
            <Badge variant="outline">{item.type.replaceAll("_", " ")}</Badge>
            <Badge variant="outline">{item.severity}</Badge>
            <Badge variant="outline">{item.status.replace("_", " ")}</Badge>
            <span>{item.current_owner?.full_name ?? "Unassigned"}</span>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Triggered" value={formatDate(item.triggered_at)} />
          <Metric label="Updated" value={formatDate(item.updated_at)} />
          <Metric label="Due" value={item.due_at ? formatDate(item.due_at) : "—"} />
          <Metric label="Shipment" value={item.linked_shipment?.label ?? "—"} />
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-5">
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Exception summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Line label="Summary" value={item.summary ?? "—"} />
              <Line label="Plant" value={item.linked_plant?.label ?? "—"} />
              <Line label="Material" value={item.linked_material?.label ?? "—"} />
              <Line label="Owner" value={item.current_owner?.full_name ?? "Unassigned"} />
              <Line label="Recommended next step" value={item.recommended_next_step ?? "—"} />
              <Line label="Action status" value={item.action_status.replace("_", " ")} />
              <Line label="Action deadline" value={item.due_at ? formatDate(item.due_at) : "—"} />
              <Line label="SLA" value={item.action_sla_breach ? "Breached" : "On track"} />
            </CardContent>
          </Card>

          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Linked risk context</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {detail.linked_shipment_detail ? (
                <div className="rounded-2xl border bg-card p-4">
                  <p className="font-semibold">{detail.linked_shipment_detail.shipment_id}</p>
                  <p className="mt-1 text-mutedForeground">
                    State: {detail.linked_shipment_detail.shipment_state.replaceAll("_", " ")}
                  </p>
                  <p className="text-mutedForeground">
                    Confidence: {detail.linked_shipment_detail.confidence}
                  </p>
                  <p className="text-mutedForeground">
                    Latest source: {detail.linked_shipment_detail.latest_status_source}
                  </p>
                </div>
              ) : (
                <p className="text-mutedForeground">No shipment is linked to this exception.</p>
              )}
              <div className="space-y-2">
                {detail.linked_context_notes.map((note) => (
                  <div key={note} className="rounded-xl bg-muted px-4 py-3">
                    {note}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <ExceptionDetailActions
          exception={item}
          users={users}
          statusOptions={detail.status_options}
          initialComments={detail.comments}
          canManage={canManage}
        />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-muted p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">{label}</p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-muted px-4 py-3">
      <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">{label}</p>
      <p className="mt-2 font-semibold">{value}</p>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
