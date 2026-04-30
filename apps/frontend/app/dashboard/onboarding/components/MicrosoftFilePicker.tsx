"use client";

import { useCallback, useEffect, useState, useTransition } from "react";

import type { MicrosoftDrive, MicrosoftFile, MicrosoftSharePointSite } from "@steelops/contracts";

type Mode = "personal" | "sharepoint";

export function MicrosoftFilePicker({
  connectionId,
  onSelect,
}: {
  connectionId: string;
  onSelect: (file: MicrosoftFile, siteId?: string | null) => void;
}) {
  const [mode, setMode] = useState<Mode>("personal");
  const [search, setSearch] = useState("");
  const [files, setFiles] = useState<MicrosoftFile[]>([]);
  const [sites, setSites] = useState<MicrosoftSharePointSite[]>([]);
  const [drives, setDrives] = useState<MicrosoftDrive[]>([]);
  const [siteId, setSiteId] = useState("");
  const [driveId, setDriveId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const loadPersonalFiles = useCallback(async (nextSearch = search) => {
    setError(null);
    const suffix = nextSearch.trim() ? `?search=${encodeURIComponent(nextSearch.trim())}` : "";
    const response = await fetch(`/api/microsoft/connections/${connectionId}/files${suffix}`);
    if (!response.ok) {
      setError("Microsoft files could not be loaded.");
      return;
    }
    setFiles((await response.json()) as MicrosoftFile[]);
  }, [connectionId, search]);

  const loadSites = useCallback(async () => {
    const response = await fetch(`/api/microsoft/connections/${connectionId}/sharepoint-sites`);
    if (!response.ok) return;
    setSites((await response.json()) as MicrosoftSharePointSite[]);
  }, [connectionId]);

  useEffect(() => {
    if (mode === "personal") {
      void loadPersonalFiles();
    } else {
      void loadSites();
    }
  }, [mode, connectionId, loadPersonalFiles, loadSites]);

  async function loadDrives(nextSiteId: string) {
    setSiteId(nextSiteId);
    setDriveId("");
    setFiles([]);
    const response = await fetch(
      `/api/microsoft/connections/${connectionId}/sharepoint-sites/${encodeURIComponent(nextSiteId)}/drives`,
    );
    if (!response.ok) return;
    setDrives((await response.json()) as MicrosoftDrive[]);
  }

  async function loadDriveFiles(nextDriveId: string) {
    setDriveId(nextDriveId);
    const response = await fetch(
      `/api/microsoft/connections/${connectionId}/drives/${encodeURIComponent(nextDriveId)}/files?site_id=${encodeURIComponent(siteId)}`,
    );
    if (!response.ok) {
      setError("SharePoint files could not be loaded.");
      return;
    }
    setFiles((await response.json()) as MicrosoftFile[]);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={`rounded-md border px-3 py-2 text-sm ${mode === "personal" ? "border-primary bg-primary text-primaryForeground" : "bg-card"}`}
          onClick={() => setMode("personal")}
        >
          Personal OneDrive
        </button>
        <button
          type="button"
          className={`rounded-md border px-3 py-2 text-sm ${mode === "sharepoint" ? "border-primary bg-primary text-primaryForeground" : "bg-card"}`}
          onClick={() => setMode("sharepoint")}
        >
          SharePoint
        </button>
      </div>

      {mode === "personal" ? (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            startTransition(() => void loadPersonalFiles());
          }}
        >
          <input
            className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm"
            placeholder="Search by exact file name, e.g. stock_snapshot"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <button className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground">
            Search
          </button>
        </form>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={siteId} onChange={(event) => void loadDrives(event.target.value)}>
            <option value="">Select SharePoint site</option>
            {sites.map((site) => (
              <option key={site.site_id} value={site.site_id}>{site.display_name}</option>
            ))}
          </select>
          <select className="rounded-md border bg-background px-3 py-2 text-sm" value={driveId} onChange={(event) => void loadDriveFiles(event.target.value)} disabled={!siteId}>
            <option value="">Select document library</option>
            {drives.map((drive) => (
              <option key={drive.drive_id} value={drive.drive_id}>{drive.name}</option>
            ))}
          </select>
        </div>
      )}

      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <div className="divide-y rounded-md border bg-card">
        {files.map((file) => (
          <button
            key={file.item_id}
            type="button"
            className="grid w-full gap-1 px-4 py-3 text-left text-sm hover:bg-muted md:grid-cols-[1fr_auto]"
            onClick={() => onSelect(file, mode === "sharepoint" ? siteId : null)}
          >
            <span className="font-medium">{file.name}</span>
            <span className="text-xs text-mutedForeground">
              {file.modified_at ? new Date(file.modified_at).toLocaleString() : "Modified date unavailable"} · {formatSize(file.size)}
            </span>
          </button>
        ))}
        {files.length === 0 ? (
          <p className="px-4 py-5 text-sm text-mutedForeground">
            {isPending ? "Loading Microsoft files..." : "No Excel or CSV files found yet. Try the exact file name without .xlsx."}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function formatSize(value: number | null) {
  if (!value) return "Unknown size";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
