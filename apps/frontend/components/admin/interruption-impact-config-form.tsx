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

const noDependencyDefaults: Pick<
  ImpactConfig,
  | "production_rate_mt_per_hour"
  | "finished_goods_value_per_mt"
  | "survivable_hours_without_material"
  | "substitution_factor"
  | "downtime_cost_per_hour"
  | "restart_cost"
  | "restart_time_hours"
  | "cascading_impact_factor"
  | "interruption_probability_override"
> = {
  production_rate_mt_per_hour: "0",
  finished_goods_value_per_mt: "0",
  survivable_hours_without_material: "0",
  substitution_factor: "1",
  downtime_cost_per_hour: "0",
  restart_cost: "0",
  restart_time_hours: "0",
  cascading_impact_factor: "1",
  interruption_probability_override: null,
};

const dependencyOptions = [
  { label: "No meaningful production impact", value: "0" },
  { label: "Minor throughput reduction", value: "0.25" },
  { label: "Moderate operational disruption", value: "0.5" },
  { label: "Severe production disruption", value: "0.75" },
  { label: "Production stops completely", value: "1" },
];

const bufferOptions = [
  { label: "Immediate impact", value: "0" },
  { label: "Less than 2 hours", value: "1" },
  { label: "2-8 hours", value: "4" },
  { label: "8-24 hours", value: "12" },
  { label: "More than 24 hours", value: "24" },
  { label: "Enter exact hours", value: "custom" },
];

const substitutionOptions = [
  { label: "No substitute possible", value: "0" },
  { label: "Limited substitute possible", value: "0.25" },
  { label: "Partial operational substitution", value: "0.5" },
  { label: "High substitution flexibility", value: "0.75" },
  { label: "Fully replaceable", value: "1" },
];

const cascadingOptions = [
  { label: "Minimal downstream impact", value: "1" },
  { label: "Moderate downstream impact", value: "1.25" },
  { label: "High downstream dependency", value: "1.5" },
  { label: "Plant-wide cascading disruption", value: "2" },
];

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
  const [restartRequired, setRestartRequired] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
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
        setRestartRequired(
          Number(config?.restart_cost ?? 0) > 0 ||
            Number(config?.restart_time_hours ?? 0) > 0,
        );
        setAdvancedOpen(Boolean(config?.interruption_probability_override));
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

  function setDependency(value: string) {
    setForm((current) => ({
      ...current,
      line_dependency_ratio: value,
      ...(value === "0" ? noDependencyDefaults : {}),
    }));
    if (value === "0") {
      setRestartRequired(false);
      setAdvancedOpen(false);
    }
  }

  function setRestart(value: boolean) {
    setRestartRequired(value);
    if (!value) {
      setForm((current) => ({
        ...current,
        restart_cost: "0",
        restart_time_hours: "0",
      }));
    }
  }

  const isNoDependency =
    form.line_dependency_ratio !== "" &&
    Number(form.line_dependency_ratio) === 0;
  const hasDependency = Number(form.line_dependency_ratio) > 0;
  const selectedBufferOption = bufferOptions.find(
    (option) =>
      option.value !== "custom" &&
      valuesEqual(option.value, form.survivable_hours_without_material),
  );
  const bufferChoice = selectedBufferOption
    ? selectedBufferOption.value
    : "custom";
  const saveForm = isNoDependency
    ? { ...form, ...noDependencyDefaults, line_dependency_ratio: "0" }
    : {
        ...form,
        restart_cost: restartRequired ? form.restart_cost : "0",
        restart_time_hours: restartRequired ? form.restart_time_hours : "0",
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
      const payload = {
        ...saveForm,
        production_line_id: null,
        interruption_probability_override:
          saveForm.interruption_probability_override
            ? saveForm.interruption_probability_override
            : null,
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
      setRestartRequired(
        Number(saved.restart_cost) > 0 || Number(saved.restart_time_hours) > 0,
      );
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

          <Section title="Operational Dependency">
            <ChoiceGroup
              label="If this material becomes unavailable, how badly is production affected?"
              value={form.line_dependency_ratio}
              options={dependencyOptions}
              onChange={setDependency}
            />
          </Section>

          {isNoDependency ? (
            <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-mutedForeground">
              No production interruption impact will be calculated because this
              material has no meaningful production dependency.
            </p>
          ) : null}

          {hasDependency ? (
            <>
              <Section title="Operational Buffer / Survivability">
                <ChoiceGroup
                  label="After usable stock is exhausted, how long can operations continue before production is impacted?"
                  value={bufferChoice}
                  options={bufferOptions}
                  onChange={(value) => {
                    if (value !== "custom") {
                      update("survivable_hours_without_material", value);
                    } else {
                      update("survivable_hours_without_material", "");
                    }
                  }}
                  helper="This is the operating buffer after usable stock is exhausted. For a fully dependent material, this may still be greater than zero if buffer stock, process inventory, or temporary operating flexibility exists."
                />
                {bufferChoice === "custom" ? (
                  <NumberField
                    label="Exact survivable hours"
                    field="survivable_hours_without_material"
                    form={form}
                    update={update}
                    helper="Enter the specific number of operating hours available after usable stock is exhausted."
                  />
                ) : null}
              </Section>

              <Section title="Substitution / Mitigation">
                <ChoiceGroup
                  label="Can this material be operationally substituted?"
                  value={form.substitution_factor}
                  options={substitutionOptions}
                  onChange={(value) => update("substitution_factor", value)}
                  helper="Substitution reduces estimated interruption impact. Use 0 when no practical substitute exists."
                />
              </Section>

              <Section title="Output Exposure">
                <NumberField
                  label="Production rate MT/hour"
                  field="production_rate_mt_per_hour"
                  form={form}
                  update={update}
                  helper="Total affected output rate for this process or line, across all relevant products."
                />
                <NumberField
                  label="Weighted output value per MT"
                  field="finished_goods_value_per_mt"
                  form={form}
                  update={update}
                  helper="Use a blended output value if this process supports multiple finished products."
                />
              </Section>

              <Section title="Additional Operational Costs">
                <NumberField
                  label="Additional downtime cost per hour"
                  field="downtime_cost_per_hour"
                  form={form}
                  update={update}
                  helper="Extra operating cost per hour during downtime, excluding lost production value. Leave 0 if unknown."
                />
                <div className="grid gap-1.5 text-sm">
                  <span className="font-medium">Restart effort</span>
                  <label className="flex min-h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={restartRequired}
                      onChange={(event) => setRestart(event.target.checked)}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Does restarting operations involve significant cost or
                    stabilization effort?
                  </label>
                </div>
                {restartRequired ? (
                  <>
                    <NumberField
                      label="Restart cost"
                      field="restart_cost"
                      form={form}
                      update={update}
                      helper="One-time cost to restart or stabilize operations after interruption. Leave 0 if unknown."
                    />
                    <NumberField
                      label="Restart time hours"
                      field="restart_time_hours"
                      form={form}
                      update={update}
                      helper="Expected time required to restart or stabilize operations after interruption."
                    />
                  </>
                ) : null}
              </Section>

              <Section title="Cascading Impact">
                <ChoiceGroup
                  label="Does disruption in this process significantly affect downstream operations?"
                  value={form.cascading_impact_factor}
                  options={cascadingOptions}
                  onChange={(value) => update("cascading_impact_factor", value)}
                  helper="Cascading impact increases estimated exposure when disruption affects downstream operations."
                />
              </Section>

              <section className="space-y-3">
                <button
                  type="button"
                  onClick={() => setAdvancedOpen((current) => !current)}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm font-semibold transition hover:bg-slate-50"
                >
                  <span>Advanced Probability Override</span>
                  <span className="text-mutedForeground">
                    {advancedOpen ? "Hide" : "Show"}
                  </span>
                </button>
                {advancedOpen ? (
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    <NumberField
                      label="Probability override optional"
                      field="interruption_probability_override"
                      form={form}
                      update={update}
                      helper="Optional. Leave blank to let OpsDeck calculate probability from risk severity, inbound trust, freshness, and dependency."
                      nullable
                    />
                  </div>
                ) : null}
              </section>
            </>
          ) : null}

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

function ChoiceGroup({
  label,
  value,
  options,
  onChange,
  helper,
}: {
  label: string;
  value: string | null;
  options: Array<{ label: string; value: string }>;
  onChange: (value: string) => void;
  helper?: string;
}) {
  return (
    <fieldset className="space-y-2 md:col-span-2 xl:col-span-3">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm transition hover:bg-slate-50"
          >
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
    if (form[field] === "" || form[field] === null) {
      return "Required operational values must be completed before saving.";
    }
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
  if (Number(form.cascading_impact_factor) < 1) {
    return "Cascading impact factor must be 1.0 or greater.";
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

function valuesEqual(left: string | null, right: string) {
  if (left === null) return false;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return leftNumber === rightNumber;
  }
  return left === right;
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
