from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ExceptionCase,
    ExternalDataSource,
    Material,
    OperationalEvent,
    Plant,
    Tenant,
    User,
)
from app.models.enums import ExceptionStatus, OperationalEventFreshnessStatus
from app.modules.exceptions.service import list_exceptions
from app.modules.reports.pdf import (
    AMBER,
    BORDER,
    GREEN,
    LIGHT,
    MARGIN_X,
    MUTED,
    NAVY,
    PAGE_WIDTH,
    RED,
    STEEL,
    WHITE,
    PdfDocument,
)
from app.modules.rules.engine import RiskCandidate
from app.modules.signal_engine.service import (
    RiskWorkspaceResponse,
    get_risk_workspace,
    list_signal_risks,
)
from app.schemas.context import RequestContext

REPORT_FILENAME_PREFIX = "opsdeck-daily-continuity-brief"


@dataclass
class ReportAction:
    risk: str
    owner: str
    status: str
    next_action: str
    due_at: datetime | None


@dataclass
class ReportData:
    generated_at: datetime
    tenant_name: str
    risks: list[RiskCandidate]
    workspace: RiskWorkspaceResponse
    actions: list[ReportAction]
    resolved_today: int
    trust_counts: dict[str, int]
    low_confidence_signals: int
    sources_used: list[str]
    changes: list[str]


def build_daily_continuity_brief_pdf(db: Session, context: RequestContext) -> bytes:
    generated_at = datetime.now(UTC)
    data = collect_report_data(db, context, generated_at)
    return render_daily_brief(data)


def daily_brief_filename(generated_at: datetime | None = None) -> str:
    value = generated_at or datetime.now(UTC)
    return f"{REPORT_FILENAME_PREFIX}-{value.date().isoformat()}.pdf"


def collect_report_data(
    db: Session,
    context: RequestContext,
    generated_at: datetime,
) -> ReportData:
    tenant = db.get(Tenant, context.tenant_id)
    risks = list_signal_risks(db, context, now=generated_at)
    workspace = get_risk_workspace(
        db,
        context,
        timeline_limit=12,
        timeline_offset=0,
        now=generated_at,
    )
    action_records, _ = list_exceptions(db, context)
    start_of_day = datetime.combine(generated_at.date(), time.min, tzinfo=UTC)
    resolved_today = sum(
        1
        for item in action_records
        if item.status == ExceptionStatus.RESOLVED
        and normalized_datetime(item.updated_at) >= start_of_day
    )
    trust_counts, low_confidence = signal_trust_counts(db, context)
    sources = [
        source.source_name
        for source in db.scalars(
            select(ExternalDataSource)
            .where(ExternalDataSource.tenant_id == context.tenant_id)
            .order_by(ExternalDataSource.source_name)
        )
    ]
    return ReportData(
        generated_at=generated_at,
        tenant_name=tenant.name if tenant else context.tenant_slug,
        risks=risks,
        workspace=workspace,
        actions=action_tracker_rows(db, context, action_records),
        resolved_today=resolved_today,
        trust_counts=trust_counts,
        low_confidence_signals=low_confidence,
        sources_used=sources,
        changes=change_history(db, context, risks, generated_at),
    )


def signal_trust_counts(db: Session, context: RequestContext) -> tuple[dict[str, int], int]:
    counts = {status.value: 0 for status in OperationalEventFreshnessStatus}
    low_confidence = 0
    for event in db.scalars(
        select(OperationalEvent).where(OperationalEvent.tenant_id == context.tenant_id)
    ):
        status = event.freshness_status.value if event.freshness_status else "unknown"
        counts[status] = counts.get(status, 0) + 1
        if event.confidence_score is not None and Decimal(event.confidence_score) < Decimal("50"):
            low_confidence += 1
    return counts, low_confidence


def action_tracker_rows(
    db: Session,
    context: RequestContext,
    records: Iterable[ExceptionCase],
) -> list[ReportAction]:
    users = {
        user.id: user.full_name
        for user in db.scalars(select(User).where(User.is_active.is_(True)))
    }
    rows: list[ReportAction] = []
    for item in records:
        if item.status in {ExceptionStatus.RESOLVED, ExceptionStatus.DISMISSED}:
            continue
        risk = item.title
        plant = db.get(Plant, item.linked_plant_id) if item.linked_plant_id else None
        material = db.get(Material, item.linked_material_id) if item.linked_material_id else None
        if plant and material:
            risk = f"{material.code} at {plant.code}"
        rows.append(
            ReportAction(
                risk=risk,
                owner=users.get(item.owner_user_id, "Unassigned"),
                status=item.status.value.replace("_", " "),
                next_action=item.next_action or "No action recorded in exception tracker.",
                due_at=item.due_at,
            )
        )
    return rows[:12]


def change_history(
    db: Session,
    context: RequestContext,
    risks: list[RiskCandidate],
    generated_at: datetime,
) -> list[str]:
    changes: list[str] = []
    for risk in risks:
        if risk.escalation_state and risk.escalation_state != "unknown":
            changes.append(
                f"{risk.escalation_state.replace('_', ' ')}: "
                f"{risk.material_reference or 'material'} at "
                f"{risk.plant_reference or 'plant'}"
            )
    since = generated_at - timedelta(days=1)
    events = list(
        db.scalars(
            select(OperationalEvent)
            .where(
                OperationalEvent.tenant_id == context.tenant_id,
                OperationalEvent.occurred_at >= since,
            )
            .order_by(OperationalEvent.occurred_at.desc())
            .limit(6)
        )
    )
    for event in events:
        target = (
            event.shipment_reference
            or event.material_reference
            or event.source_reference
            or "signal"
        )
        changes.append(f"{event.event_type.value.replace('_', ' ')}: {target}")
    return dedupe(changes)[:8]


def render_daily_brief(data: ReportData) -> bytes:
    pdf = PdfDocument("OpsDeck Daily Continuity Brief")
    y = draw_cover(pdf, data)
    y = draw_executive_summary(pdf, data, y)
    y = draw_highest_priority_risk(pdf, data, y)
    y = draw_risk_table(pdf, data, y)
    y = draw_changes(pdf, data, y)
    y = draw_data_trust(pdf, data, y)
    draw_action_tracker(pdf, data, y)
    return pdf.build()


def draw_cover(pdf: PdfDocument, data: ReportData) -> float:
    pdf.rect(0, 760, PAGE_WIDTH, 82, fill=NAVY)
    pdf.text("OpsDeck", MARGIN_X, 808, size=18, color=WHITE, bold=True)
    pdf.text(
        "Continuity intelligence for industrial operations",
        MARGIN_X,
        790,
        size=9,
        color=(0.75, 0.84, 0.94),
    )
    pdf.text(
        "CONFIDENTIAL / INTERNAL USE",
        PAGE_WIDTH - 194,
        808,
        size=8,
        color=(0.75, 0.84, 0.94),
        bold=True,
    )
    pdf.text("Daily Continuity Brief", MARGIN_X, 720, size=27, color=NAVY, bold=True)
    pdf.text(data.tenant_name, MARGIN_X, 696, size=12, color=STEEL, bold=True)
    pdf.text(
        f"Generated {format_datetime(data.generated_at)}",
        MARGIN_X,
        678,
        size=10,
        color=MUTED,
    )
    selected = data.workspace.selected_risk
    if selected:
        pdf.rect(MARGIN_X, 612, PAGE_WIDTH - (MARGIN_X * 2), 44, fill=LIGHT, stroke=BORDER)
        pdf.text("Highest priority exposure", MARGIN_X + 16, 636, size=9, color=MUTED, bold=True)
        pdf.text(
            f"{selected.material_reference or 'Material'} at {selected.plant_reference or 'Plant'}",
            MARGIN_X + 16,
            618,
            size=14,
            color=NAVY,
            bold=True,
        )
        draw_severity(pdf, selected.severity, PAGE_WIDTH - 132, 625)
    else:
        pdf.rect(MARGIN_X, 612, PAGE_WIDTH - (MARGIN_X * 2), 44, fill=LIGHT, stroke=BORDER)
        pdf.text(
            "No critical continuity exposure detected",
            MARGIN_X + 16,
            627,
            size=14,
            color=NAVY,
            bold=True,
        )
    return 582


def draw_executive_summary(pdf: PdfDocument, data: ReportData, y: float) -> float:
    y = section_title(pdf, "Executive Summary", y)
    critical = sum(1 for risk in data.risks if risk.severity == "critical")
    watch = sum(1 for risk in data.risks if risk.severity in {"high", "medium"})
    stale_low = (
        data.trust_counts.get("stale", 0)
        + data.trust_counts.get("critical", 0)
        + data.low_confidence_signals
    )
    delayed_low_cover = sum(
        1
        for risk in data.risks
        if risk.risk_type in {"inbound_delay_against_cover", "shipment_degraded"}
    )
    selected = data.workspace.selected_risk
    cards = [
        ("Critical risks", str(critical), "inside operating buffer", RED if critical else GREEN),
        ("Watch-level risks", str(watch), "degradation building", AMBER if watch else GREEN),
        ("Resolved today", str(data.resolved_today), "closed exceptions", GREEN),
        (
            "Trust degradation",
            str(stale_low),
            "stale or low-confidence signals",
            RED if stale_low else GREEN,
        ),
        (
            "Delayed inbound",
            str(delayed_low_cover),
            "affecting continuity view",
            AMBER if delayed_low_cover else GREEN,
        ),
        (
            "Priority exposure",
            selected.material_reference if selected else "None",
            selected.plant_reference if selected else "No active exposure",
            RED if selected and selected.severity == "critical" else STEEL,
        ),
    ]
    x = MARGIN_X
    card_width = 158
    for index, (label, value, helper, color) in enumerate(cards):
        if index == 3:
            x = MARGIN_X
            y -= 82
        draw_kpi_card(pdf, x, y - 62, card_width, label, value, helper, color)
        x += card_width + 14
    return y - 158


def draw_highest_priority_risk(pdf: PdfDocument, data: ReportData, y: float) -> float:
    y = pdf.ensure_space(y, 145)
    y = section_title(pdf, "Highest Priority Risk", y)
    risk = data.workspace.selected_risk
    if risk is None:
        empty_state(
            pdf,
            y,
            (
                "No critical risks detected. The report still includes continuity trust "
                "and open action status."
            ),
        )
        return y - 50
    exposure = data.workspace.exposure
    summary = (
        risk.explainability.summary
        if risk.explainability
        else exposure.operational_reason
        if exposure
        else ""
    )
    pdf.rect(
        MARGIN_X,
        y - 112,
        PAGE_WIDTH - (MARGIN_X * 2),
        112,
        fill=(0.99, 0.98, 0.97),
        stroke=(0.93, 0.70, 0.70),
    )
    draw_severity(pdf, risk.severity, MARGIN_X + 16, y - 24)
    pdf.text(
        f"{risk.material_reference or 'Material'} at {risk.plant_reference or 'Plant'}",
        MARGIN_X + 16,
        y - 48,
        size=15,
        color=NAVY,
        bold=True,
    )
    pdf.text(
        f"Days of cover: {format_decimal(risk.days_of_cover)}",
        MARGIN_X + 16,
        y - 70,
        size=10,
        color=NAVY,
        bold=True,
    )
    pdf.text(
        f"Projected exhaustion: {format_date(risk.projected_exhaustion_date)}",
        MARGIN_X + 156,
        y - 70,
        size=10,
        color=NAVY,
    )
    pdf.text(
        f"Inbound status: {risk.continuity_status or 'unknown'}",
        MARGIN_X + 348,
        y - 70,
        size=10,
        color=NAVY,
    )
    pdf.wrapped_text(
        f"Why it matters: {summary or 'Continuity risk detected by configured thresholds.'}",
        MARGIN_X + 16,
        y - 90,
        width_chars=92,
        size=9,
        color=MUTED,
        max_lines=2,
    )
    action = first_action_text(data.actions)
    pdf.wrapped_text(
        f"Recorded next action: {action}",
        MARGIN_X + 16,
        y - 112,
        width_chars=92,
        size=9,
        color=MUTED,
        max_lines=1,
    )
    return y - 136


def draw_risk_table(pdf: PdfDocument, data: ReportData, y: float) -> float:
    y = pdf.ensure_space(y, 180)
    y = section_title(pdf, "Critical & Watch Risks", y)
    rows = [
        [
            risk.severity,
            risk.plant_reference or "-",
            risk.material_reference or "-",
            format_decimal(risk.days_of_cover),
            risk.continuity_status or "-",
            risk.freshness_status or "-",
            owner_for_risk(data.actions, risk),
            "open signal",
        ]
        for risk in data.risks
        if risk.severity in {"critical", "high", "medium"}
    ][:10]
    if not rows:
        empty_state(
            pdf,
            y,
            "No critical or watch-level continuity risks are active in the current tenant view.",
        )
        return y - 50
    return draw_table(
        pdf,
        y,
        ["Severity", "Plant", "Material", "Cover", "Inbound", "Freshness", "Owner", "Status"],
        rows,
        [54, 52, 82, 50, 74, 62, 72, 62],
    )


def draw_changes(pdf: PdfDocument, data: ReportData, y: float) -> float:
    y = pdf.ensure_space(y, 95)
    y = section_title(pdf, "What Changed Since Yesterday", y)
    if not data.changes:
        empty_state(
            pdf,
            y,
            (
                "Change history will appear after consecutive daily reports or risk "
                "snapshots are available."
            ),
        )
        return y - 50
    for change in data.changes[:6]:
        pdf.text("•", MARGIN_X + 2, y - 14, size=10, color=STEEL, bold=True)
        pdf.wrapped_text(
            change,
            MARGIN_X + 16,
            y - 14,
            width_chars=88,
            size=9,
            color=NAVY,
            max_lines=1,
        )
        y -= 20
    return y - 10


def draw_data_trust(pdf: PdfDocument, data: ReportData, y: float) -> float:
    y = pdf.ensure_space(y, 125)
    y = section_title(pdf, "Data Trust", y)
    trust = [
        ("Fresh", data.trust_counts.get("fresh", 0), GREEN),
        ("Delayed", data.trust_counts.get("delayed", 0), AMBER),
        ("Stale", data.trust_counts.get("stale", 0), RED),
        (
            "Low confidence",
            data.low_confidence_signals,
            RED if data.low_confidence_signals else GREEN,
        ),
    ]
    x = MARGIN_X
    for label, value, color in trust:
        draw_kpi_card(pdf, x, y - 54, 116, label, str(value), "signals", color)
        x += 128
    y -= 78
    sources = (
        ", ".join(data.sources_used[:5])
        if data.sources_used
        else "No external sources recorded"
    )
    pdf.wrapped_text(
        f"Sources used: {sources}",
        MARGIN_X,
        y,
        width_chars=96,
        size=9,
        color=MUTED,
        max_lines=2,
    )
    return y - 38


def draw_action_tracker(pdf: PdfDocument, data: ReportData, y: float) -> None:
    y = pdf.ensure_space(y, 150)
    y = section_title(pdf, "Action Tracker", y)
    if not data.actions:
        empty_state(pdf, y, "No open exception actions are currently recorded.")
        draw_disclaimer(pdf, y - 62)
        return
    rows = [
        [item.risk, item.owner, item.status, item.next_action, format_date(item.due_at)]
        for item in data.actions[:8]
    ]
    y = draw_table(
        pdf,
        y,
        ["Risk", "Owner", "Status", "Next action", "Due"],
        rows,
        [92, 78, 58, 220, 60],
    )
    draw_disclaimer(pdf, y - 12)


def draw_disclaimer(pdf: PdfDocument, y: float) -> None:
    y = pdf.ensure_space(y, 34)
    pdf.line(MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y, BORDER)
    pdf.wrapped_text(
        (
            "This report is based on available uploaded/synced operational data and configured "
            "thresholds. It should support, not replace, operational judgment."
        ),
        MARGIN_X,
        y - 18,
        width_chars=105,
        size=8,
        color=MUTED,
        max_lines=2,
    )


def draw_kpi_card(
    pdf: PdfDocument,
    x: float,
    y: float,
    width: float,
    label: str,
    value: str,
    helper: str,
    accent: tuple[float, float, float],
) -> None:
    pdf.rect(x, y, width, 60, fill=WHITE, stroke=BORDER)
    pdf.rect(x, y + 57, width, 3, fill=accent)
    pdf.text(label, x + 10, y + 42, size=8, color=MUTED, bold=True)
    pdf.text(value, x + 10, y + 19, size=18, color=NAVY, bold=True)
    pdf.wrapped_text(
        helper,
        x + 10,
        y + 8,
        width_chars=24,
        size=7.5,
        color=MUTED,
        max_lines=1,
    )


def section_title(pdf: PdfDocument, title: str, y: float) -> float:
    pdf.text(title, MARGIN_X, y, size=14, color=NAVY, bold=True)
    pdf.line(MARGIN_X, y - 8, PAGE_WIDTH - MARGIN_X, y - 8, BORDER)
    return y - 24


def draw_severity(pdf: PdfDocument, severity: str, x: float, y: float) -> None:
    color = RED if severity == "critical" else AMBER if severity in {"high", "medium"} else STEEL
    pdf.rect(x, y, 66, 16, fill=color)
    pdf.text(severity.upper(), x + 8, y + 5, size=7.5, color=WHITE, bold=True)


def draw_table(
    pdf: PdfDocument,
    y: float,
    headers: list[str],
    rows: list[list[str]],
    widths: list[int],
) -> float:
    x = MARGIN_X
    table_width = sum(widths)
    pdf.rect(x, y - 22, table_width, 22, fill=NAVY)
    current_x = x
    for header, width in zip(headers, widths, strict=True):
        pdf.text(header, current_x + 5, y - 14, size=7.5, color=WHITE, bold=True)
        current_x += width
    y -= 22
    for index, row in enumerate(rows):
        y = pdf.ensure_space(y, 28)
        fill = (0.98, 0.99, 1.0) if index % 2 == 0 else WHITE
        pdf.rect(x, y - 28, table_width, 28, fill=fill, stroke=BORDER, line_width=0.4)
        current_x = x
        for cell, width in zip(row, widths, strict=True):
            pdf.wrapped_text(
                cell,
                current_x + 5,
                y - 11,
                width_chars=max(8, width // 5),
                size=7.5,
                color=NAVY,
                max_lines=2,
                leading=9,
            )
            current_x += width
        y -= 28
    return y - 18


def empty_state(pdf: PdfDocument, y: float, text: str) -> None:
    pdf.rect(MARGIN_X, y - 36, PAGE_WIDTH - (MARGIN_X * 2), 36, fill=LIGHT, stroke=BORDER)
    pdf.wrapped_text(
        text,
        MARGIN_X + 12,
        y - 20,
        width_chars=94,
        size=9,
        color=MUTED,
        max_lines=2,
    )


def format_datetime(value: datetime) -> str:
    return value.strftime("%d %b %Y, %H:%M UTC")


def format_date(value: datetime | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value[:10]
    return value.date().isoformat()


def format_decimal(value: Decimal | str | None) -> str:
    if value is None:
        return "-"
    return f"{Decimal(str(value)):.2f}"


def normalized_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def first_action_text(actions: list[ReportAction]) -> str:
    return actions[0].next_action if actions else "No action recorded in exception tracker."


def owner_for_risk(actions: list[ReportAction], risk: RiskCandidate) -> str:
    for action in actions:
        if risk.material_reference and risk.material_reference in action.risk:
            return action.owner
    return "Unassigned"


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
