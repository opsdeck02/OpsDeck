"use client";

import { useState, useTransition } from "react";

import type { ExceptionComment, ExceptionItem, ExceptionStatus, TenantUser } from "@steelops/contracts";

export function ExceptionDetailActions({
  exception,
  users,
  statusOptions,
  initialComments,
  canManage,
}: {
  exception: ExceptionItem;
  users: TenantUser[];
  statusOptions: ExceptionStatus[];
  initialComments: ExceptionComment[];
  canManage: boolean;
}) {
  const [ownerUserId, setOwnerUserId] = useState(String(exception.current_owner?.id ?? ""));
  const [status, setStatus] = useState<ExceptionStatus>(exception.status);
  const [comment, setComment] = useState("");
  const [comments, setComments] = useState(initialComments);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function saveOwner() {
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/exceptions/${exception.id}/owner`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          owner_user_id: ownerUserId ? Number(ownerUserId) : null,
        }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Owner update failed.");
        return;
      }
      setMessage("Owner updated.");
      window.location.reload();
    });
  }

  function saveStatus(nextStatus: ExceptionStatus) {
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/exceptions/${exception.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Status update failed.");
        return;
      }
      setStatus(nextStatus);
      setMessage("Status updated.");
      window.location.reload();
    });
  }

  function addComment() {
    const trimmed = comment.trim();
    if (!trimmed) {
      setMessage("Comment is required.");
      return;
    }
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/exceptions/${exception.id}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment: trimmed }),
      });
      const body = (await response.json()) as ExceptionComment | { detail?: string };
      if (!response.ok) {
        const errorBody = body as { detail?: string };
        setMessage(
          typeof errorBody.detail === "string" ? errorBody.detail : "Comment save failed.",
        );
        return;
      }
      setComments((current) => [...current, body as ExceptionComment]);
      setComment("");
      setMessage("Comment added.");
    });
  }

  function saveActionStatus(nextStatus: "in_progress" | "completed") {
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/exceptions/${exception.id}/action`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_status: nextStatus }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Action update failed.");
        return;
      }
      setMessage("Action updated.");
      window.location.reload();
    });
  }

  return (
    <div className="space-y-5">
      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <h2 className="text-lg font-semibold">Actions</h2>
        {canManage ? (
          <div className="mt-4 grid gap-3">
            <label className="space-y-2 text-sm">
              <span className="font-medium">Owner</span>
              <select
                value={ownerUserId}
                onChange={(event) => setOwnerUserId(event.target.value)}
                className="w-full rounded-2xl border bg-card px-4 py-3"
              >
                <option value="">Unassigned</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name} ({user.role.replace("_", " ")})
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={saveOwner}
              disabled={isPending}
              className="rounded-2xl border px-4 py-3 text-sm font-semibold disabled:opacity-60"
            >
              Save owner
            </button>
            <label className="space-y-2 text-sm">
              <span className="font-medium">Status</span>
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value as ExceptionStatus)}
                className="w-full rounded-2xl border bg-card px-4 py-3"
              >
                {statusOptions.map((option) => (
                  <option key={option} value={option}>
                    {option.replace("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            {statusOptions.length <= 2 ? (
              <p className="text-sm text-mutedForeground">
                Resolution is automatic after fresh data confirms the issue is cleared.
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => saveStatus(status)}
              disabled={isPending}
              className="rounded-2xl border px-4 py-3 text-sm font-semibold disabled:opacity-60"
            >
              Save status
            </button>
            <div className="grid gap-3 sm:grid-cols-2">
              {exception.action_status !== "in_progress" && exception.action_status !== "completed" ? (
                <button
                  type="button"
                  onClick={() => saveActionStatus("in_progress")}
                  disabled={isPending}
                  className="rounded-2xl border px-4 py-3 text-sm font-semibold disabled:opacity-60"
                >
                  Start action
                </button>
              ) : null}
              {exception.action_status !== "completed" ? (
                <button
                  type="button"
                  onClick={() => saveActionStatus("completed")}
                  disabled={isPending}
                  className="rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
                >
                  Complete action
                </button>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="mt-4 rounded-2xl bg-muted px-4 py-3 text-sm text-mutedForeground">
            Sponsor access is read-only. Owner changes, status updates, and comments stay with operators.
          </p>
        )}
        {message ? <p className="mt-4 rounded-2xl bg-muted px-4 py-3 text-sm">{message}</p> : null}
      </section>

      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <h2 className="text-lg font-semibold">Comments</h2>
        <div className="mt-4 space-y-3">
          {comments.map((entry) => (
            <div key={entry.id} className="rounded-2xl border bg-card p-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{entry.author?.full_name ?? "Unknown user"}</span>
                <span className="text-mutedForeground">
                  {new Intl.DateTimeFormat("en", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(entry.created_at))}
                </span>
              </div>
              <p className="mt-2 text-mutedForeground">{entry.comment}</p>
            </div>
          ))}
          {comments.length === 0 ? (
            <p className="text-sm text-mutedForeground">No comments yet.</p>
          ) : null}
        </div>
        {canManage ? (
          <div className="mt-4 space-y-3">
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={4}
              placeholder="Add an operator note"
              className="w-full rounded-2xl border bg-card px-4 py-3 text-sm"
            />
            <button
              type="button"
              onClick={addComment}
              disabled={isPending}
              className="rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
            >
              Add comment
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
