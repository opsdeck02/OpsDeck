"use client";

import { useEffect, useState, useTransition } from "react";
import Link from "next/link";

import { MicrosoftFilePicker } from "@/app/dashboard/onboarding/components/MicrosoftFilePicker";
import type { MappingPreview, MicrosoftConnection, MicrosoftFile } from "@steelops/contracts";

const fileTypes = [
  { value: "shipment", label: "Shipment" },
  { value: "stock", label: "Stock" },
  { value: "threshold", label: "Threshold" },
];

const frequencies = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 60, label: "1 hr" },
  { value: 240, label: "4 hr" },
  { value: 1440, label: "24 hr" },
];

const fieldLabels: Record<string, string> = {
  shipment_id: "Shipment ID",
  plant_code: "Plant code/name",
  material_code: "Material code/name",
  material_name: "Material name",
  supplier_name: "Supplier / vendor",
  quantity_mt: "Quantity MT",
  planned_eta: "Planned ETA",
  current_eta: "Current ETA",
  delay_days: "Delay days",
  current_state: "Shipment status",
  latest_update_at: "Latest update time",
  on_hand_mt: "Current stock",
  quality_held_mt: "Blocked / quality-held stock",
  available_to_consume_mt: "Available unrestricted stock",
  daily_consumption_mt: "Daily consumption",
  snapshot_time: "Snapshot / last updated time",
  threshold_days: "Critical threshold days",
  warning_days: "Warning days",
};

export default function MicrosoftOnboardingPage() {
  const [connections, setConnections] = useState<MicrosoftConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [selectedFile, setSelectedFile] = useState<MicrosoftFile | null>(null);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [fileType, setFileType] = useState<"shipment" | "stock" | "threshold">("shipment");
  const [sheetName, setSheetName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [frequency, setFrequency] = useState(60);
  const [mappingPreview, setMappingPreview] = useState<MappingPreview | null>(null);
  const [mappingOverrides, setMappingOverrides] = useState<Record<string, string>>({});
  const [mappingError, setMappingError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    void loadConnections();
  }, []);

  async function loadConnections() {
    const response = await fetch("/api/microsoft/connections", { cache: "no-store" });
    if (!response.ok) return;
    const body = (await response.json()) as MicrosoftConnection[];
    setConnections(body);
    const active = body.find((item) => item.is_active);
    if (active) setSelectedConnectionId(active.id);
  }

  async function connectMicrosoft() {
    const response = await fetch("/api/microsoft/auth-url");
    const body = (await response.json()) as { auth_url?: string; detail?: string };
    if (!response.ok || !body.auth_url) {
      setMessage(body.detail ?? "Microsoft authorization could not be started.");
      return;
    }
    window.location.href = body.auth_url;
  }

  async function onFileSelect(file: MicrosoftFile, siteId?: string | null) {
    setSelectedFile(file);
    setSelectedSiteId(siteId ?? null);
    setDisplayName(file.name);
    setSheetNames([]);
    setSheetName("");
    setMappingPreview(null);
    setMappingOverrides({});
    setMappingError(null);
    let firstSheet = "";
    if (file.name.toLowerCase().endsWith(".xlsx")) {
      const params = new URLSearchParams({ drive_id: file.drive_id, item_id: file.item_id });
      if (siteId) params.set("site_id", siteId);
      const response = await fetch(
        `/api/microsoft/connections/${selectedConnectionId}/files/sheet-names?${params.toString()}`,
      );
      if (response.ok) {
        const body = (await response.json()) as { sheet_names: string[] };
        setSheetNames(body.sheet_names);
        firstSheet = body.sheet_names[0] ?? "";
        setSheetName(firstSheet);
      }
    }
    await loadMappingPreview(file, siteId ?? null, fileType, firstSheet);
  }

  async function loadMappingPreview(
    file = selectedFile,
    siteId = selectedSiteId,
    nextFileType = fileType,
    nextSheetName = sheetName,
  ) {
    if (!selectedConnectionId || !file) return;
    setMappingError(null);
    const params = new URLSearchParams({
      drive_id: file.drive_id,
      item_id: file.item_id,
      file_type: nextFileType,
    });
    if (siteId) params.set("site_id", siteId);
    if (nextSheetName) params.set("sheet_name", nextSheetName);
    const response = await fetch(
      `/api/microsoft/connections/${selectedConnectionId}/files/mapping-preview?${params.toString()}`,
    );
    const body = await response.json();
    if (!response.ok) {
      setMappingPreview(null);
      setMappingOverrides({});
      setMappingError(typeof body.detail === "string" ? body.detail : "Mapping preview failed.");
      return;
    }
    const preview = body as MappingPreview;
    setMappingPreview(preview);
    setMappingOverrides(
      Object.fromEntries(
        preview.suggestions
          .filter((item) => item.suggested_field)
          .map((item) => [item.source_header, item.suggested_field as string]),
      ),
    );
  }

  function createDataSource() {
    if (!selectedConnectionId || !selectedFile) {
      setMessage("Connect Microsoft and select a file first.");
      return;
    }
    setMessage(null);
    startTransition(async () => {
      const response = await fetch("/api/microsoft/data-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          connection_id: selectedConnectionId,
          drive_id: selectedFile.drive_id,
          item_id: selectedFile.item_id,
          site_id: selectedSiteId,
          file_type: fileType,
          sheet_name: sheetName || null,
          column_mapping: Object.keys(mappingOverrides).length > 0 ? mappingOverrides : null,
          sync_frequency_minutes: frequency,
          display_name: displayName || selectedFile.name,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Microsoft source could not be synced.");
        return;
      }
      setMessage("Microsoft source connected and synced.");
    });
  }

  const selectedConnection = connections.find((item) => item.id === selectedConnectionId);

  return (
    <div className="grid gap-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-[0.18em] text-mutedForeground">Data source</p>
          <h1 className="text-2xl font-semibold">Microsoft 365 auto-sync</h1>
        </div>
        <Link className="rounded-md border px-3 py-2 text-sm" href="/dashboard/onboarding">Back</Link>
      </div>

      <section className="rounded-md border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">1. Connect account</h2>
            <p className="mt-1 text-sm text-mutedForeground">Connect OneDrive or SharePoint with delegated Microsoft Graph access.</p>
          </div>
          <button type="button" onClick={connectMicrosoft} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground">
            Connect Microsoft 365
          </button>
        </div>
        {connections.length > 0 ? (
          <select className="mt-4 w-full rounded-md border bg-background px-3 py-2 text-sm" value={selectedConnectionId} onChange={(event) => setSelectedConnectionId(event.target.value)}>
            {connections.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.display_name} · {connection.email} {connection.is_active ? "" : "(inactive)"}
              </option>
            ))}
          </select>
        ) : null}
      </section>

      {selectedConnection ? (
        <section className="rounded-md border bg-card p-5">
          <h2 className="font-semibold">2. Pick a file</h2>
          <p className="mb-4 mt-1 text-sm text-mutedForeground">{selectedConnection.display_name} · {selectedConnection.email}</p>
          <MicrosoftFilePicker connectionId={selectedConnection.id} onSelect={onFileSelect} />
        </section>
      ) : null}

      {selectedFile ? (
        <section className="rounded-md border bg-card p-5">
          <h2 className="font-semibold">3. Configure sync</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <input className="rounded-md border bg-background px-3 py-2 text-sm" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Display name" />
            <select
              className="rounded-md border bg-background px-3 py-2 text-sm"
              value={fileType}
              onChange={(event) => {
                const nextFileType = event.target.value as typeof fileType;
                setFileType(nextFileType);
                void loadMappingPreview(selectedFile, selectedSiteId, nextFileType, sheetName);
              }}
            >
              {fileTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <select
              className="rounded-md border bg-background px-3 py-2 text-sm"
              value={sheetName}
              onChange={(event) => {
                setSheetName(event.target.value);
                void loadMappingPreview(selectedFile, selectedSiteId, fileType, event.target.value);
              }}
              disabled={sheetNames.length === 0}
            >
              <option value="">Default sheet</option>
              {sheetNames.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
            <select className="rounded-md border bg-background px-3 py-2 text-sm" value={frequency} onChange={(event) => setFrequency(Number(event.target.value))}>
              {frequencies.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </div>
          <div className="mt-4 rounded-md border bg-background p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-semibold">Manual column mapping</p>
                <p className="mt-1 text-sm text-mutedForeground">
                  Review detected headers and override any column before scheduled sync.
                </p>
              </div>
              <button type="button" onClick={() => void loadMappingPreview()} className="rounded-md border px-3 py-2 text-sm">
                Refresh preview
              </button>
            </div>
            {mappingError ? <p className="mt-3 text-sm text-danger">{mappingError}</p> : null}
            {mappingPreview ? (
              <div className="mt-4 space-y-3">
                <div className="rounded-md bg-muted px-3 py-2 text-sm">
                  <p className="font-medium">Required OpsDeck fields</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {mappingPreview.required_fields.map((field) => (
                      <span key={field} className="rounded-full border bg-card px-3 py-1 text-xs">
                        {fieldLabels[field] ?? field}
                      </span>
                    ))}
                  </div>
                </div>
                {mappingPreview.suggestions.map((item) => (
                  <div key={item.source_header} className="grid gap-2 rounded-md border bg-card p-3 md:grid-cols-[1fr_1fr_auto]">
                    <div>
                      <p className="text-xs text-mutedForeground">Incoming column</p>
                      <p className="font-medium">{item.source_header}</p>
                    </div>
                    <div>
                      <p className="text-xs text-mutedForeground">Mapped to</p>
                      <select
                        value={mappingOverrides[item.source_header] ?? ""}
                        onChange={(event) =>
                          setMappingOverrides((current) => ({
                            ...current,
                            [item.source_header]: event.target.value,
                          }))
                        }
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                      >
                        <option value="">Ignore column</option>
                        {mappingPreview.required_fields.map((value) => (
                          <option key={value} value={value}>
                            Required: {fieldLabels[value] ?? value}
                          </option>
                        ))}
                        {mappingPreview.optional_fields.map((value) => (
                          <option key={value} value={value}>
                            Optional: {fieldLabels[value] ?? value}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="self-end rounded-full bg-muted px-3 py-1 text-xs">
                      {item.confidence}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-mutedForeground">Select a file to preview mapping.</p>
            )}
          </div>
          <button type="button" onClick={createDataSource} disabled={isPending} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground disabled:opacity-60">
            {isPending ? "Syncing..." : "Connect & Sync Now"}
          </button>
          {message ? <p className="mt-3 text-sm text-mutedForeground">{message}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
