from __future__ import annotations

from datetime import date
from typing import Any

from app.modules.reports.pdf import BLUE, GREEN, MUTED, NAVY, STEEL, PdfDocument


def build_operational_history_pdf(payload: dict[str, Any]) -> bytes:
    title = str(payload.get("title") or "OpsDeck Operational History Report")
    doc = PdfDocument(title=title)
    y = 770
    tenant = payload.get("tenant", {})
    period = payload.get("period", {})

    doc.text("OPSDECK", 44, y, size=11, color=BLUE, bold=True)
    y -= 30
    doc.wrapped_text(
        "OpsDeck Operational History Report",
        44,
        y,
        width_chars=42,
        size=24,
        color=NAVY,
        bold=True,
        leading=27,
    )
    y -= 68
    doc.text(str(tenant.get("name") or "Tenant"), 44, y, size=15, color=STEEL, bold=True)
    y -= 22
    doc.text(f"Report type: {payload.get('report_type', 'pilot').title()}", 44, y)
    y -= 16
    doc.text(f"Period: {format_period(period)}", 44, y)
    y -= 16
    doc.text(f"Version: {payload.get('version', 1)}", 44, y)
    y -= 16
    doc.text(f"Generated: {payload.get('generated_at', 'N/A')}", 44, y)
    y -= 34

    y = section(doc, "Executive Summary", y)
    y = paragraph(doc, payload.get("summary") or "No executive summary recorded yet.", y)
    y = section(doc, "Pilot / Monthly Scope", y)
    y = bullets(
        doc,
        [
            f"Tenant: {tenant.get('name', 'N/A')} ({tenant.get('slug', 'N/A')})",
            f"Plan: {tenant.get('plan_tier', 'N/A')}",
            f"Period: {format_period(period)}",
            f"Report type: {payload.get('report_type', 'pilot')}",
        ],
        y,
    )
    y = section(doc, "Weekly Review Summary", y)
    y = weekly_reviews(doc, payload.get("weekly_reviews", []), y)
    y = section(doc, "Milestones", y)
    y = record_list(doc, payload.get("milestones", []), y, "No milestones recorded.")
    y = section(doc, "Review Notes", y)
    y = record_list(doc, payload.get("notes", []), y, "No review notes recorded.")
    y = section(doc, "Operational Findings / Continuity Assessment", y)
    y = bullets(doc, payload.get("continuity_summary", []), y)
    y = section(doc, "Historical Review Summary", y)
    y = bullets(doc, payload.get("historical_summary", []), y)
    y = section(doc, "Data Quality / Limitations", y)
    y = bullets(doc, payload.get("limitations", []), y)
    y = section(doc, "Success Criteria Review", y)
    y = bullets(doc, payload.get("success_criteria", []), y)
    y = section(doc, "Recommended Next Steps", y)
    bullets(doc, payload.get("next_steps", []), y)
    return doc.build()


def section(doc: PdfDocument, label: str, y: float) -> float:
    y = doc.ensure_space(y, 52)
    doc.text(label, 44, y, size=14, color=GREEN, bold=True)
    doc.line(44, y - 8, 550, y - 8)
    return y - 26


def paragraph(doc: PdfDocument, value: str, y: float) -> float:
    y = doc.ensure_space(y, 56)
    return doc.wrapped_text(value, 44, y, width_chars=92, size=9.5, color=NAVY, leading=13) - 8


def bullets(doc: PdfDocument, values: list[str], y: float) -> float:
    items = values or ["No data available yet."]
    for item in items:
        y = doc.ensure_space(y, 28)
        doc.text("•", 50, y, size=10, color=STEEL, bold=True)
        y = doc.wrapped_text(item, 64, y, width_chars=88, size=9.2, color=NAVY, leading=12) - 4
    return y


def record_list(
    doc: PdfDocument,
    records: list[dict[str, Any]],
    y: float,
    empty: str,
) -> float:
    if not records:
        return bullets(doc, [empty], y)
    for record in records:
        y = doc.ensure_space(y, 62)
        title = record.get("title") or "Untitled"
        kind = record.get("milestone_type") or record.get("note_type") or "review"
        status = record.get("status")
        date_value = record.get("occurred_at") or record.get("note_date")
        doc.text(str(title), 50, y, size=10, color=NAVY, bold=True)
        y -= 13
        meta = f"{str(kind).replace('_', ' ').title()}"
        if status:
            meta += f" · {str(status).title()}"
        if date_value:
            meta += f" · {date_value}"
        doc.text(meta, 50, y, size=8.5, color=MUTED)
        body = record.get("description") or record.get("body")
        if body:
            y -= 13
            y = doc.wrapped_text(body, 50, y, width_chars=86, size=8.8, color=NAVY, leading=11)
        y -= 8
    return y


def weekly_reviews(doc: PdfDocument, records: list[dict[str, Any]], y: float) -> float:
    if not records:
        return bullets(doc, ["No structured weekly reviews recorded."], y)
    for record in records:
        y = doc.ensure_space(y, 72)
        title = f"Week {record.get('week_number')}: {record.get('review_title') or 'Review'}"
        doc.text(title, 50, y, size=10, color=NAVY, bold=True)
        y -= 13
        summary = record.get("meeting_summary") or "No meeting summary recorded."
        y = doc.wrapped_text(summary, 50, y, width_chars=86, size=8.8, color=NAVY, leading=11)
        actions = record.get("actions") or []
        if actions:
            y -= 4
            open_count = sum(1 for action in actions if action.get("status") != "Completed")
            doc.text(
                f"Actions: {len(actions)} total, {open_count} open/in progress.",
                50,
                y,
                size=8.5,
                color=MUTED,
            )
            y -= 12
        next_focus = record.get("next_focus")
        if next_focus:
            y = doc.wrapped_text(
                f"Next focus: {next_focus}",
                50,
                y,
                width_chars=86,
                size=8.5,
                color=MUTED,
                leading=11,
            )
        y -= 8
    return y


def format_period(period: dict[str, Any]) -> str:
    start = period.get("start")
    end = period.get("end")
    if start and end:
        return f"{format_date(start)} to {format_date(end)}"
    if start:
        return f"From {format_date(start)}"
    if end:
        return f"Through {format_date(end)}"
    return "Not specified"


def format_date(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
