"use client";

import { useState, useTransition } from "react";

export function StockActionControls({
  plantId,
  materialId,
  actionStatus,
  canManage = true,
}: {
  plantId: number;
  materialId: number;
  actionStatus: string | null;
  canManage?: boolean;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function updateAction(nextStatus: "in_progress" | "completed") {
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/stock-cover/${plantId}/${materialId}/action`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_status: nextStatus }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Action update failed.");
        return;
      }
      window.location.reload();
    });
  }

  if (!canManage) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        {actionStatus !== "in_progress" && actionStatus !== "completed" ? (
          <button
            type="button"
            onClick={() => updateAction("in_progress")}
            disabled={isPending}
            className="rounded-2xl border px-4 py-3 text-sm font-semibold disabled:opacity-60"
          >
            Start
          </button>
        ) : null}
        {actionStatus !== "completed" ? (
          <button
            type="button"
            onClick={() => updateAction("completed")}
            disabled={isPending}
            className="rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
          >
            Mark complete
          </button>
        ) : null}
      </div>
      {message ? <p className="rounded-2xl bg-muted px-4 py-3 text-sm">{message}</p> : null}
    </div>
  );
}
