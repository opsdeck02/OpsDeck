"use client";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="rounded-2xl border bg-card/90 p-4 shadow-panel">
      <h2 className="text-lg font-semibold">Dashboard load failed</h2>
      <p className="mt-2 text-sm text-mutedForeground">
        {error.message || "Something went wrong while loading this tenant view."}
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded-xl border px-4 py-2 text-sm font-semibold"
      >
        Retry
      </button>
    </div>
  );
}
