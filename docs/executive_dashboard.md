# Executive Dashboard

This document describes the MVP V1 sponsor/executive dashboard.

## Purpose Of Each Section

### KPI Strip

Provides a 2-minute summary of:

- total tracked plant/material combinations
- critical risks
- warning risks
- open exceptions
- unassigned exceptions

### Risk Summary

Shows the highest-priority plant/material continuity risks using the refined stock-cover engine.

For each item the dashboard shows:

- days of cover
- threshold
- risk status
- confidence
- effective inbound vs raw inbound

This helps leadership understand whether nominal inbound quantity is actually reliable enough to protect supply.

### Exception Summary

Highlights:

- critical open exceptions
- unassigned exceptions
- recently updated exceptions

This gives visibility into what is already being worked and where ownership gaps still exist.

### Movement Health Snapshot

Summarizes:

- stale movement data
- low-confidence shipments
- likely delayed shipments

This provides a fast trust check on post-arrival execution quality.

### What Needs Attention

This is the dashboard’s highest-signal section.

It deterministically ranks immediate-action items from:

- critical open exceptions
- critical stock risks
- delayed shipments

Each item shows:

- a short description
- the linked entity
- owner or unassigned
- recommended next step

## How Metrics Are Calculated

- `tracked_combinations`
  - total plant/material combinations returned by the stock-cover summary
- `critical_risks`
  - stock-cover rows with status `critical`
- `warning_risks`
  - stock-cover rows with status `warning`
- `open_exceptions`
  - exceptions with status `open` or `in_progress`
- `unassigned_exceptions`
  - open or in-progress exceptions with no owner

## Confidence And Freshness Interpretation

Leadership-facing freshness is shown for:

- stock data
- exception data
- movement data

The freshness labels come from the shared helper:

- `fresh`
- `aging`
- `stale`
- `unknown`

Confidence shown in risks and movement health should be read as:

- `high`
  - recent, complete, and consistent signals
- `medium`
  - usable but not fully supported
- `low`
  - stale, incomplete, or conflicting signals

## Known MVP Limitations

- The dashboard is based on deterministic heuristics, not predictive analytics.
- Financial impact, demurrage optimization, and procurement cost impact are not yet modeled.
- Exception prioritization is intentionally simple and not SLA-based.
- Movement health uses current signal quality and delay heuristics, not external telemetry.
- Executive summaries rely on the same tenant-scoped operational data already in the control tower; no separate reporting warehouse exists yet.
