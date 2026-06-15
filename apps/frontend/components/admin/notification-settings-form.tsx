"use client";

import { useEffect, useState, useTransition } from "react";
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface NotificationSettings {
  critical_alerts_enabled: boolean;
  weekly_digest_enabled: boolean;
  recipients_to: string[];
  recipients_cc: string[];
  pilot_contacts: string[];
  digest_day: string;
  digest_time: string;
  tenant_timezone: string;
  cooldown_hours: number;
}

const defaultSettings: NotificationSettings = {
  critical_alerts_enabled: true,
  weekly_digest_enabled: true,
  recipients_to: [],
  recipients_cc: [],
  pilot_contacts: [],
  digest_day: "monday",
  digest_time: "08:00",
  tenant_timezone: "Asia/Kolkata",
  cooldown_hours: 24,
};

export function NotificationSettingsForm() {
  const [form, setForm] = useState<NotificationSettings>(defaultSettings);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    fetch("/api/notifications/settings", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response));
        setForm((await response.json()) as NotificationSettings);
      })
      .catch((err) =>
        setError(err.message || "Could not load notification settings."),
      );
  }, []);

  function update<K extends keyof NotificationSettings>(
    field: K,
    value: NotificationSettings[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function save() {
    setError("");
    setMessage("");
    startTransition(async () => {
      const response = await fetch("/api/notifications/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      setForm((await response.json()) as NotificationSettings);
      setMessage("Notification settings saved.");
    });
  }

  function sendTest(path: string, label: string) {
    setError("");
    setMessage("");
    startTransition(async () => {
      const response = await fetch(path, { method: "POST" });
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      const body = await response.json();
      setMessage(
        `${label}: ${body.status}${
          body.skipped_reason ? ` - ${body.skipped_reason}` : ""
        }`,
      );
    });
  }

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Notification Settings</CardTitle>
        <p className="text-sm leading-6 text-mutedForeground">
          Configure email recipients, alert cooldown, and weekly digest timing.
          Delivery uses the pilot-safe console sender until external email is connected.
        </p>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-3 rounded-lg bg-slate-50 p-3 text-sm font-semibold">
            <input
              type="checkbox"
              checked={form.critical_alerts_enabled}
              onChange={(event) =>
                update("critical_alerts_enabled", event.target.checked)
              }
            />
            Immediate critical alerts
          </label>
          <label className="flex items-center gap-3 rounded-lg bg-slate-50 p-3 text-sm font-semibold">
            <input
              type="checkbox"
              checked={form.weekly_digest_enabled}
              onChange={(event) =>
                update("weekly_digest_enabled", event.target.checked)
              }
            />
            Weekly continuity digest
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <TextArea
            label="To recipients"
            value={form.recipients_to.join("\n")}
            onChange={(value) => update("recipients_to", parseEmails(value))}
          />
          <TextArea
            label="CC recipients"
            value={form.recipients_cc.join("\n")}
            onChange={(value) => update("recipients_cc", parseEmails(value))}
          />
          <TextArea
            label="Pilot contacts"
            value={form.pilot_contacts.join("\n")}
            onChange={(value) => update("pilot_contacts", parseEmails(value))}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Field label="Digest day">
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              value={form.digest_day}
              onChange={(event) => update("digest_day", event.target.value)}
            >
              {["monday", "tuesday", "wednesday", "thursday", "friday"].map(
                (day) => (
                  <option key={day} value={day}>
                    {day[0].toUpperCase() + day.slice(1)}
                  </option>
                ),
              )}
            </select>
          </Field>
          <Field label="Digest time">
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              type="time"
              value={form.digest_time}
              onChange={(event) => update("digest_time", event.target.value)}
            />
          </Field>
          <Field label="Tenant timezone">
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              value={form.tenant_timezone}
              onChange={(event) => update("tenant_timezone", event.target.value)}
            />
          </Field>
          <Field label="Cooldown hours">
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              min={1}
              max={168}
              type="number"
              value={form.cooldown_hours}
              onChange={(event) =>
                update("cooldown_hours", Number(event.target.value))
              }
            />
          </Field>
        </div>

        {message ? (
          <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700">
            {message}
          </p>
        ) : null}
        {error ? (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground disabled:opacity-60"
            disabled={isPending}
            onClick={save}
            type="button"
          >
            Save settings
          </button>
          <button
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 disabled:opacity-60"
            disabled={isPending}
            onClick={() =>
              sendTest("/api/notifications/test-critical-alert", "Critical alert test")
            }
            type="button"
          >
            Send test critical alert
          </button>
          <button
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 disabled:opacity-60"
            disabled={isPending}
            onClick={() =>
              sendTest("/api/notifications/test-digest", "Weekly digest test")
            }
            type="button"
          >
            Send test digest
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <textarea
        className="mt-1 min-h-32 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="text-sm font-semibold text-slate-700">
      {label}
      {children}
    </label>
  );
}

function parseEmails(value: string) {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json();
    return body.detail ?? "Request failed.";
  } catch {
    return "Request failed.";
  }
}
