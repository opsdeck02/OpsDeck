"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import type { ReactNode } from "react";

import { ConfigurationValidationSummary } from "@/components/admin/configuration-validation-summary";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ContextOption {
  plant_id: number;
  plant_code: string;
  plant_name: string;
  material_id: number;
  material_code: string;
  material_name: string;
}

interface ContinuityThresholdConfig {
  id?: number;
  plant_id: number;
  material_id: number;
  warning_days: string;
  threshold_days: string;
  minimum_buffer_stock_days: string | null;
  minimum_buffer_stock_mt: string | null;
  stockout_alert_horizon_days: string | null;
}

const emptyConfig: ContinuityThresholdConfig = {
  plant_id: 0,
  material_id: 0,
  warning_days: "",
  threshold_days: "",
  minimum_buffer_stock_days: null,
  minimum_buffer_stock_mt: null,
  stockout_alert_horizon_days: null,
};

const warningOptions = [
  { label: "Only when operationally urgent", value: "3" },
  { label: "Short operational visibility", value: "7" },
  { label: "Standard operational planning", value: "14" },
  { label: "Long procurement visibility", value: "30" },
  { label: "Strategic/import-sensitive material", value: "60" },
  { label: "Enter exact days", value: "custom" },
];

const criticalOptions = [
  { label: "Immediate operational risk", value: "1" },
  { label: "Severe continuity concern", value: "3" },
  { label: "High production exposure", value: "7" },
  { label: "Strategic operational exposure", value: "15" },
  { label: "Enter exact days", value: "custom" },
];

const stockoutOptions = [
  { label: "24 hours", value: "1" },
  { label: "72 hours", value: "3" },
  { label: "7 days", value: "7" },
  { label: "14 days", value: "14" },
  { label: "Enter exact days", value: "custom" },
];

export function ContinuityThresholdsConfigForm({
  contexts,
}: {
  contexts: ContextOption[];
}) {
  const [selectedPlantId, setSelectedPlantId] = useState(
    contexts[0]?.plant_id ?? 0,
  );
  const materials = useMemo(
    () => contexts.filter((item) => item.plant_id === selectedPlantId),
    [contexts, selectedPlantId],
  );
  const [selectedMaterialId, setSelectedMaterialId] = useState(
    materials[0]?.material_id ?? 0,
  );
  const [form, setForm] = useState<ContinuityThresholdConfig>({
    ...emptyConfig,
    plant_id: selectedPlantId,
    material_id: selectedMaterialId,
  });
  const [reserveRequired, setReserveRequired] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    const nextMaterial = contexts.find(
      (item) =>
        item.plant_id === selectedPlantId &&
        item.material_id === selectedMaterialId,
    )
      ? selectedMaterialId
      : (materials[0]?.material_id ?? 0);
    if (nextMaterial !== selectedMaterialId) {
      setSelectedMaterialId(nextMaterial);
    }
  }, [contexts, materials, selectedMaterialId, selectedPlantId]);

  useEffect(() => {
    if (!selectedPlantId || !selectedMaterialId) return;
    const query = new URLSearchParams({
      plant_id: String(selectedPlantId),
      material_id: String(selectedMaterialId),
    });
    setMessage("");
    setError("");
    fetch(`/api/impact/continuity-thresholds?${query.toString()}`, {
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response));
        const config =
          (await response.json()) as ContinuityThresholdConfig | null;
        setForm({
          ...emptyConfig,
          ...(config ?? {}),
          plant_id: selectedPlantId,
          material_id: selectedMaterialId,
        });
        setReserveRequired(
          config?.minimum_buffer_stock_days != null ||
            config?.minimum_buffer_stock_mt != null,
        );
        setMessage(
          config
            ? "Loaded existing threshold configuration."
            : "No existing threshold configuration for this context.",
        );
      })
      .catch((err) =>
        setError(err.message || "Could not load threshold configuration."),
      );
  }, [selectedMaterialId, selectedPlantId]);

  function update(
    field: keyof ContinuityThresholdConfig,
    value: string | null,
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function setReserve(value: boolean) {
    setReserveRequired(value);
    if (!value) {
      setForm((current) => ({
        ...current,
        minimum_buffer_stock_days: null,
        minimum_buffer_stock_mt: null,
      }));
    }
  }

  const warningChoice = selectedChoice(warningOptions, form.warning_days);
  const criticalChoice = selectedChoice(criticalOptions, form.threshold_days);
  const stockoutChoice = selectedChoice(
    stockoutOptions,
    form.stockout_alert_horizon_days,
  );
  const saveForm: ContinuityThresholdConfig = {
    ...form,
    minimum_buffer_stock_days: reserveRequired
      ? emptyStringToNull(form.minimum_buffer_stock_days)
      : null,
    minimum_buffer_stock_mt: reserveRequired
      ? emptyStringToNull(form.minimum_buffer_stock_mt)
      : null,
    stockout_alert_horizon_days: emptyStringToNull(
      form.stockout_alert_horizon_days,
    ),
  };

  function save() {
    setError("");
    setMessage("");
    const validation = validate(saveForm);
    if (validation) {
      setError(validation);
      return;
    }
    startTransition(async () => {
      const response = await fetch("/api/impact/continuity-thresholds", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(saveForm),
      });
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      const saved = (await response.json()) as ContinuityThresholdConfig;
      setForm(saved);
      setReserveRequired(
        saved.minimum_buffer_stock_days != null ||
          saved.minimum_buffer_stock_mt != null,
      );
      setMessage("Continuity threshold configuration saved.");
    });
  }

  if (contexts.length === 0) {
    return (
      <Card className="bg-card/90 shadow-panel">
        <CardContent className="pt-4">
          <p className="text-sm text-mutedForeground">
            No plant/material continuity contexts are available for
            configuration.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Plant-material thresholds</CardTitle>
        <p className="text-sm text-mutedForeground">
          These settings calibrate warning and critical continuity boundaries
          for the selected material context.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <Section title="Configuration Context">
          <Field label="Plant" helper="Required plant context.">
            <select
              value={selectedPlantId}
              onChange={(event) =>
                setSelectedPlantId(Number(event.target.value))
              }
              className={inputClass}
            >
              {[
                ...new Map(
                  contexts.map((item) => [item.plant_id, item]),
                ).values(),
              ].map((item) => (
                <option key={item.plant_id} value={item.plant_id}>
                  {item.plant_name} ({item.plant_code})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Material" helper="Required material dependency.">
            <select
              value={selectedMaterialId}
              onChange={(event) =>
                setSelectedMaterialId(Number(event.target.value))
              }
              className={inputClass}
            >
              {materials.map((item) => (
                <option key={item.material_id} value={item.material_id}>
                  {item.material_name} ({item.material_code})
                </option>
              ))}
            </select>
          </Field>
        </Section>

        <ConfigurationValidationSummary
          plantId={selectedPlantId}
          materialId={selectedMaterialId}
        />

        <Section title="Warning Timing">
          <ChoiceGroup
            label="How early should OpsDeck start warning about this material?"
            value={warningChoice}
            options={warningOptions}
            onChange={(value) => {
              update("warning_days", value === "custom" ? "" : value);
            }}
            helper="Warning threshold should usually be earlier than the critical threshold."
          />
          {warningChoice === "custom" ? (
            <NumberField
              label="Exact warning days"
              field="warning_days"
              form={form}
              update={update}
            />
          ) : null}
        </Section>

        <Section title="Critical Timing">
          <ChoiceGroup
            label="When should this material be considered operationally critical?"
            value={criticalChoice}
            options={criticalOptions}
            onChange={(value) => {
              update("threshold_days", value === "custom" ? "" : value);
            }}
            helper="Critical threshold is the point where the material needs immediate operational attention."
          />
          {criticalChoice === "custom" ? (
            <NumberField
              label="Exact critical days"
              field="threshold_days"
              form={form}
              update={update}
            />
          ) : null}
        </Section>

        <Section title="Protected Reserve">
          <div className="space-y-2 md:col-span-2 xl:col-span-3">
            <p className="text-sm font-medium">
              Should OpsDeck treat this material as requiring protected reserve
              stock?
            </p>
            <div className="grid gap-2 md:grid-cols-2">
              <label className={choiceClass}>
                <input
                  type="radio"
                  checked={!reserveRequired}
                  onChange={() => setReserve(false)}
                  className="h-4 w-4 border-slate-300"
                />
                No
              </label>
              <label className={choiceClass}>
                <input
                  type="radio"
                  checked={reserveRequired}
                  onChange={() => setReserve(true)}
                  className="h-4 w-4 border-slate-300"
                />
                Yes
              </label>
            </div>
            <p className="max-w-3xl text-xs leading-4 text-mutedForeground">
              Use reserve stock when the client never wants this material to
              fall below a protected operating buffer.
            </p>
          </div>
          {reserveRequired ? (
            <>
              <NumberField
                label="Protected reserve days optional"
                field="minimum_buffer_stock_days"
                form={form}
                update={update}
                nullable
              />
              <NumberField
                label="Protected reserve MT optional"
                field="minimum_buffer_stock_mt"
                form={form}
                update={update}
                nullable
              />
            </>
          ) : null}
        </Section>

        <Section title="Projected Stockout Alert Horizon">
          <ChoiceGroup
            label="How early should OpsDeck escalate projected stockout risk?"
            value={stockoutChoice}
            options={stockoutOptions}
            onChange={(value) => {
              update(
                "stockout_alert_horizon_days",
                value === "custom" ? "" : value,
              );
            }}
            helper="OpsDeck uses this horizon when evaluating projected stockout risk for this plant-material context."
          />
          {stockoutChoice === "custom" ? (
            <NumberField
              label="Exact stockout alert days"
              field="stockout_alert_horizon_days"
              form={form}
              update={update}
              nullable
            />
          ) : null}
        </Section>

        {error ? (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {message ? (
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground">
            {message}
          </p>
        ) : null}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={save}
            disabled={isPending}
            className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {isPending ? "Saving..." : "Save thresholds"}
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{children}</div>
    </section>
  );
}

function Field({
  label,
  helper,
  children,
}: {
  label: string;
  helper?: string;
  children: ReactNode;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {helper ? (
        <span className="text-xs leading-4 text-mutedForeground">{helper}</span>
      ) : null}
    </label>
  );
}

function ChoiceGroup({
  label,
  value,
  options,
  onChange,
  helper,
}: {
  label: string;
  value: string;
  options: Array<{ label: string; value: string }>;
  onChange: (value: string) => void;
  helper?: string;
}) {
  return (
    <fieldset className="space-y-2 md:col-span-2 xl:col-span-3">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {options.map((option) => (
          <label key={option.value} className={choiceClass}>
            <input
              type="radio"
              value={option.value}
              checked={valuesEqual(value, option.value)}
              onChange={() => onChange(option.value)}
              className="h-4 w-4 border-slate-300"
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
      {helper ? (
        <p className="max-w-3xl text-xs leading-4 text-mutedForeground">
          {helper}
        </p>
      ) : null}
    </fieldset>
  );
}

function NumberField({
  label,
  field,
  form,
  update,
  nullable = false,
}: {
  label: string;
  field: keyof ContinuityThresholdConfig;
  form: ContinuityThresholdConfig;
  update: (
    field: keyof ContinuityThresholdConfig,
    value: string | null,
  ) => void;
  nullable?: boolean;
}) {
  return (
    <Field label={label} helper="Must be greater than or equal to 0.">
      <input
        value={(form[field] as string | null) ?? ""}
        onChange={(event) =>
          update(field, event.target.value || (nullable ? null : ""))
        }
        className={inputClass}
        inputMode="decimal"
        placeholder={nullable ? "Optional" : "0"}
      />
    </Field>
  );
}

function validate(form: ContinuityThresholdConfig) {
  if (form.warning_days === "" || form.threshold_days === "") {
    return "Warning and critical timing must be completed before saving.";
  }
  const warning = Number(form.warning_days);
  const critical = Number(form.threshold_days);
  if (!Number.isFinite(warning) || warning < 0) {
    return "Warning days must be 0 or greater.";
  }
  if (!Number.isFinite(critical) || critical < 0) {
    return "Critical threshold must be 0 or greater.";
  }
  if (warning < critical) {
    return "Warning threshold must be greater than or equal to the critical threshold.";
  }
  for (const [label, value] of [
    ["Protected reserve days", form.minimum_buffer_stock_days],
    ["Protected reserve MT", form.minimum_buffer_stock_mt],
    ["Projected stockout alert horizon", form.stockout_alert_horizon_days],
  ] as const) {
    if (value === null || value === "") continue;
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) {
      return `${label} must be 0 or greater.`;
    }
  }
  return "";
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item: { msg?: string }) => item.msg ?? "Validation error")
        .join(" ");
    }
    return "Request failed.";
  } catch {
    return "Request failed.";
  }
}

function selectedChoice(
  options: Array<{ value: string }>,
  value: string | null,
) {
  const matched = options.find(
    (option) => option.value !== "custom" && valuesEqual(value, option.value),
  );
  return matched?.value ?? "custom";
}

function valuesEqual(left: string | null, right: string) {
  if (left === null) return false;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return leftNumber === rightNumber;
  }
  return left === right;
}

function emptyStringToNull(value: string | null) {
  return value === "" ? null : value;
}

const choiceClass =
  "flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm transition hover:bg-slate-50";

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";
