"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ContextOption {
  plant_id: number;
  plant_code: string;
  plant_name: string;
  material_id: number;
  material_code: string;
  material_name: string;
}

interface ImpactConfig {
  id?: number;
  plant_id: number;
  material_id: number;
  production_line_id: number | null;
  production_rate_mt_per_hour: string;
  finished_goods_value_per_mt: string;
  survivable_hours_without_material: string;
  line_dependency_ratio: string;
  downtime_cost_per_hour: string;
  restart_cost: string;
  restart_time_hours: string;
  substitution_factor: string;
  cascading_impact_factor: string;
  interruption_probability_override: string | null;
  currency: string;
  is_active: boolean;
}

const emptyConfig: ImpactConfig = {
  plant_id: 0,
  material_id: 0,
  production_line_id: null,
  production_rate_mt_per_hour: "",
  finished_goods_value_per_mt: "",
  survivable_hours_without_material: "",
  line_dependency_ratio: "",
  downtime_cost_per_hour: "",
  restart_cost: "",
  restart_time_hours: "",
  substitution_factor: "",
  cascading_impact_factor: "1.00",
  interruption_probability_override: null,
  currency: "INR",
  is_active: true,
};

export function InterruptionImpactConfigForm({
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
  const [form, setForm] = useState<ImpactConfig>({
    ...emptyConfig,
    plant_id: selectedPlantId,
    material_id: selectedMaterialId,
  });
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
    if (nextMaterial !== selectedMaterialId)
      setSelectedMaterialId(nextMaterial);
  }, [contexts, materials, selectedMaterialId, selectedPlantId]);

  useEffect(() => {
    if (!selectedPlantId || !selectedMaterialId) return;
    const query = new URLSearchParams({
      plant_id: String(selectedPlantId),
      material_id: String(selectedMaterialId),
    });
    setMessage("");
    setError("");
    fetch(`/api/impact/interruption-config?${query.toString()}`, {
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response));
        const config = (await response.json()) as ImpactConfig | null;
        setForm({
          ...emptyConfig,
          ...(config ?? {}),
          plant_id: selectedPlantId,
          material_id: selectedMaterialId,
          production_line_id: null,
          interruption_probability_override:
            config?.interruption_probability_override ?? null,
        });
        setMessage(
          config
            ? "Loaded existing configuration."
            : "No existing configuration for this context.",
        );
      })
      .catch((err) => setError(err.message || "Could not load configuration."));
  }, [selectedMaterialId, selectedPlantId]);

  function update(field: keyof ImpactConfig, value: string | boolean | null) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function save() {
    setError("");
    setMessage("");
    const validation = validate(form);
    if (validation) {
      setError(validation);
      return;
    }
    startTransition(async () => {
      const payload = {
        ...form,
        production_line_id: null,
        interruption_probability_override:
          form.interruption_probability_override === ""
            ? null
            : form.interruption_probability_override,
      };
      const response = await fetch("/api/impact/interruption-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      const saved = (await response.json()) as ImpactConfig;
      setForm({
        ...saved,
        interruption_probability_override:
          saved.interruption_probability_override ?? null,
      });
      setMessage("Operational interruption impact configuration saved.");
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
    <>
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Production interruption assumptions</CardTitle>
          <p className="text-sm text-mutedForeground">
            These values affect operational interruption impact calculations for
            the selected context.
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

          <Section title="Production Economics">
            <NumberField
              label="Production rate MT/hour"
              field="production_rate_mt_per_hour"
              form={form}
              update={update}
              helper="Average finished-goods output rate for the affected line or process."
            />
            <NumberField
              label="Finished goods value per MT"
              field="finished_goods_value_per_mt"
              form={form}
              update={update}
              helper="Estimated selling value or realization value of the finished output."
            />
            <NumberField
              label="Downtime cost per hour"
              field="downtime_cost_per_hour"
              form={form}
              update={update}
              helper="Estimated operational cost of the line being down, excluding lost production value."
            />
            <NumberField
              label="Restart cost"
              field="restart_cost"
              form={form}
              update={update}
              helper="One-time cost to restart or stabilize operations after interruption."
            />
            <NumberField
              label="Restart time hours"
              field="restart_time_hours"
              form={form}
              update={update}
              helper="Expected time required to restart or stabilize operations after interruption."
            />
            <Field label="Currency" helper="Three-letter currency code.">
              <input
                value={form.currency}
                onChange={(event) =>
                  update("currency", event.target.value.toUpperCase())
                }
                className={inputClass}
                maxLength={3}
              />
            </Field>
          </Section>

          <Section title="Operational Continuity Behavior">
            <NumberField
              label="Survivable hours without material"
              field="survivable_hours_without_material"
              form={form}
              update={update}
              helper="How long operations can continue before production is impacted if this material becomes unavailable."
            />
            <NumberField
              label="Line dependency ratio"
              field="line_dependency_ratio"
              form={form}
              update={update}
              helper="0.0 = minimal production dependency. 1.0 = production stops completely without this material."
            />
            <NumberField
              label="Substitution factor"
              field="substitution_factor"
              form={form}
              update={update}
              helper="0.0 = no substitute available. 1.0 = fully replaceable operationally."
            />
            <NumberField
              label="Cascading impact factor"
              field="cascading_impact_factor"
              form={form}
              update={update}
              helper="1.0 = no downstream multiplier. Values above 1.0 increase impact for downstream disruption."
            />
            <NumberField
              label="Probability override optional"
              field="interruption_probability_override"
              form={form}
              update={update}
              helper="Optional. Leave blank to let OpsDeck calculate probability from risk severity, inbound trust, freshness, and dependency."
              nullable
            />
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
              {isPending ? "Saving..." : "Save configuration"}
            </button>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Impact Preview</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-mutedForeground">
            Save this configuration. OpsDeck will apply it to matching
            plant-material risks when operational timing data is available.
          </p>
        </CardContent>
      </Card>
    </>
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

function NumberField({
  label,
  field,
  form,
  update,
  helper = "Must be greater than or equal to 0.",
  nullable = false,
}: {
  label: string;
  field: keyof ImpactConfig;
  form: ImpactConfig;
  update: (field: keyof ImpactConfig, value: string | null) => void;
  helper?: string;
  nullable?: boolean;
}) {
  return (
    <Field label={label} helper={helper}>
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

function validate(form: ImpactConfig) {
  const required: Array<keyof ImpactConfig> = [
    "production_rate_mt_per_hour",
    "finished_goods_value_per_mt",
    "survivable_hours_without_material",
    "line_dependency_ratio",
    "downtime_cost_per_hour",
    "restart_cost",
    "restart_time_hours",
    "substitution_factor",
    "cascading_impact_factor",
  ];
  for (const field of required) {
    const value = Number(form[field]);
    if (!Number.isFinite(value) || value < 0)
      return "All economics and hour values must be 0 or greater.";
  }
  for (const field of [
    "line_dependency_ratio",
    "substitution_factor",
  ] as const) {
    const value = Number(form[field]);
    if (value < 0 || value > 1) return "Ratios must be between 0.0 and 1.0.";
  }
  if (
    form.interruption_probability_override !== null &&
    form.interruption_probability_override !== ""
  ) {
    const value = Number(form.interruption_probability_override);
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      return "Probability override must be blank or between 0.0 and 1.0.";
    }
  }
  if (!/^[A-Z]{3}$/.test(form.currency))
    return "Currency must be a three-letter code.";
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

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";
