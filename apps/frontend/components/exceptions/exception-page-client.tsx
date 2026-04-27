"use client";

import { useMemo, useState, useTransition } from "react";

import type { ExceptionEvaluationResponse, ExceptionItem, TenantUser } from "@steelops/contracts";

const statuses = ["", "open", "in_progress", "resolved", "closed"];
const severities = ["", "low", "medium", "high", "critical"];
const types = [
  "",
  "stock_cover_critical",
  "stock_cover_warning",
  "shipment_eta_delay",
  "shipment_stale_update",
  "inland_delay_risk",
];

export function ExceptionPageClient({
  users,
  initialFilters,
  canManage,
}: {
  users: TenantUser[];
  initialFilters: {
    status?: string;
    severity?: string;
    type?: string;
    owner_user_id?: string;
    unassigned_only?: string;
  };
  canManage: boolean;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const hasOwnerFilter = useMemo(() => Boolean(initialFilters.owner_user_id), [initialFilters.owner_user_id]);

  function evaluateRules() {
    setMessage(null);
    startTransition(async () => {
      const response = await fetch("/api/exceptions/evaluate", { method: "POST" });
      const body = (await response.json()) as ExceptionEvaluationResponse | { detail?: string };
      if (!response.ok) {
        const errorBody = body as { detail?: string };
        setMessage(
          typeof errorBody.detail === "string" ? errorBody.detail : "Evaluation failed.",
        );
        return;
      }
      const result = body as ExceptionEvaluationResponse;
      setMessage(
        `Created ${result.created}, updated ${result.updated}, resolved ${result.resolved}. Open after refresh: ${result.open_after_evaluation}.`,
      );
      window.location.reload();
    });
  }

  return (
    <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <select
            name="status"
            defaultValue={initialFilters.status ?? ""}
            className="rounded-2xl border bg-card px-4 py-3 text-sm"
          >
            {statuses.map((status) => (
              <option key={status || "all"} value={status}>
                {status ? status.replace("_", " ") : "All statuses"}
              </option>
            ))}
          </select>
          <select
            name="severity"
            defaultValue={initialFilters.severity ?? ""}
            className="rounded-2xl border bg-card px-4 py-3 text-sm"
          >
            {severities.map((severity) => (
              <option key={severity || "all"} value={severity}>
                {severity || "All severities"}
              </option>
            ))}
          </select>
          <select
            name="type"
            defaultValue={initialFilters.type ?? ""}
            className="rounded-2xl border bg-card px-4 py-3 text-sm"
          >
            {types.map((type) => (
              <option key={type || "all"} value={type}>
                {type ? type.replaceAll("_", " ") : "All types"}
              </option>
            ))}
          </select>
          <select
            name="owner_user_id"
            defaultValue={initialFilters.owner_user_id ?? ""}
            className="rounded-2xl border bg-card px-4 py-3 text-sm"
          >
            <option value="">All owners</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm">
            <input type="checkbox" name="unassigned_only" defaultChecked={initialFilters.unassigned_only === "true"} />
            <span>Unassigned only</span>
          </label>
          <button
            type="submit"
            className="rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground"
          >
            Apply filters
          </button>
        </form>
        {canManage ? (
          <button
            type="button"
            onClick={evaluateRules}
            disabled={isPending}
            className="rounded-2xl border px-5 py-3 text-sm font-semibold disabled:opacity-60"
          >
            {isPending ? "Refreshing..." : "Evaluate exceptions"}
          </button>
        ) : (
          <p className="text-sm text-mutedForeground">
            Read-only sponsor access. Workflow actions stay with operators and tenant admins.
          </p>
        )}
      </div>
      {message ? <p className="mt-4 rounded-2xl bg-muted px-4 py-3 text-sm">{message}</p> : null}
      {hasOwnerFilter ? (
        <p className="mt-4 text-xs text-mutedForeground">Owner filters use tenant membership records.</p>
      ) : null}
    </section>
  );
}
