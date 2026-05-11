"use client";

import { useState } from "react";
import { FileDown } from "lucide-react";

type ToastState = {
  tone: "success" | "error";
  message: string;
} | null;

export function DailyBriefButton({ compact = false }: { compact?: boolean }) {
  const [isLoading, setIsLoading] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);

  async function downloadBrief() {
    setIsLoading(true);
    setToast(null);
    try {
      const response = await fetch("/api/reports/daily-continuity-brief", {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error("Report request failed");
      }
      const blob = await response.blob();
      const filename = filenameFromDisposition(
        response.headers.get("Content-Disposition"),
      );
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
      setToast({ tone: "success", message: "Daily brief downloaded" });
    } catch {
      setToast({
        tone: "error",
        message: "Could not generate brief. Please try again.",
      });
    } finally {
      setIsLoading(false);
      window.setTimeout(() => setToast(null), 3500);
    }
  }

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        onClick={downloadBrief}
        disabled={isLoading}
        className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-3.5 py-2 text-left text-sm font-semibold text-white shadow-panel ring-1 ring-slate-900/10 transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-70"
      >
        <FileDown className="h-4 w-4" />
        <span className="leading-tight">
          {isLoading ? "Preparing brief..." : "Generate Daily Brief"}
          {!compact ? (
            <span className="block text-[11px] font-medium text-white/62">
              PDF for management review
            </span>
          ) : null}
        </span>
      </button>
      {toast ? (
        <div
          className={`absolute right-0 top-[calc(100%+8px)] z-20 w-64 rounded-xl px-3 py-2 text-xs font-semibold shadow-panel ring-1 ${
            toast.tone === "success"
              ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
              : "bg-red-50 text-red-800 ring-red-200"
          }`}
        >
          {toast.message}
        </div>
      ) : null}
    </div>
  );
}

function filenameFromDisposition(value: string | null) {
  const fallback = "opsdeck-daily-continuity-brief.pdf";
  if (!value) return fallback;
  const match = /filename="?([^"]+)"?/i.exec(value);
  return match?.[1] ?? fallback;
}

