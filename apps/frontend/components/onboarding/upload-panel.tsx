"use client";

import { useEffect, useState, useTransition } from "react";

import type {
  ExternalDataSource,
  ExternalDataSourceSyncResult,
  MappingPreview,
  IngestionJob,
  UploadResult,
} from "@steelops/contracts";

const fileTypes = [
  { value: "shipment", label: "Shipment file" },
  { value: "stock", label: "Stock snapshot file" },
  { value: "threshold", label: "Plant-material threshold file" },
];

const fieldLabels: Record<string, string> = {
  shipment_id: "Shipment ID",
  plant_code: "Plant code/name",
  material_code: "Material code/name",
  supplier_name: "Supplier / vendor",
  quantity_mt: "Quantity MT",
  planned_eta: "Planned ETA",
  current_eta: "Current ETA",
  delay_days: "Delay days",
  current_state: "Shipment status",
  source_of_truth: "Source of truth (system-filled)",
  latest_update_at: "Latest update time",
  vessel_name: "Vessel name",
  imo_number: "IMO number",
  mmsi: "MMSI",
  origin_port: "Origin port",
  destination_port: "Destination port",
  eta_confidence: "ETA confidence",
  on_hand_mt: "On-hand MT",
  quality_held_mt: "Quality-held MT",
  available_to_consume_mt: "Available to consume MT",
  daily_consumption_mt: "Daily consumption MT",
  snapshot_time: "Snapshot time",
  threshold_days: "Critical threshold days",
  warning_days: "Warning days",
};

export function UploadPanel({
  automatedSourcesEnabled = true,
}: {
  automatedSourcesEnabled?: boolean;
}) {
  const [fileType, setFileType] = useState("shipment");
  const [uploadMode, setUploadMode] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState<"google_sheets" | "excel_online">("excel_online");
  const [sourceUrl, setSourceUrl] = useState("");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [history, setHistory] = useState<IngestionJob[]>([]);
  const [mappingPreview, setMappingPreview] = useState<MappingPreview | null>(null);
  const [mappingOverrides, setMappingOverrides] = useState<Record<string, string>>({});
  const [dataSources, setDataSources] = useState<ExternalDataSource[]>([]);
  const [editingSourceId, setEditingSourceId] = useState<number | null>(null);
  const [dataSourceForm, setDataSourceForm] = useState({
    source_type: "google_sheets" as "google_sheets" | "excel_online",
    source_name: "",
    source_url: "",
    dataset_type: "shipments" as "shipments" | "stock" | "thresholds",
    mapping_config_text: "",
    sync_frequency_minutes: "60",
    is_active: true,
  });
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const uploadUrlDetection = describeUrl(sourceUrl);
  const dataSourceUrlDetection = describeUrl(dataSourceForm.source_url);

  useEffect(() => {
    void loadHistory();
    if (automatedSourcesEnabled) {
      void loadDataSources();
    } else {
      setDataSources([]);
    }
  }, [automatedSourcesEnabled]);

  useEffect(() => {
    if (!automatedSourcesEnabled && uploadMode === "url") {
      setUploadMode("file");
      setMappingPreview(null);
      setMappingOverrides({});
    }
  }, [automatedSourcesEnabled, uploadMode]);

  useEffect(() => {
    if (uploadMode === "file" && file) {
      void previewMapping(fileType, file);
    }
    if (automatedSourcesEnabled && uploadMode === "url" && sourceUrl.trim()) {
      void previewUrlMapping();
    }
  }, [automatedSourcesEnabled, fileType, uploadMode]);

  async function loadHistory() {
    const response = await fetch("/api/ingestion/history", { cache: "no-store" });
    if (response.ok) {
      setHistoryError(null);
      setHistory((await response.json()) as IngestionJob[]);
      return;
    }
    setHistoryError("Ingestion history could not be loaded.");
  }

  async function loadDataSources() {
    if (!automatedSourcesEnabled) {
      setDataSources([]);
      return;
    }
    const response = await fetch("/api/tenant-data-sources", { cache: "no-store" });
    if (!response.ok) {
      setDataSources([]);
      return;
    }
    setDataSources((await response.json()) as ExternalDataSource[]);
  }

  async function previewMapping(selectedFileType: string, selectedFile: File) {
    const formData = new FormData();
    formData.append("file_type", selectedFileType);
    formData.append("file", selectedFile);
    const response = await fetch("/api/ingestion/mapping-preview", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      setMappingPreview(null);
      setMappingOverrides({});
      return;
    }
    const body = (await response.json()) as MappingPreview;
    setMappingPreview(body);
    setMappingOverrides(
      Object.fromEntries(
        body.suggestions
          .filter((item) => item.suggested_field)
          .map((item) => [item.source_header, item.suggested_field as string]),
      ),
    );
  }

  async function previewUrlMapping() {
    if (!sourceUrl.trim()) {
      setError("Paste a Google Sheets or Excel/OneDrive URL first.");
      return;
    }
    setError(null);
    const formData = new FormData();
    formData.append("file_type", fileType);
    formData.append("source_type", sourceType);
    formData.append("source_url", sourceUrl.trim());
    const response = await fetch("/api/ingestion/url-mapping-preview", {
      method: "POST",
      body: formData,
    });
    const body = await response.json();
    if (!response.ok) {
      setMappingPreview(null);
      setMappingOverrides({});
      setError(typeof body.detail === "string" ? body.detail : "URL mapping preview failed.");
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

  function clearUploadedData() {
    const confirmed = window.confirm(
      "Delete uploaded data for this tenant? This clears shipments, stock snapshots, thresholds, ingestion history, and related exceptions.",
    );
    if (!confirmed) {
      return;
    }

    setError(null);
    setResult(null);
    startTransition(async () => {
      const response = await fetch("/api/ingestion/upload/clear", {
        method: "DELETE",
      });
      const body = (await response.json()) as { detail?: string } & Record<string, number>;
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Uploaded data could not be deleted.");
        return;
      }
      setFile(null);
      setHistory([]);
      setResult(null);
      setError(
        `Deleted ${body.shipments ?? 0} shipments, ${body.stock_snapshots ?? 0} stock snapshots, ${body.thresholds ?? 0} thresholds, and ${body.ingestion_jobs ?? 0} ingestion jobs.`,
      );
      await loadHistory();
    });
  }

  function uploadFile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (uploadMode === "url" && automatedSourcesEnabled) {
      uploadUrl();
      return;
    }
    if (!file) {
      setError("Choose a CSV or XLSX file first.");
      return;
    }

    setError(null);
    setResult(null);
    startTransition(async () => {
      const formData = new FormData();
      formData.append("file_type", fileType);
      formData.append("file", file);
      formData.append("mapping_overrides", JSON.stringify(mappingOverrides));

      const response = await fetch("/api/ingestion/upload", {
        method: "POST",
        body: formData,
      });
      const body = await response.json();

      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Upload failed validation.");
        if (body.detail?.validation_errors) {
          setResult(body.detail as UploadResult);
        }
      } else {
        setResult(body as UploadResult);
      }
      await loadHistory();
    });
  }

  function uploadUrl() {
    if (!automatedSourcesEnabled) {
      setError("URL ingestion is included in paid and enterprise plans.");
      return;
    }
    if (!sourceUrl.trim()) {
      setError("Paste a Google Sheets or Excel/OneDrive URL first.");
      return;
    }

    setError(null);
    setResult(null);
    startTransition(async () => {
      const formData = new FormData();
      formData.append("file_type", fileType);
      formData.append("source_type", sourceType);
      formData.append("source_url", sourceUrl.trim());
      formData.append("mapping_overrides", JSON.stringify(mappingOverrides));

      const response = await fetch("/api/ingestion/url-upload", {
        method: "POST",
        body: formData,
      });
      const body = await response.json();

      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "URL upload failed validation.");
        if (body.detail?.validation_errors) {
          setResult(body.detail as UploadResult);
        }
      } else {
        setResult(body as UploadResult);
      }
      await loadHistory();
    });
  }

  function onFileSelected(nextFile: File | null) {
    setFile(nextFile);
    if (!nextFile) {
      setMappingPreview(null);
      setMappingOverrides({});
      return;
    }
    void previewMapping(fileType, nextFile);
  }

  function resetDataSourceForm() {
    setEditingSourceId(null);
    setDataSourceForm({
      source_type: "google_sheets",
      source_name: "",
      source_url: "",
      dataset_type: "shipments",
      mapping_config_text: "",
      sync_frequency_minutes: "60",
      is_active: true,
    });
  }

  function populateDataSourceForm(source: ExternalDataSource) {
    setEditingSourceId(source.id);
    setDataSourceForm({
      source_type: source.source_type,
      source_name: source.source_name,
      source_url: source.source_url,
      dataset_type: source.dataset_type,
      mapping_config_text: JSON.stringify(source.mapping_config, null, 2),
      sync_frequency_minutes: String(source.sync_frequency_minutes),
      is_active: source.is_active,
    });
  }

  function saveDataSource() {
    if (!automatedSourcesEnabled) {
      setError("Automated URL sources are included in paid and enterprise plans.");
      return;
    }
    let mappingConfig: Record<string, unknown> = {};
    if (dataSourceForm.mapping_config_text.trim()) {
      try {
        mappingConfig = JSON.parse(dataSourceForm.mapping_config_text) as Record<string, unknown>;
      } catch {
        setError("URL source mapping JSON is invalid.");
        return;
      }
    }

    setError(null);
    startTransition(async () => {
      const response = await fetch(
        editingSourceId ? `/api/tenant-data-sources/${editingSourceId}` : "/api/tenant-data-sources",
        {
          method: editingSourceId ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_type: dataSourceForm.source_type,
            source_name: dataSourceForm.source_name,
            source_url: dataSourceForm.source_url,
            dataset_type: dataSourceForm.dataset_type,
            mapping_config: mappingConfig,
            sync_frequency_minutes: Number(dataSourceForm.sync_frequency_minutes),
            is_active: dataSourceForm.is_active,
          }),
        },
      );
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "URL source save failed.");
        return;
      }
      resetDataSourceForm();
      await loadDataSources();
    });
  }

  function runSyncNow(sourceId: number) {
    if (!automatedSourcesEnabled) {
      setError("Automated URL sync is included in paid and enterprise plans.");
      return;
    }
    setError(null);
    startTransition(async () => {
      const response = await fetch(`/api/tenant-data-sources/${sourceId}`, { method: "POST" });
      const body = (await response.json()) as ExternalDataSourceSyncResult & { detail?: string };
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "URL sync failed.");
        return;
      }
      setError(
        `Sync ${body.sync_status}. Rows ${body.rows_received}, accepted ${body.rows_accepted}, rejected ${body.rows_rejected}.`,
      );
      await loadDataSources();
      await loadHistory();
    });
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_0.9fr]">
      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <div className="space-y-2">
          <h2 className="text-xl font-semibold">Upload onboarding data</h2>
          <p className="text-sm text-mutedForeground">
            Upload CSV or XLSX files for shipments, stock snapshots, or thresholds.
          </p>
        </div>
        <form onSubmit={uploadFile} className="mt-6 space-y-4">
          <label className="block space-y-2 text-sm font-medium">
            <span>File type</span>
            <select
              value={fileType}
              onChange={(event) => setFileType(event.target.value)}
              className="w-full rounded-2xl border bg-card px-4 py-3"
            >
              {fileTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </label>
          {uploadMode === "file" ? (
            <label className="block space-y-2 text-sm font-medium">
              <span>File</span>
              <input
                type="file"
                accept=".csv,.xlsx"
                onChange={(event) => onFileSelected(event.target.files?.[0] ?? null)}
                className="w-full rounded-2xl border bg-card px-4 py-3"
              />
            </label>
          ) : null}
          {automatedSourcesEnabled ? (
            <div className="rounded-2xl border bg-muted/40 p-4">
              <p className="font-medium">Upload mode</p>
              <p className="mt-1 text-sm text-mutedForeground">
                Choose one path: manual file upload or direct URL upload.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setUploadMode("file");
                    setMappingPreview(null);
                    setMappingOverrides({});
                  }}
                  className={`rounded-2xl border px-4 py-2 text-xs font-semibold ${uploadMode === "file" ? "bg-primary text-primaryForeground" : ""}`}
                >
                  Manual file
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setUploadMode("url");
                    setMappingPreview(null);
                    setMappingOverrides({});
                  }}
                  className={`rounded-2xl border px-4 py-2 text-xs font-semibold ${uploadMode === "url" ? "bg-primary text-primaryForeground" : ""}`}
                >
                  URL upload
                </button>
              </div>
              {uploadMode === "url" ? (
                <div className="mt-3 grid gap-3">
                  <select
                    value={sourceType}
                    onChange={(event) => setSourceType(event.target.value as "google_sheets" | "excel_online")}
                    className="rounded-2xl border bg-card px-4 py-3 text-sm"
                  >
                    <option value="excel_online">Excel / OneDrive direct link</option>
                    <option value="google_sheets">Google Sheets public link</option>
                  </select>
                  <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                    <input
                      value={sourceUrl}
                      onChange={(event) => setSourceUrl(event.target.value)}
                      placeholder="Paste OneDrive, Google Drive, SharePoint, CSV, or XLSX URL"
                      className="rounded-2xl border bg-card px-4 py-3 text-sm"
                    />
                    <button
                      type="button"
                      onClick={previewUrlMapping}
                      disabled={isPending}
                      className="rounded-2xl border px-4 py-3 text-sm font-medium disabled:opacity-60"
                    >
                      Preview mapping
                    </button>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-mutedForeground">
                    <span className="rounded-full border bg-card px-3 py-1 font-medium text-primary">
                      {uploadUrlDetection.label}
                    </span>
                    <span>
                      Paste any OneDrive, Google Drive, or SharePoint share link. Ensure &apos;Anyone with the link can view&apos; is enabled.
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-2xl border bg-muted/40 p-4">
              <p className="font-medium">Manual onboarding</p>
              <p className="mt-1 text-sm text-mutedForeground">
                Pilot tenants can upload CSV or XLSX files manually. URL ingestion and Microsoft 365 auto-sync are included in paid and enterprise plans.
              </p>
            </div>
          )}
          <div className="rounded-2xl border p-4">
            <p className="font-medium">Column mapping review</p>
            <p className="mt-1 text-sm text-mutedForeground">
              OpsDeck now suggests forgiving matches for different Indian column names. You can override any mapping before upload.
            </p>
            <div className="mt-3 space-y-3">
              <div className="rounded-2xl bg-muted/50 p-3 text-sm">
                <p className="font-medium">Required OpsDeck columns for this upload</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(mappingPreview?.required_fields ?? []).map((field) => (
                    <span key={field} className="rounded-full bg-card px-3 py-1 text-xs">
                      {fieldLabels[field] ?? field}
                    </span>
                  ))}
                  {!mappingPreview ? (
                    <span className="text-mutedForeground">Choose a file to see required columns.</span>
                  ) : null}
                </div>
                {mappingPreview?.file_type === "shipment" ? (
                  <p className="mt-2 text-xs text-mutedForeground">
                    Source of truth is saved automatically as manual_upload for file uploads and as the URL source type for automated sync.
                  </p>
                ) : null}
              </div>
              {mappingPreview ? (
                <div className="rounded-2xl bg-muted/50 p-3 text-sm">
                  <p className="font-medium">Columns found in your upload</p>
                  <p className="mt-1 break-words text-mutedForeground">{mappingPreview.headers.join(", ")}</p>
                </div>
              ) : null}
              {!mappingPreview || mappingPreview.suggestions.length === 0 ? (
                <p className="text-sm text-mutedForeground">Choose a file to preview header mapping.</p>
              ) : (
                mappingPreview.suggestions.map((item) => (
                  <div key={item.source_header} className="grid gap-2 rounded-2xl border bg-card p-3 md:grid-cols-[1fr_1fr_auto]">
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
                        className="w-full rounded-2xl border bg-card px-4 py-2 text-sm"
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
                ))
              )}
            </div>
          </div>
          {automatedSourcesEnabled ? (
            <div className="rounded-2xl border p-4">
              <p className="font-medium">URL source for automated ingestion</p>
              <p className="mt-1 text-sm text-mutedForeground">
                Save a Google Sheets or Excel Online URL here if you want the same dataset to sync without manual file uploads.
              </p>
              <div className="mt-3 grid gap-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <select
                    value={dataSourceForm.source_type}
                    onChange={(event) =>
                      setDataSourceForm((current) => ({
                        ...current,
                        source_type: event.target.value as "google_sheets" | "excel_online",
                      }))
                    }
                    className="rounded-2xl border bg-card px-4 py-3 text-sm"
                  >
                    <option value="google_sheets">Google Sheets</option>
                    <option value="excel_online">Excel Online</option>
                  </select>
                  <select
                    value={dataSourceForm.dataset_type}
                    onChange={(event) =>
                      setDataSourceForm((current) => ({
                        ...current,
                        dataset_type: event.target.value as "shipments" | "stock" | "thresholds",
                      }))
                    }
                    className="rounded-2xl border bg-card px-4 py-3 text-sm"
                  >
                    <option value="shipments">Shipments</option>
                    <option value="stock">Stock</option>
                    <option value="thresholds">Thresholds</option>
                  </select>
                </div>
                <input
                  value={dataSourceForm.source_name}
                  onChange={(event) => setDataSourceForm((current) => ({ ...current, source_name: event.target.value }))}
                  placeholder="Source name"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <input
                  value={dataSourceForm.source_url}
                  onChange={(event) => setDataSourceForm((current) => ({ ...current, source_url: event.target.value }))}
                  placeholder="OneDrive, Google Drive, SharePoint, CSV, or XLSX URL"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <div className="flex flex-wrap items-center gap-2 text-xs text-mutedForeground">
                  <span className="rounded-full border bg-card px-3 py-1 font-medium text-primary">
                    {dataSourceUrlDetection.label}
                  </span>
                  <span>
                    Paste any OneDrive, Google Drive, or SharePoint share link. Ensure &apos;Anyone with the link can view&apos; is enabled.
                  </span>
                </div>
                <textarea
                  value={dataSourceForm.mapping_config_text}
                  onChange={(event) =>
                    setDataSourceForm((current) => ({ ...current, mapping_config_text: event.target.value }))
                  }
                  placeholder={'Optional source config JSON\n{"sheet_gid":"0"}'}
                  className="min-h-24 rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                  <input
                    value={dataSourceForm.sync_frequency_minutes}
                    onChange={(event) =>
                      setDataSourceForm((current) => ({ ...current, sync_frequency_minutes: event.target.value }))
                    }
                    className="rounded-2xl border bg-card px-4 py-3 text-sm"
                    placeholder="Sync frequency minutes"
                  />
                  <button
                    type="button"
                    onClick={saveDataSource}
                    disabled={isPending}
                    className="rounded-2xl border px-4 py-3 text-sm font-medium disabled:opacity-60"
                  >
                    {editingSourceId ? "Update URL source" : "Save URL source"}
                  </button>
                </div>
              </div>
              <div className="mt-3 space-y-3">
                {dataSources.map((source) => (
                  <div key={source.id} className="rounded-2xl border bg-card p-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-medium">{source.source_name}</p>
                        <p className="text-mutedForeground">{source.source_type} for {source.dataset_type}</p>
                      </div>
                      <span className="rounded-full bg-muted px-3 py-1 text-xs">{source.last_sync_status ?? "not_started"}</span>
                    </div>
                    <p className="mt-2 break-all text-mutedForeground">{source.source_url}</p>
                    <div className="mt-3 flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() => runSyncNow(source.id)}
                        className="rounded-2xl bg-primary px-4 py-2 text-xs font-semibold text-primaryForeground"
                      >
                        Run sync now
                      </button>
                      <button
                        type="button"
                        onClick={() => populateDataSourceForm(source)}
                        className="rounded-2xl border px-4 py-2 text-xs font-semibold"
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                ))}
                {dataSources.length === 0 ? (
                  <p className="text-sm text-mutedForeground">No URL sources saved yet.</p>
                ) : null}
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={isPending}
              className="rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
            >
              {isPending ? "Uploading..." : automatedSourcesEnabled && uploadMode === "url" ? "Upload URL" : "Upload file"}
            </button>
            {fileTypes.map((type) => (
              <a
                key={type.value}
                href={`/api/ingestion/templates/${type.value}`}
                className="rounded-2xl border px-4 py-3 text-sm font-medium"
              >
                {type.value} template
              </a>
            ))}
            <button
              type="button"
              onClick={clearUploadedData}
              disabled={isPending}
              className="rounded-2xl border border-accent px-4 py-3 text-sm font-medium text-primary disabled:opacity-60"
            >
              Delete uploaded data
            </button>
          </div>
        </form>
        {error ? <p className="mt-4 rounded-2xl bg-muted p-4 text-sm text-primary">{error}</p> : null}
        {result ? (
          <div className="mt-5 rounded-2xl bg-muted p-4 text-sm">
            <p className="font-semibold">Upload summary</p>
            <p>Rows received: {result.rows_received}</p>
            <p>Accepted: {result.rows_accepted}</p>
            <p>Rejected: {result.rows_rejected}</p>
            <p>
              Created {result.summary_counts.created}, updated {result.summary_counts.updated},
              unchanged {result.summary_counts.unchanged}
            </p>
            {result.validation_errors.length > 0 ? (
              <div className="mt-3 space-y-2">
                {result.validation_errors.slice(0, 5).map((rowError) => (
                  <p key={rowError.row_number}>
                    Row {rowError.row_number}: {rowError.errors.join("; ")}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <h2 className="text-xl font-semibold">Ingestion history</h2>
        <div className="mt-4 space-y-3">
          {historyError ? (
            <p className="rounded-2xl bg-muted p-4 text-sm text-primary">{historyError}</p>
          ) : null}
          {history.map((job) => (
            <div key={job.id} className="rounded-2xl border bg-card p-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{job.file_type}</span>
                <span className="rounded-full bg-muted px-3 py-1 text-xs">{job.status}</span>
              </div>
              <p className="mt-2 text-mutedForeground">
                {job.rows_accepted}/{job.rows_received} accepted, {job.rows_rejected} rejected
              </p>
            </div>
          ))}
          {history.length === 0 ? (
            <p className="text-sm text-mutedForeground">No ingestion jobs yet.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function describeUrl(url: string): { platform: string; label: string } {
  const value = url.trim().toLowerCase();
  if (!value) {
    return { platform: "empty", label: "Paste a URL" };
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return { platform: "unknown", label: "Unknown - may not work" };
  }
  const host = parsed.hostname;
  const path = parsed.pathname;
  if (host.includes("docs.google.com") && path.includes("/spreadsheets/")) {
    return { platform: "google_sheets", label: "Google Sheets detected ✓" };
  }
  if (host.includes("drive.google.com") || host.includes("docs.google.com")) {
    return { platform: "google_drive", label: "Google Drive detected ✓" };
  }
  if (host.includes("sharepoint.com")) {
    return { platform: "sharepoint", label: "SharePoint detected ✓" };
  }
  if (host.includes("onedrive.live.com") || host.includes("1drv.ms") || host.includes("onedrive.com")) {
    return { platform: "onedrive", label: "OneDrive detected ✓" };
  }
  if (
    path.endsWith(".xlsx") ||
    path.endsWith(".xls") ||
    path.endsWith(".csv") ||
    parsed.searchParams.get("download") === "1" ||
    parsed.searchParams.get("export") === "download"
  ) {
    return { platform: "direct", label: "Direct URL (no transformation needed)" };
  }
  return { platform: "unknown", label: "Unknown - may not work" };
}
