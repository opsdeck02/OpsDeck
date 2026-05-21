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

interface ShipmentInboundTrustConfig {
  id?: number;
  plant_id: number;
  material_id: number;
  visibility_profile: string;
  expected_visibility_cadence_hours: string;
  eta_drift_tolerance_hours: string;
  weak_visibility_threshold: string;
  minimum_trusted_inbound_ratio: string | null;
  allow_unverified_inbound_protection: boolean;
  is_active: boolean;
}

const emptyConfig: ShipmentInboundTrustConfig = {
  plant_id: 0,
  material_id: 0,
  visibility_profile: "unknown",
  expected_visibility_cadence_hours: "24",
  eta_drift_tolerance_hours: "12",
  weak_visibility_threshold: "0.50",
  minimum_trusted_inbound_ratio: null,
  allow_unverified_inbound_protection: false,
  is_active: true,
};

const profileOptions = [
  { label: "Ocean / import shipment", value: "ocean" },
  { label: "Port / discharge movement", value: "port" },
  { label: "Inland truck movement", value: "inland" },
  { label: "Rail movement", value: "rail" },
  { label: "Mixed logistics flow", value: "mixed" },
  { label: "Unknown / varies by shipment", value: "unknown" },
];

const cadenceOptions = [
  { label: "Every 6 hours", value: "6" },
  { label: "Every 12 hours", value: "12" },
  { label: "Every 24 hours", value: "24" },
  { label: "Every 48 hours", value: "48" },
  { label: "Every 72 hours", value: "72" },
  { label: "Enter exact hours", value: "custom" },
];

const etaToleranceOptions = [
  { label: "2 hours", value: "2" },
  { label: "4 hours", value: "4" },
  { label: "12 hours", value: "12" },
  { label: "24 hours", value: "24" },
  { label: "48 hours", value: "48" },
  { label: "Enter exact hours", value: "custom" },
];

const weakThresholdOptions = [
  { label: "Very strict", value: "0.75" },
  { label: "Balanced", value: "0.50" },
  { label: "Tolerant", value: "0.35" },
  { label: "Enter exact ratio", value: "custom" },
];

const minimumTrustedOptions = [
  { label: "No minimum requirement", value: "none" },
  { label: "Low minimum protection", value: "0.25" },
  { label: "Moderate minimum protection", value: "0.50" },
  { label: "High minimum protection", value: "0.75" },
  { label: "Enter exact ratio", value: "custom" },
];

export function ShipmentInboundTrustConfigForm({
  contexts,
}: {
  contexts: ContextOption[];
}) {
  const plants = useMemo(
    () => [...new Map(contexts.map((item) => [item.plant_id, item])).values()],
    [contexts],
  );
  const [selectedPlantId, setSelectedPlantId] = useState(
    plants[0]?.plant_id ?? 0,
  );
  const materials = useMemo(
    () => contexts.filter((item) => item.plant_id === selectedPlantId),
    [contexts, selectedPlantId],
  );
  const [selectedMaterialId, setSelectedMaterialId] = useState(
    materials[0]?.material_id ?? 0,
  );
  const [form, setForm] = useState<ShipmentInboundTrustConfig>({
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
    fetch(`/api/impact/shipment-inbound-trust?${query.toString()}`, {
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response));
        const config =
          (await response.json()) as ShipmentInboundTrustConfig | null;
        setForm({
          ...emptyConfig,
          ...(config ?? {}),
          plant_id: selectedPlantId,
          material_id: selectedMaterialId,
        });
        setMessage(
          config
            ? "Loaded existing shipment trust configuration."
            : "No existing shipment trust configuration for this context.",
        );
      })
      .catch((err) =>
        setError(err.message || "Could not load shipment trust configuration."),
      );
  }, [selectedMaterialId, selectedPlantId]);

  function update(
    field: keyof ShipmentInboundTrustConfig,
    value: string | boolean | null,
  ) {
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
      const response = await fetch("/api/impact/shipment-inbound-trust", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          minimum_trusted_inbound_ratio:
            form.minimum_trusted_inbound_ratio === ""
              ? null
              : form.minimum_trusted_inbound_ratio,
        }),
      });
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      const saved = (await response.json()) as ShipmentInboundTrustConfig;
      setForm(saved);
      setMessage("Shipment and inbound trust configuration saved.");
    });
  }

  if (contexts.length === 0) {
    return (
      <Card className="bg-card/90 shadow-panel">
        <CardContent className="pt-4">
          <p className="text-sm text-mutedForeground">
            No plant/material continuity contexts are available for shipment
            trust configuration.
          </p>
        </CardContent>
      </Card>
    );
  }

  const cadenceChoice = selectedChoice(
    cadenceOptions,
    form.expected_visibility_cadence_hours,
  );
  const etaChoice = selectedChoice(
    etaToleranceOptions,
    form.eta_drift_tolerance_hours,
  );
  const weakChoice = selectedChoice(
    weakThresholdOptions,
    form.weak_visibility_threshold,
  );
  const minimumChoice =
    form.minimum_trusted_inbound_ratio == null
      ? "none"
      : selectedChoice(minimumTrustedOptions, form.minimum_trusted_inbound_ratio);

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Plant-material inbound trust</CardTitle>
        <p className="text-sm text-mutedForeground">
          Calibrate trusted inbound protection without implying physical inbound
          quantity has disappeared.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <Section title="Configuration Context">
          <Field label="Plant">
            <select
              value={selectedPlantId}
              onChange={(event) =>
                setSelectedPlantId(Number(event.target.value))
              }
              className={inputClass}
            >
              {plants.map((item) => (
                <option key={item.plant_id} value={item.plant_id}>
                  {item.plant_name} ({item.plant_code})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Material">
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

        <Section title="Shipment Visibility Profile">
          <ChoiceGroup
            label="What type of inbound movement is this material usually dependent on?"
            value={form.visibility_profile}
            options={profileOptions}
            onChange={(value) => update("visibility_profile", value)}
            helper="This tells OpsDeck what update cadence is operationally normal. Ocean shipments should not be treated like inland trucks."
          />
        </Section>

        <Section title="Expected Update Cadence">
          <ChoiceGroup
            label="How often should OpsDeck normally expect a meaningful shipment update?"
            value={cadenceChoice}
            options={cadenceOptions}
            onChange={(value) =>
              update(
                "expected_visibility_cadence_hours",
                value === "custom" ? "" : value,
              )
            }
            helper="If a shipment is still within its expected cadence and ETA is stable, OpsDeck should not reduce inbound trust aggressively."
          />
          {cadenceChoice === "custom" ? (
            <NumberField
              label="Exact update cadence hours"
              value={form.expected_visibility_cadence_hours}
              onChange={(value) =>
                update("expected_visibility_cadence_hours", value)
              }
            />
          ) : null}
        </Section>

        <Section title="ETA Drift Tolerance">
          <ChoiceGroup
            label="How much ETA movement is operationally acceptable before trust should degrade?"
            value={etaChoice}
            options={etaToleranceOptions}
            onChange={(value) =>
              update("eta_drift_tolerance_hours", value === "custom" ? "" : value)
            }
            helper="Ocean shipments usually tolerate larger ETA movement than inland or near-plant shipments."
          />
          {etaChoice === "custom" ? (
            <NumberField
              label="Exact ETA drift tolerance hours"
              value={form.eta_drift_tolerance_hours}
              onChange={(value) => update("eta_drift_tolerance_hours", value)}
            />
          ) : null}
        </Section>

        <Section title="Inbound Protection Confidence">
          <ChoiceGroup
            label="When should inbound protection be considered weak?"
            value={weakChoice}
            options={weakThresholdOptions}
            onChange={(value) =>
              update("weak_visibility_threshold", value === "custom" ? "" : value)
            }
            helper="If visibility confidence falls below this level, OpsDeck treats inbound protection as weak."
          />
          {weakChoice === "custom" ? (
            <NumberField
              label="Exact weak visibility ratio"
              value={form.weak_visibility_threshold}
              onChange={(value) => update("weak_visibility_threshold", value)}
            />
          ) : null}
          <ChoiceGroup
            label="What minimum trusted inbound ratio should OpsDeck consider operationally safe?"
            value={minimumChoice}
            options={minimumTrustedOptions}
            onChange={(value) =>
              update(
                "minimum_trusted_inbound_ratio",
                value === "none" ? null : value === "custom" ? "" : value,
              )
            }
            helper="If trusted inbound protection falls below this level, OpsDeck may elevate continuity risk."
          />
          {minimumChoice === "custom" ? (
            <NumberField
              label="Exact minimum trusted inbound ratio"
              value={form.minimum_trusted_inbound_ratio ?? ""}
              onChange={(value) =>
                update("minimum_trusted_inbound_ratio", value)
              }
            />
          ) : null}
        </Section>

        <Section title="Unverified Inbound Handling">
          <ChoiceGroup
            label="Should unverified inbound shipments contribute to operational protection?"
            value={form.allow_unverified_inbound_protection ? "yes" : "no"}
            options={[
              {
                label: "No, require verified inbound confidence",
                value: "no",
              },
              {
                label: "Yes, partially trust unverified inbound",
                value: "yes",
              },
            ]}
            onChange={(value) =>
              update("allow_unverified_inbound_protection", value === "yes")
            }
            helper="Unverified inbound means shipment exists in records but lacks enough operational visibility to be strongly trusted."
          />
          <label className="flex items-center gap-2 pt-1 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => update("is_active", event.target.checked)}
              className="h-4 w-4"
            />
            Active configuration
          </label>
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
            {isPending ? "Saving..." : "Save shipment trust"}
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
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label} helper="Must be greater than or equal to 0.">
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass}
        inputMode="decimal"
        placeholder="0"
      />
    </Field>
  );
}

function validate(form: ShipmentInboundTrustConfig) {
  for (const [label, value] of [
    ["Expected update cadence", form.expected_visibility_cadence_hours],
    ["ETA drift tolerance", form.eta_drift_tolerance_hours],
  ] as const) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) {
      return `${label} must be 0 or greater.`;
    }
  }
  const weak = Number(form.weak_visibility_threshold);
  if (!Number.isFinite(weak) || weak < 0 || weak > 1) {
    return "Weak visibility threshold must be between 0.0 and 1.0.";
  }
  if (form.minimum_trusted_inbound_ratio != null) {
    const minimum = Number(form.minimum_trusted_inbound_ratio);
    if (!Number.isFinite(minimum) || minimum < 0 || minimum > 1) {
      return "Minimum trusted inbound ratio must be between 0.0 and 1.0.";
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
  } catch {
    return "Request failed.";
  }
  return "Request failed.";
}

function selectedChoice(
  options: Array<{ value: string }>,
  current: string | null,
) {
  if (current == null) return "none";
  const match = options.find(
    (option) => option.value !== "custom" && valuesEqual(option.value, current),
  );
  return match?.value ?? "custom";
}

function valuesEqual(left: string, right: string) {
  const a = Number(left);
  const b = Number(right);
  return Number.isFinite(a) && Number.isFinite(b) ? a === b : left === right;
}

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";
const choiceClass =
  "flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm transition hover:bg-slate-50";
