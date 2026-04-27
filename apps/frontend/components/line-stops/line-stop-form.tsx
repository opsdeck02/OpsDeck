"use client";

import { useMemo, useState, useTransition } from "react";

type ComboOption = {
  plant_id: number;
  plant_name: string;
  material_id: number;
  material_name: string;
};

export function LineStopForm({ options }: { options: ComboOption[] }) {
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const defaultKey = options[0] ? optionKey(options[0]) : "";
  const [selectedKey, setSelectedKey] = useState(defaultKey);

  const selected = useMemo(
    () => options.find((item) => optionKey(item) === selectedKey) ?? options[0],
    [options, selectedKey],
  );

  function submit(formData: FormData) {
    setMessage(null);
    if (!selected) {
      setMessage("Load plant/material combinations before recording incidents.");
      return;
    }

    const stoppedAt = String(formData.get("stopped_at") ?? "");
    const durationHours = String(formData.get("duration_hours") ?? "");
    if (!stoppedAt || !durationHours) {
      setMessage("Stopped date and duration are required.");
      return;
    }

    startTransition(async () => {
      const response = await fetch("/api/line-stops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plant_id: selected.plant_id,
          material_id: selected.material_id,
          stopped_at: new Date(stoppedAt).toISOString(),
          duration_hours: durationHours,
          notes: String(formData.get("notes") ?? "").trim() || null,
        }),
      });
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      if (!response.ok) {
        setMessage(body?.detail ?? "Line-stop incident could not be recorded.");
        return;
      }
      setMessage("Line-stop incident recorded.");
      window.location.reload();
    });
  }

  return (
    <form action={submit} className="space-y-3">
      <select
        value={selectedKey}
        onChange={(event) => setSelectedKey(event.target.value)}
        className="w-full rounded-xl border bg-background px-3 py-2 text-sm"
        disabled={options.length === 0 || isPending}
      >
        {options.map((item) => (
          <option key={optionKey(item)} value={optionKey(item)}>
            {item.plant_name} / {item.material_name}
          </option>
        ))}
      </select>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          name="stopped_at"
          type="datetime-local"
          className="rounded-xl border bg-background px-3 py-2 text-sm"
          disabled={isPending}
        />
        <input
          name="duration_hours"
          type="number"
          min="0.01"
          step="0.01"
          placeholder="Duration hours"
          className="rounded-xl border bg-background px-3 py-2 text-sm"
          disabled={isPending}
        />
      </div>
      <textarea
        name="notes"
        rows={2}
        placeholder="Operational note"
        className="w-full rounded-xl border bg-background px-3 py-2 text-sm"
        disabled={isPending}
      />
      <button
        type="submit"
        disabled={isPending || options.length === 0}
        className="rounded-2xl bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground disabled:opacity-60"
      >
        Record incident
      </button>
      {message ? <p className="rounded-xl bg-muted px-3 py-2 text-sm">{message}</p> : null}
    </form>
  );
}

function optionKey(item: ComboOption) {
  return `${item.plant_id}:${item.material_id}`;
}
