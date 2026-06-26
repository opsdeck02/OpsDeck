"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type {
  OperationalHistoryMilestone,
  OperationalHistoryNote,
  OperationalHistoryReportSnapshot,
  OperationalHistorySummary,
  WeeklyReview,
} from "@/lib/api";

interface Props {
  tenantId: number;
  initialSummary: OperationalHistorySummary;
  initialReports: OperationalHistoryReportSnapshot[];
  initialWeeklyReviews: WeeklyReview[];
}

const today = new Date().toISOString().slice(0, 10);

export function OperationalHistoryPanel({
  tenantId,
  initialSummary,
  initialReports,
  initialWeeklyReviews,
}: Props) {
  const router = useRouter();
  const [summary, setSummary] = useState(initialSummary);
  const [reports, setReports] = useState(initialReports);
  const [weeklyReviews, setWeeklyReviews] = useState(initialWeeklyReviews);
  const [selectedReview, setSelectedReview] = useState<WeeklyReview | null>(
    initialWeeklyReviews[0] ?? null,
  );
  const [milestoneEdit, setMilestoneEdit] = useState<OperationalHistoryMilestone | null>(null);
  const [noteEdit, setNoteEdit] = useState<OperationalHistoryNote | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refreshHistory() {
    const [summaryResponse, reportsResponse, reviewsResponse] = await Promise.all([
      fetch(`/api/operational-history/tenants/${tenantId}`),
      fetch(`/api/operational-history/tenants/${tenantId}/reports`),
      fetch(`/api/operational-reviews/tenants/${tenantId}/weekly-reviews`),
    ]);
    if (summaryResponse.ok) {
      setSummary((await summaryResponse.json()) as OperationalHistorySummary);
    }
    if (reportsResponse.ok) {
      setReports((await reportsResponse.json()) as OperationalHistoryReportSnapshot[]);
    }
    if (reviewsResponse.ok) {
      const nextReviews = (await reviewsResponse.json()) as WeeklyReview[];
      setWeeklyReviews(nextReviews);
      setSelectedReview((current) => {
        if (!current) return nextReviews[0] ?? null;
        return nextReviews.find((item) => item.id === current.id) ?? nextReviews[0] ?? null;
      });
    }
    router.refresh();
  }

  async function submitMilestone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      title: String(form.get("title") ?? ""),
      milestone_type: String(form.get("milestone_type") ?? "weekly_review"),
      status: String(form.get("status") ?? "pending"),
      occurred_at: dateTimeValue(form.get("occurred_at")),
      description: String(form.get("description") ?? ""),
    };
    const target = milestoneEdit
      ? `/api/operational-history/tenants/${tenantId}/milestones/${milestoneEdit.id}`
      : `/api/operational-history/tenants/${tenantId}/milestones`;
    const response = await fetch(target, {
      method: milestoneEdit ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setStatus("Could not save milestone.");
      return;
    }
    setMilestoneEdit(null);
    event.currentTarget.reset();
    setStatus("Milestone saved.");
    await refreshHistory();
  }

  async function submitNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      title: String(form.get("title") ?? ""),
      note_type: String(form.get("note_type") ?? "weekly_review"),
      note_date: dateTimeValue(form.get("note_date")),
      body: String(form.get("body") ?? ""),
      attendees: listValue(form.get("attendees")),
      actions: listValue(form.get("actions")),
    };
    const target = noteEdit
      ? `/api/operational-history/tenants/${tenantId}/notes/${noteEdit.id}`
      : `/api/operational-history/tenants/${tenantId}/notes`;
    const response = await fetch(target, {
      method: noteEdit ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setStatus("Could not save note.");
      return;
    }
    setNoteEdit(null);
    event.currentTarget.reset();
    setStatus("Review note saved.");
    await refreshHistory();
  }

  async function generateReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/operational-history/tenants/${tenantId}/reports/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        report_type: String(form.get("report_type") ?? "pilot"),
        title: String(form.get("title") ?? "Focused Evaluation Report"),
        period_start: emptyToNull(form.get("period_start")),
        period_end: emptyToNull(form.get("period_end")),
      }),
    });
    if (!response.ok) {
      setStatus("Could not generate report.");
      return;
    }
    setStatus("Report snapshot generated.");
    await refreshHistory();
  }

  async function submitWeeklyReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      week_number: Number(form.get("week_number") ?? 1),
      review_date: dateTimeValue(form.get("review_date")) ?? `${today}T00:00:00Z`,
      review_title: String(form.get("review_title") ?? ""),
      attendees: listValue(form.get("attendees")),
      meeting_summary: String(form.get("meeting_summary") ?? ""),
      operational_observations: listValue(form.get("operational_observations")),
      customer_feedback: String(form.get("customer_feedback") ?? ""),
      agreed_actions: parseActions(String(form.get("agreed_actions") ?? "")),
      blockers: String(form.get("blockers") ?? ""),
      next_focus: String(form.get("next_focus") ?? ""),
    };
    const target = selectedReview
      ? `/api/operational-reviews/tenants/${tenantId}/weekly-reviews/${selectedReview.id}`
      : `/api/operational-reviews/tenants/${tenantId}/weekly-reviews`;
    const response = await fetch(target, {
      method: selectedReview ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setStatus("Could not save weekly review.");
      return;
    }
    const saved = (await response.json()) as WeeklyReview;
    setSelectedReview(saved);
    setStatus("Weekly review saved.");
    await refreshHistory();
  }

  async function updateActionStatus(review: WeeklyReview, actionId: number, nextStatus: string) {
    const response = await fetch(
      `/api/operational-reviews/tenants/${tenantId}/weekly-reviews/${review.id}/actions/${actionId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      },
    );
    if (!response.ok) {
      setStatus("Could not update action status.");
      return;
    }
    setStatus("Action status updated.");
    await refreshHistory();
  }

  async function deleteMilestone(item: OperationalHistoryMilestone) {
    if (!window.confirm(`Delete milestone "${item.title}"?`)) return;
    const response = await fetch(
      `/api/operational-history/tenants/${tenantId}/milestones/${item.id}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      setStatus("Could not delete milestone.");
      return;
    }
    if (milestoneEdit?.id === item.id) setMilestoneEdit(null);
    setStatus("Milestone deleted.");
    await refreshHistory();
  }

  async function deleteNote(item: OperationalHistoryNote) {
    if (!window.confirm(`Delete note "${item.title}"?`)) return;
    const response = await fetch(
      `/api/operational-history/tenants/${tenantId}/notes/${item.id}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      setStatus("Could not delete note.");
      return;
    }
    if (noteEdit?.id === item.id) setNoteEdit(null);
    setStatus("Review note deleted.");
    await refreshHistory();
  }

  return (
    <div className="grid gap-5">
      {status ? (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700">
          {status}
        </div>
      ) : null}

      <section className="grid gap-3 md:grid-cols-4">
        <SummaryCard label="Milestones" value={summary.milestone_count} />
        <SummaryCard label="Notes" value={summary.note_count} />
        <SummaryCard label="Reports" value={summary.report_count} />
        <SummaryCard
          label="Latest generated report"
          value={summary.latest_report ? `v${summary.latest_report.version}` : "None"}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <Panel title="Weekly Reviews">
          <div className="grid gap-3">
            <button
              type="button"
              onClick={() => setSelectedReview(null)}
              className="rounded-lg border border-dashed px-4 py-3 text-left text-sm font-semibold"
            >
              Add weekly review
            </button>
            {weeklyReviews.length ? (
              weeklyReviews.map((review) => (
                <button
                  key={review.id}
                  type="button"
                  onClick={() => setSelectedReview(review)}
                  className={`rounded-lg border bg-white p-4 text-left ${
                    selectedReview?.id === review.id ? "border-primary" : ""
                  }`}
                >
                  <p className="font-semibold text-foreground">
                    Week {review.week_number}: {review.review_title}
                  </p>
                  <p className="mt-1 text-xs uppercase tracking-[0.14em] text-mutedForeground">
                    {formatDate(review.review_date)} · {review.actions.length} actions
                  </p>
                </button>
              ))
            ) : (
              <EmptyState text="No weekly reviews recorded yet." />
            )}
          </div>
        </Panel>

        <Panel
          title={
            selectedReview
              ? `Week ${selectedReview.week_number} Review`
              : "Create weekly review"
          }
        >
          <form
            key={selectedReview?.id ?? "new-review"}
            className="grid gap-3"
            onSubmit={submitWeeklyReview}
          >
            <div className="grid gap-3 sm:grid-cols-[0.35fr_0.65fr]">
              <Input
                name="week_number"
                label="Week"
                type="number"
                min={1}
                defaultValue={selectedReview?.week_number ?? weeklyReviews.length + 1}
              />
              <Input
                name="review_date"
                label="Review date"
                type="date"
                defaultValue={dateInput(selectedReview?.review_date) || today}
              />
            </div>
            <Input
              name="review_title"
              label="Review title"
              defaultValue={selectedReview?.review_title ?? ""}
              required
            />
            <Input
              name="attendees"
              label="Attendees"
              defaultValue={(selectedReview?.attendees ?? []).join(", ")}
            />
            <Textarea
              name="meeting_summary"
              label="Summary"
              defaultValue={selectedReview?.meeting_summary ?? ""}
            />
            <Textarea
              name="operational_observations"
              label="Operational observations"
              defaultValue={(selectedReview?.operational_observations ?? []).join("\n")}
            />
            <Textarea
              name="customer_feedback"
              label="Customer feedback"
              defaultValue={selectedReview?.customer_feedback ?? ""}
            />
            <Textarea
              name="agreed_actions"
              label="Agreed actions"
              defaultValue={selectedReview?.actions.map(actionLine).join("\n") ?? ""}
            />
            <Textarea
              name="blockers"
              label="Blockers"
              defaultValue={selectedReview?.blockers ?? ""}
            />
            <Textarea
              name="next_focus"
              label="Next focus"
              defaultValue={selectedReview?.next_focus ?? ""}
            />
            <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground">
              {selectedReview ? "Save weekly review" : "Create weekly review"}
            </button>
          </form>

          {selectedReview ? (
            <div className="mt-5 rounded-xl border bg-white p-4">
              <h3 className="text-sm font-semibold text-foreground">Action Tracker</h3>
              <div className="mt-3 grid gap-3">
                {selectedReview.actions.length ? (
                  selectedReview.actions.map((action) => (
                    <div
                      key={action.id}
                      className="grid gap-3 rounded-lg bg-slate-50 p-3 sm:grid-cols-[1fr_160px]"
                    >
                      <div>
                        <p className="font-semibold text-foreground">{action.description}</p>
                        <p className="mt-1 text-sm text-mutedForeground">
                          Owner: {action.owner ?? "Unassigned"} · Due:{" "}
                          {action.due_date ? formatDate(action.due_date) : "Not dated"}
                        </p>
                      </div>
                      <Select
                        name={`action-${action.id}`}
                        label="Status"
                        value={action.status}
                        options={["Open", "In Progress", "Completed", "Deferred"]}
                        onChange={(event) =>
                          updateActionStatus(selectedReview, action.id, event.target.value)
                        }
                      />
                    </div>
                  ))
                ) : (
                  <EmptyState text="No actions tracked for this review." />
                )}
              </div>
            </div>
          ) : null}
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
        <Panel title="Milestones">
          <div className="grid gap-3">
            {summary.recent_milestones.length ? (
              summary.recent_milestones.map((item) => (
                <HistoryRow
                  key={item.id}
                  title={item.title}
                  meta={`${label(item.milestone_type)} · ${label(item.status)} · ${formatDate(item.occurred_at)}`}
                  body={item.description}
                  onEdit={() => setMilestoneEdit(item)}
                  onDelete={() => deleteMilestone(item)}
                />
              ))
            ) : (
              <EmptyState text="No milestones recorded yet." />
            )}
          </div>
        </Panel>
        <Panel title={milestoneEdit ? "Edit milestone" : "Add milestone"}>
          <form className="grid gap-3" onSubmit={submitMilestone}>
            <Input name="title" label="Title" defaultValue={milestoneEdit?.title} required />
            <div className="grid gap-3 sm:grid-cols-3">
              <Input
                name="milestone_type"
                label="Type"
                defaultValue={milestoneEdit?.milestone_type ?? "weekly_review"}
              />
              <Select
                name="status"
                label="Status"
                defaultValue={milestoneEdit?.status ?? "pending"}
                options={["pending", "complete", "blocked"]}
              />
              <Input
                name="occurred_at"
                label="Occurred date"
                type="date"
                defaultValue={dateInput(milestoneEdit?.occurred_at)}
              />
            </div>
            <Textarea
              name="description"
              label="Description"
              defaultValue={milestoneEdit?.description ?? ""}
            />
            <div className="flex gap-2">
              <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground">
                {milestoneEdit ? "Save milestone" : "Add milestone"}
              </button>
              {milestoneEdit ? (
                <button
                  type="button"
                  onClick={() => setMilestoneEdit(null)}
                  className="rounded-lg border px-4 py-2 text-sm font-semibold"
                >
                  Cancel
                </button>
              ) : null}
            </div>
          </form>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
        <Panel title="Review notes">
          <div className="grid gap-3">
            {summary.recent_notes.length ? (
              summary.recent_notes.map((item) => (
                <HistoryRow
                  key={item.id}
                  title={item.title}
                  meta={`${label(item.note_type)} · ${formatDate(item.note_date)}`}
                  body={item.body}
                  onEdit={() => setNoteEdit(item)}
                  onDelete={() => deleteNote(item)}
                />
              ))
            ) : (
              <EmptyState text="No review notes recorded yet." />
            )}
          </div>
        </Panel>
        <Panel title={noteEdit ? "Edit review note" : "Add review note"}>
          <form className="grid gap-3" onSubmit={submitNote}>
            <Input name="title" label="Title" defaultValue={noteEdit?.title} required />
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                name="note_type"
                label="Note type"
                defaultValue={noteEdit?.note_type ?? "weekly_review"}
              />
              <Input
                name="note_date"
                label="Note date"
                type="date"
                defaultValue={dateInput(noteEdit?.note_date)}
              />
            </div>
            <Textarea name="body" label="Body" defaultValue={noteEdit?.body ?? ""} required />
            <Input
              name="attendees"
              label="Attendees"
              defaultValue={(noteEdit?.attendees ?? []).join(", ")}
            />
            <Input
              name="actions"
              label="Actions"
              defaultValue={(noteEdit?.actions ?? []).join(", ")}
            />
            <div className="flex gap-2">
              <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground">
                {noteEdit ? "Save note" : "Add note"}
              </button>
              {noteEdit ? (
                <button
                  type="button"
                  onClick={() => setNoteEdit(null)}
                  className="rounded-lg border px-4 py-2 text-sm font-semibold"
                >
                  Cancel
                </button>
              ) : null}
            </div>
          </form>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
        <Panel title="Generated reports">
          <div className="grid gap-3">
            {reports.length ? (
              reports.map((item) => (
                <div key={item.id} className="rounded-lg border bg-white p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-foreground">{item.title}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.14em] text-mutedForeground">
                        {label(item.report_type)} · v{item.version} · {formatPeriod(item)}
                      </p>
                      <p className="mt-2 text-sm text-mutedForeground">
                        Generated {formatDate(item.generated_at)}
                      </p>
                    </div>
                    <a
                      href={`/api/operational-history/tenants/${tenantId}/reports/${item.id}/pdf`}
                      className="rounded-lg border px-3 py-2 text-sm font-semibold"
                    >
                      Download PDF
                    </a>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState text="No report snapshots generated yet." />
            )}
          </div>
        </Panel>
        <Panel title="Generate report snapshot">
          <form className="grid gap-3" onSubmit={generateReport}>
            <Select
              name="report_type"
              label="Report type"
              defaultValue="pilot"
              options={["pilot", "monthly", "executive"]}
            />
            <Input name="title" label="Title" defaultValue="Focused Evaluation Report" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Input name="period_start" label="Period start" type="date" defaultValue={today} />
              <Input name="period_end" label="Period end" type="date" />
            </div>
            <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground">
              Generate Pilot Report
            </button>
          </form>
        </Panel>
      </section>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border bg-card/90 p-5 shadow-panel">
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function HistoryRow({
  title,
  meta,
  body,
  onEdit,
  onDelete,
}: {
  title: string;
  meta: string;
  body?: string | null;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-foreground">{title}</p>
          <p className="mt-1 text-xs uppercase tracking-[0.14em] text-mutedForeground">{meta}</p>
          {body ? <p className="mt-2 line-clamp-2 text-sm text-mutedForeground">{body}</p> : null}
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={onEdit} className="rounded-lg border px-3 py-2 text-xs font-semibold">
            Edit
          </button>
          <button
            onClick={onDelete}
            className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-lg bg-slate-50 p-4 text-sm text-mutedForeground">{text}</div>;
}

function Input({
  label,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="grid gap-1 text-sm font-semibold text-foreground">
      {label}
      <input
        {...props}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-primary"
      />
    </label>
  );
}

function Textarea({
  label,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  return (
    <label className="grid gap-1 text-sm font-semibold text-foreground">
      {label}
      <textarea
        {...props}
        className="min-h-24 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-primary"
      />
    </label>
  );
}

function Select({
  label,
  options,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label: string; options: string[] }) {
  return (
    <label className="grid gap-1 text-sm font-semibold text-foreground">
      {label}
      <select
        {...props}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-primary"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {labelText(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function label(value: string) {
  return labelText(value);
}

function labelText(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value: string | null) {
  if (!value) return "Not dated";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value));
}

function formatPeriod(report: OperationalHistoryReportSnapshot) {
  if (report.period_start && report.period_end) {
    return `${formatDate(report.period_start)} to ${formatDate(report.period_end)}`;
  }
  if (report.period_start) return `from ${formatDate(report.period_start)}`;
  if (report.period_end) return `through ${formatDate(report.period_end)}`;
  return "No period";
}

function dateInput(value?: string | null) {
  return value ? value.slice(0, 10) : "";
}

function dateTimeValue(value: FormDataEntryValue | null) {
  const clean = emptyToNull(value);
  return clean ? `${clean}T00:00:00Z` : null;
}

function emptyToNull(value: FormDataEntryValue | null) {
  const clean = String(value ?? "").trim();
  return clean || null;
}

function listValue(value: FormDataEntryValue | null) {
  return String(value ?? "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseActions(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [description, owner, dueDate, status] = line.split("|").map((item) => item.trim());
      return {
        description,
        owner: owner || null,
        due_date: dueDate || null,
        status: status || "Open",
      };
    });
}

function actionLine(action: {
  description: string;
  owner: string | null;
  due_date: string | null;
  status: string;
}) {
  return [
    action.description,
    action.owner ?? "",
    action.due_date ?? "",
    action.status,
  ].join(" | ");
}
