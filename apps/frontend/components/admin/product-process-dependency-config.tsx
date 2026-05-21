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

interface ProductionLine {
  id: number;
  plant_id: number;
  code: string;
  name: string;
  is_active: boolean;
}

interface ProcessProductDependency {
  id: number;
  process_id: number;
  product_name: string;
  output_share_ratio: string;
  product_value_per_mt: string;
  operational_criticality_factor: string;
  is_active: boolean;
}

interface MaterialProcessDependency {
  id: number;
  material_id: number;
  process_id: number;
  dependency_ratio: string;
  substitution_factor: string | null;
  survivability_hours: string | null;
  is_active: boolean;
}

const criticalityOptions = [
  { label: "Low operational priority", value: "0.75" },
  { label: "Standard priority", value: "1" },
  { label: "High operational priority", value: "1.25" },
  { label: "Strategic / customer-critical output", value: "1.5" },
  { label: "Enter exact factor", value: "custom" },
];

const dependencyOptions = [
  { label: "Minimal dependency", value: "0.25" },
  { label: "Moderate dependency", value: "0.5" },
  { label: "Severe dependency", value: "0.75" },
  { label: "Process stops without it", value: "1" },
  { label: "Enter exact ratio", value: "custom" },
];

const substitutionOptions = [
  { label: "Use existing interruption config fallback", value: "fallback" },
  { label: "No substitute possible", value: "0" },
  { label: "Limited substitute possible", value: "0.25" },
  { label: "Partial substitution", value: "0.5" },
  { label: "High substitution flexibility", value: "0.75" },
  { label: "Fully replaceable", value: "1" },
];

const survivabilityOptions = [
  { label: "Use existing interruption config fallback", value: "fallback" },
  { label: "Immediate impact", value: "0" },
  { label: "Less than 2 hours", value: "1" },
  { label: "2-8 hours", value: "4" },
  { label: "8-24 hours", value: "12" },
  { label: "More than 24 hours", value: "24" },
  { label: "Enter exact hours", value: "custom" },
];

type Tab = "processes" | "product-mix" | "material-dependency";

export function ProductProcessDependencyConfig({
  contexts,
}: {
  contexts: ContextOption[];
}) {
  const plants = useMemo(
    () => [...new Map(contexts.map((item) => [item.plant_id, item])).values()],
    [contexts],
  );
  const [tab, setTab] = useState<Tab>("processes");
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
  const [lines, setLines] = useState<ProductionLine[]>([]);
  const [selectedProcessId, setSelectedProcessId] = useState(0);
  const [productRows, setProductRows] = useState<ProcessProductDependency[]>(
    [],
  );
  const [materialRows, setMaterialRows] = useState<MaterialProcessDependency[]>(
    [],
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const hasActiveProcesses = lines.some((line) => line.is_active);

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
    if (!selectedPlantId) return;
    fetchLines(selectedPlantId)
      .then((items) => {
        setLines(items);
        setSelectedProcessId((current) =>
          items.some((line) => line.id === current) ? current : (items[0]?.id ?? 0),
        );
      })
      .catch((err) => setError(err.message || "Could not load processes."));
  }, [selectedPlantId]);

  useEffect(() => {
    setSelectedProcessId((current) =>
      lines.some((line) => line.id === current) ? current : (lines[0]?.id ?? 0),
    );
  }, [lines]);

  useEffect(() => {
    if (!hasActiveProcesses && tab !== "processes") {
      setTab("processes");
    }
  }, [hasActiveProcesses, tab]);

  useEffect(() => {
    if (!selectedProcessId) {
      setProductRows([]);
      return;
    }
    fetchRows<ProcessProductDependency>(
      `/api/impact/process-product-dependencies?process_id=${selectedProcessId}`,
    )
      .then(setProductRows)
      .catch((err) => setError(err.message || "Could not load product mix."));
  }, [selectedProcessId]);

  useEffect(() => {
    if (!selectedPlantId) return;
    fetchRows<MaterialProcessDependency>(
      `/api/impact/material-process-dependencies?plant_id=${selectedPlantId}`,
    )
      .then(setMaterialRows)
      .catch((err) =>
        setError(err.message || "Could not load material dependencies."),
      );
  }, [selectedPlantId]);

  function refreshAfterSave(nextMessage: string) {
    setMessage(nextMessage);
    setError("");
    if (selectedPlantId) {
      fetchLines(selectedPlantId).then(setLines);
      fetchRows<MaterialProcessDependency>(
        `/api/impact/material-process-dependencies?plant_id=${selectedPlantId}`,
      ).then(setMaterialRows);
    }
    if (selectedProcessId) {
      fetchRows<ProcessProductDependency>(
        `/api/impact/process-product-dependencies?process_id=${selectedProcessId}`,
      ).then(setProductRows);
    }
  }

  if (contexts.length === 0) {
    return (
      <Card className="bg-card/90 shadow-panel">
        <CardContent className="pt-4">
          <p className="text-sm text-mutedForeground">
            No plant/material continuity contexts are available for dependency
            configuration.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader className="space-y-3">
        <div>
          <CardTitle>Operational dependency calibration</CardTitle>
          <p className="mt-1 max-w-3xl text-sm leading-5 text-mutedForeground">
            If no product/process dependency is configured for a material,
            OpsDeck uses the existing weighted output value fallback.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <TabButton active={tab === "processes"} onClick={() => setTab("processes")}>
            Processes / Lines
          </TabButton>
          <TabButton
            active={tab === "product-mix"}
            disabled={!hasActiveProcesses}
            onClick={() => setTab("product-mix")}
          >
            Product Mix
          </TabButton>
          <TabButton
            active={tab === "material-dependency"}
            disabled={!hasActiveProcesses}
            onClick={() => setTab("material-dependency")}
          >
            Material Dependency
          </TabButton>
        </div>
        {!hasActiveProcesses ? (
          <p className="text-xs leading-4 text-mutedForeground">
            Product mix and material dependency require at least one
            process/line.
          </p>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-5">
        <ContextSelectors
          plants={plants}
          materials={materials}
          lines={lines}
          selectedPlantId={selectedPlantId}
          selectedMaterialId={selectedMaterialId}
          selectedProcessId={selectedProcessId}
          setSelectedPlantId={setSelectedPlantId}
          setSelectedMaterialId={setSelectedMaterialId}
          setSelectedProcessId={setSelectedProcessId}
          showMaterial={tab === "material-dependency"}
          showProcess={tab !== "processes"}
        />

        <ConfigurationValidationSummary
          plantId={selectedPlantId}
          materialId={selectedMaterialId}
        />

        {tab === "processes" ? (
          <ProcessesSection
            selectedPlantId={selectedPlantId}
            lines={lines}
            onSaved={refreshAfterSave}
            setError={setError}
          />
        ) : null}
        {tab === "product-mix" ? (
          <ProductMixSection
            selectedProcessId={selectedProcessId}
            rows={productRows}
            lines={lines}
            onSaved={refreshAfterSave}
            setError={setError}
          />
        ) : null}
        {tab === "material-dependency" ? (
          <MaterialDependencySection
            selectedMaterialId={selectedMaterialId}
            selectedProcessId={selectedProcessId}
            rows={materialRows}
            lines={lines}
            materials={materials}
            onSaved={refreshAfterSave}
            setError={setError}
          />
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
      </CardContent>
    </Card>
  );
}

function ContextSelectors({
  plants,
  materials,
  lines,
  selectedPlantId,
  selectedMaterialId,
  selectedProcessId,
  setSelectedPlantId,
  setSelectedMaterialId,
  setSelectedProcessId,
  showMaterial,
  showProcess,
}: {
  plants: ContextOption[];
  materials: ContextOption[];
  lines: ProductionLine[];
  selectedPlantId: number;
  selectedMaterialId: number;
  selectedProcessId: number;
  setSelectedPlantId: (value: number) => void;
  setSelectedMaterialId: (value: number) => void;
  setSelectedProcessId: (value: number) => void;
  showMaterial: boolean;
  showProcess: boolean;
}) {
  return (
    <Section title="Configuration Context">
      <Field label="Plant" helper="Required plant context.">
        <select
          value={selectedPlantId}
          onChange={(event) => setSelectedPlantId(Number(event.target.value))}
          className={inputClass}
        >
          {plants.map((item) => (
            <option key={item.plant_id} value={item.plant_id}>
              {item.plant_name} ({item.plant_code})
            </option>
          ))}
        </select>
      </Field>
      {showMaterial ? (
        <Field label="Material" helper="Material affected by the process dependency.">
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
      ) : null}
      {showProcess ? (
        <Field label="Process / line" helper="Operational process used by impact calculation.">
          <select
            value={selectedProcessId}
            onChange={(event) =>
              setSelectedProcessId(Number(event.target.value))
            }
            className={inputClass}
          >
            {lines.length === 0 ? <option value={0}>No processes yet</option> : null}
            {lines.map((line) => (
              <option key={line.id} value={line.id}>
                {line.code} / {line.name}
              </option>
            ))}
          </select>
        </Field>
      ) : null}
    </Section>
  );
}

function ProcessesSection({
  selectedPlantId,
  lines,
  onSaved,
  setError,
}: {
  selectedPlantId: number;
  lines: ProductionLine[];
  onSaved: (message: string) => void;
  setError: (message: string) => void;
}) {
  const [editing, setEditing] = useState<ProductionLine | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [active, setActive] = useState(true);
  const [isPending, startTransition] = useTransition();

  function edit(line: ProductionLine) {
    setEditing(line);
    setCode(line.code);
    setName(line.name);
    setActive(line.is_active);
  }

  function reset() {
    setEditing(null);
    setCode("");
    setName("");
    setActive(true);
  }

  function save() {
    if (!selectedPlantId || !code.trim() || !name.trim()) {
      setError("Plant, process code, and process name are required.");
      return;
    }
    startTransition(async () => {
      const response = await fetch(
        editing
          ? `/api/impact/production-lines/${editing.id}`
          : "/api/impact/production-lines",
        {
          method: editing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            plant_id: selectedPlantId,
            code,
            name,
            is_active: active,
          }),
        },
      );
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      reset();
      onSaved(editing ? "Process updated." : "Process created.");
    });
  }

  return (
    <Section title="Processes / Lines">
      <Field label="Process / line code" helper="Example: BF-1, RM-2, CO-1.">
        <input value={code} onChange={(event) => setCode(event.target.value)} className={inputClass} />
      </Field>
      <Field label="Process / line name" helper="Example: Blast Furnace 1.">
        <input value={name} onChange={(event) => setName(event.target.value)} className={inputClass} />
      </Field>
      <label className="flex items-center gap-2 pt-7 text-sm">
        <input
          type="checkbox"
          checked={active}
          onChange={(event) => setActive(event.target.checked)}
          className="h-4 w-4"
        />
        Active process
      </label>
      <ActionRow
        pending={isPending}
        saveLabel={editing ? "Update process" : "Add process"}
        onSave={save}
        onCancel={editing ? reset : undefined}
      />
      <CompactTable empty="No operational processes or lines are configured for this plant yet. Add the first process/line to enable product mix and material dependency configuration.">
        {lines.map((line) => (
          <Row key={line.id}>
            <div>
              <p className="font-medium">
                {line.code} / {line.name}
              </p>
              <p className="text-xs text-mutedForeground">
                {line.is_active ? "Active" : "Inactive"}
              </p>
            </div>
            <button type="button" onClick={() => edit(line)} className={linkButtonClass}>
              Edit
            </button>
          </Row>
        ))}
      </CompactTable>
    </Section>
  );
}

function ProductMixSection({
  selectedProcessId,
  rows,
  lines,
  onSaved,
  setError,
}: {
  selectedProcessId: number;
  rows: ProcessProductDependency[];
  lines: ProductionLine[];
  onSaved: (message: string) => void;
  setError: (message: string) => void;
}) {
  const [editing, setEditing] = useState<ProcessProductDependency | null>(null);
  const [productName, setProductName] = useState("");
  const [outputSharePercent, setOutputSharePercent] = useState("");
  const [productValue, setProductValue] = useState("");
  const [criticality, setCriticality] = useState("1");
  const [active, setActive] = useState(true);
  const [isPending, startTransition] = useTransition();
  const criticalityChoice = selectedChoice(criticalityOptions, criticality);

  function edit(row: ProcessProductDependency) {
    setEditing(row);
    setProductName(row.product_name);
    setOutputSharePercent(String(Number(row.output_share_ratio) * 100));
    setProductValue(row.product_value_per_mt);
    setCriticality(row.operational_criticality_factor);
    setActive(row.is_active);
  }

  function reset() {
    setEditing(null);
    setProductName("");
    setOutputSharePercent("");
    setProductValue("");
    setCriticality("1");
    setActive(true);
  }

  function save() {
    const validation = validateProductMix(
      selectedProcessId,
      productName,
      outputSharePercent,
      productValue,
      criticality,
    );
    if (validation) {
      setError(validation);
      return;
    }
    startTransition(async () => {
      const response = await fetch(
        editing
          ? `/api/impact/process-product-dependencies/${editing.id}`
          : "/api/impact/process-product-dependencies",
        {
          method: editing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            process_id: selectedProcessId,
            product_name: productName,
            output_share_ratio: String(Number(outputSharePercent) / 100),
            product_value_per_mt: productValue,
            operational_criticality_factor: criticality,
            is_active: active,
          }),
        },
      );
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      reset();
      onSaved(editing ? "Product mix row updated." : "Product mix row added.");
    });
  }

  function deactivate(row: ProcessProductDependency) {
    startTransition(async () => {
      const response = await fetch(
        `/api/impact/process-product-dependencies/${row.id}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      onSaved("Product mix row deactivated.");
    });
  }

  const selectedLine = lines.find((line) => line.id === selectedProcessId);

  return (
    <Section title="Product Mix">
      {selectedLine ? (
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground md:col-span-2 xl:col-span-3">
          Product mix for {selectedLine.code} / {selectedLine.name}. This is an
          operational exposure estimate, not exact financial loss.
        </p>
      ) : null}
      <Field label="Product name" helper="Finished or intermediate output supported by this process.">
        <input value={productName} onChange={(event) => setProductName(event.target.value)} className={inputClass} />
      </Field>
      <Field
        label="Output share %"
        helper="Approximate share of this process output represented by this product. Total can be reviewed later; V1 does not need perfect accounting precision."
      >
        <input value={outputSharePercent} onChange={(event) => setOutputSharePercent(event.target.value)} className={inputClass} inputMode="decimal" placeholder="0-100" />
      </Field>
      <Field label="Product value per MT" helper="Estimated output value used for exposure weighting.">
        <input value={productValue} onChange={(event) => setProductValue(event.target.value)} className={inputClass} inputMode="decimal" placeholder="0" />
      </Field>
      <ChoiceGroup
        label="Operational criticality"
        value={criticalityChoice}
        options={criticalityOptions}
        onChange={(value) => setCriticality(value === "custom" ? "" : value)}
        helper="Higher values weight product exposure toward more operationally important output."
      />
      {criticalityChoice === "custom" ? (
        <Field label="Exact criticality factor" helper="Must be between 0.0 and 2.0.">
          <input value={criticality} onChange={(event) => setCriticality(event.target.value)} className={inputClass} inputMode="decimal" />
        </Field>
      ) : null}
      <label className="flex items-center gap-2 pt-7 text-sm">
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} className="h-4 w-4" />
        Active product mix row
      </label>
      <ActionRow
        pending={isPending}
        saveLabel={editing ? "Update product mix" : "Add product mix"}
        onSave={save}
        onCancel={editing ? reset : undefined}
      />
      <CompactTable empty="No product mix configured for this process yet.">
        {rows.map((row) => (
          <Row key={row.id}>
            <div>
              <p className="font-medium">{row.product_name}</p>
              <p className="text-xs text-mutedForeground">
                {formatPercent(row.output_share_ratio)} output share - INR{" "}
                {row.product_value_per_mt}/MT - criticality{" "}
                {row.operational_criticality_factor} -{" "}
                {row.is_active ? "Active" : "Inactive"}
              </p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => edit(row)} className={linkButtonClass}>
                Edit
              </button>
              {row.is_active ? (
                <button type="button" onClick={() => deactivate(row)} className={linkButtonClass}>
                  Deactivate
                </button>
              ) : null}
            </div>
          </Row>
        ))}
      </CompactTable>
    </Section>
  );
}

function MaterialDependencySection({
  selectedMaterialId,
  selectedProcessId,
  rows,
  lines,
  materials,
  onSaved,
  setError,
}: {
  selectedMaterialId: number;
  selectedProcessId: number;
  rows: MaterialProcessDependency[];
  lines: ProductionLine[];
  materials: ContextOption[];
  onSaved: (message: string) => void;
  setError: (message: string) => void;
}) {
  const [editing, setEditing] = useState<MaterialProcessDependency | null>(null);
  const [dependencyRatio, setDependencyRatio] = useState("0.5");
  const [substitutionFactor, setSubstitutionFactor] = useState<string | null>(null);
  const [survivabilityHours, setSurvivabilityHours] = useState<string | null>(null);
  const [active, setActive] = useState(true);
  const [isPending, startTransition] = useTransition();
  const dependencyChoice = selectedChoice(dependencyOptions, dependencyRatio);
  const substitutionChoice =
    substitutionFactor == null
      ? "fallback"
      : selectedChoice(substitutionOptions, substitutionFactor);
  const survivabilityChoice =
    survivabilityHours == null
      ? "fallback"
      : selectedChoice(survivabilityOptions, survivabilityHours);

  function edit(row: MaterialProcessDependency) {
    setEditing(row);
    setDependencyRatio(row.dependency_ratio);
    setSubstitutionFactor(row.substitution_factor);
    setSurvivabilityHours(row.survivability_hours);
    setActive(row.is_active);
  }

  function reset() {
    setEditing(null);
    setDependencyRatio("0.5");
    setSubstitutionFactor(null);
    setSurvivabilityHours(null);
    setActive(true);
  }

  function save() {
    const validation = validateMaterialDependency(
      selectedMaterialId,
      selectedProcessId,
      dependencyRatio,
      substitutionFactor,
      survivabilityHours,
    );
    if (validation) {
      setError(validation);
      return;
    }
    startTransition(async () => {
      const response = await fetch(
        editing
          ? `/api/impact/material-process-dependencies/${editing.id}`
          : "/api/impact/material-process-dependencies",
        {
          method: editing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            material_id: selectedMaterialId,
            process_id: selectedProcessId,
            dependency_ratio: dependencyRatio,
            substitution_factor: substitutionFactor,
            survivability_hours: survivabilityHours,
            is_active: active,
          }),
        },
      );
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      reset();
      onSaved(
        editing
          ? "Material dependency updated."
          : "Material dependency added.",
      );
    });
  }

  function deactivate(row: MaterialProcessDependency) {
    startTransition(async () => {
      const response = await fetch(
        `/api/impact/material-process-dependencies/${row.id}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        setError(await errorMessage(response));
        return;
      }
      onSaved("Material dependency deactivated.");
    });
  }

  return (
    <Section title="Material Dependency">
      <ChoiceGroup
        label="If this material becomes unavailable, how much does this process depend on it?"
        value={dependencyChoice}
        options={dependencyOptions}
        onChange={(value) => setDependencyRatio(value === "custom" ? "" : value)}
        helper="Dependency severity weights the process exposure used by interruption impact."
      />
      {dependencyChoice === "custom" ? (
        <Field label="Exact dependency ratio" helper="Must be between 0.0 and 1.0.">
          <input value={dependencyRatio} onChange={(event) => setDependencyRatio(event.target.value)} className={inputClass} inputMode="decimal" />
        </Field>
      ) : null}
      <ChoiceGroup
        label="Can this process operate with a substitute for this material?"
        value={substitutionChoice}
        options={substitutionOptions}
        onChange={(value) =>
          setSubstitutionFactor(value === "fallback" ? null : value)
        }
        helper="Use fallback to keep the existing interruption configuration substitution value."
      />
      <ChoiceGroup
        label="Does this process have its own survival time for this material?"
        value={survivabilityChoice}
        options={survivabilityOptions}
        onChange={(value) =>
          setSurvivabilityHours(value === "fallback" ? null : value === "custom" ? "" : value)
        }
        helper="Use fallback to keep the existing interruption configuration survivability value."
      />
      {survivabilityChoice === "custom" ? (
        <Field label="Exact survivability hours" helper="Must be greater than or equal to 0.">
          <input value={survivabilityHours ?? ""} onChange={(event) => setSurvivabilityHours(event.target.value)} className={inputClass} inputMode="decimal" />
        </Field>
      ) : null}
      <label className="flex items-center gap-2 pt-7 text-sm">
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} className="h-4 w-4" />
        Active material dependency
      </label>
      <ActionRow
        pending={isPending}
        saveLabel={editing ? "Update dependency" : "Add dependency"}
        onSave={save}
        onCancel={editing ? reset : undefined}
      />
      <CompactTable empty="No material-process dependencies configured for this plant yet.">
        {rows.map((row) => (
          <Row key={row.id}>
            <div>
              <p className="font-medium">
                {materialLabel(materials, row.material_id)} {"->"}{" "}
                {lineLabel(lines, row.process_id)}
              </p>
              <p className="text-xs text-mutedForeground">
                dependency {row.dependency_ratio} - substitution{" "}
                {row.substitution_factor ?? "fallback"} - survivability{" "}
                {row.survivability_hours ?? "fallback"} -{" "}
                {row.is_active ? "Active" : "Inactive"}
              </p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => edit(row)} className={linkButtonClass}>
                Edit
              </button>
              {row.is_active ? (
                <button type="button" onClick={() => deactivate(row)} className={linkButtonClass}>
                  Deactivate
                </button>
              ) : null}
            </div>
          </Row>
        ))}
      </CompactTable>
    </Section>
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

function TabButton({
  active,
  disabled = false,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
        active
          ? "bg-slate-950 text-white"
          : disabled
            ? "cursor-not-allowed bg-slate-100 text-slate-400"
            : "bg-slate-100 text-slate-700 hover:bg-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

function ActionRow({
  pending,
  saveLabel,
  onSave,
  onCancel,
}: {
  pending: boolean;
  saveLabel: string;
  onSave: () => void;
  onCancel?: () => void;
}) {
  return (
    <div className="flex items-end justify-end gap-2 md:col-span-2 xl:col-span-3">
      {onCancel ? (
        <button type="button" onClick={onCancel} className={secondaryButtonClass}>
          Cancel
        </button>
      ) : null}
      <button
        type="button"
        onClick={onSave}
        disabled={pending}
        className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
      >
        {pending ? "Saving..." : saveLabel}
      </button>
    </div>
  );
}

function CompactTable({
  empty,
  children,
}: {
  empty: string;
  children: ReactNode;
}) {
  return (
    <div className="md:col-span-2 xl:col-span-3">
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {Array.isArray(children) && children.length === 0 ? (
          <p className="px-3 py-3 text-sm text-mutedForeground">{empty}</p>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

function Row({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 px-3 py-3 text-sm">
      {children}
    </div>
  );
}

async function fetchLines(plantId: number) {
  return fetchRows<ProductionLine>(`/api/impact/production-lines?plant_id=${plantId}`);
}

async function fetchRows<T>(path: string): Promise<T[]> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as T[];
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

function validateProductMix(
  processId: number,
  productName: string,
  outputSharePercent: string,
  productValue: string,
  criticality: string,
) {
  if (!processId) return "Select a process before saving product mix.";
  if (!productName.trim()) return "Product name is required.";
  const share = Number(outputSharePercent);
  if (!Number.isFinite(share) || share < 0 || share > 100) {
    return "Output share must be between 0 and 100 percent.";
  }
  const value = Number(productValue);
  if (!Number.isFinite(value) || value < 0) {
    return "Product value per MT must be 0 or greater.";
  }
  const factor = Number(criticality);
  if (!Number.isFinite(factor) || factor < 0 || factor > 2) {
    return "Operational criticality factor must be between 0.0 and 2.0.";
  }
  return "";
}

function validateMaterialDependency(
  materialId: number,
  processId: number,
  dependencyRatio: string,
  substitutionFactor: string | null,
  survivabilityHours: string | null,
) {
  if (!materialId || !processId) return "Select material and process before saving.";
  const dependency = Number(dependencyRatio);
  if (!Number.isFinite(dependency) || dependency < 0 || dependency > 1) {
    return "Dependency ratio must be between 0.0 and 1.0.";
  }
  if (substitutionFactor != null) {
    const substitution = Number(substitutionFactor);
    if (!Number.isFinite(substitution) || substitution < 0 || substitution > 1) {
      return "Substitution factor must be between 0.0 and 1.0.";
    }
  }
  if (survivabilityHours != null) {
    const survivability = Number(survivabilityHours);
    if (!Number.isFinite(survivability) || survivability < 0) {
      return "Survivability hours must be 0 or greater.";
    }
  }
  return "";
}

function selectedChoice(
  options: Array<{ value: string }>,
  current: string | null,
) {
  if (current == null) return "fallback";
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

function formatPercent(value: string) {
  return `${Number(value) * 100}%`;
}

function lineLabel(lines: ProductionLine[], id: number) {
  const line = lines.find((item) => item.id === id);
  return line ? `${line.code} / ${line.name}` : "Selected process";
}

function materialLabel(materials: ContextOption[], id: number) {
  const material = materials.find((item) => item.material_id === id);
  return material
    ? `${material.material_name} (${material.material_code})`
    : "Selected material";
}

const inputClass =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";
const choiceClass =
  "flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm transition hover:bg-slate-50";
const linkButtonClass =
  "text-xs font-semibold text-slate-700 underline-offset-2 hover:underline";
const secondaryButtonClass =
  "rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50";
