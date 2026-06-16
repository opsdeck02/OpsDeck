from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel
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
from app.modules.line_stops.service import build_historical_validation_report
from app.modules.reports.pdf import (
    AMBER,
    BLUE,
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
    AssessmentCalibration,
    MaterialRiskRollup,
    RiskWorkspaceResponse,
    get_risk_workspace,
    list_material_risk_rollups,
    list_signal_risks,
)
from app.schemas.context import RequestContext

REPORT_FILENAME_PREFIX = "opsdeck-daily-continuity-brief"
EXECUTIVE_CONTINUITY_REPORT_TITLE = "Executive Continuity Report"


class ExecutiveReportSummary(BaseModel):
    generated_at: datetime
    tenant: str
    plant_scope: str
    material_scope: str | None = None
    materials_assessed: int
    critical_materials: int
    high_risk_materials: int
    average_assessment_calibration_score: Decimal | None
    average_assessment_calibration: str
    average_operational_trust_score: Decimal | None
    average_operational_trust: str
    historical_validation_detection_rate: Decimal | None


class ExecutiveInboundProtection(BaseModel):
    physical_inbound: Decimal | None
    trusted_inbound: Decimal | None
    visibility_uncertainty: Decimal | None
    interpretation: str


class ExecutiveContinuityProjection(BaseModel):
    warning_threshold_days: Decimal | None
    reserve_threshold_days: Decimal | None
    critical_threshold_days: Decimal | None
    interruption_threshold_days: Decimal | None
    warning_date: datetime | None
    reserve_breach_date: datetime | None
    critical_breach_date: datetime | None
    interruption_date: datetime | None
    interpretation: str


class ExecutiveMaterialRisk(BaseModel):
    material: str
    material_reference: str | None
    plant: str
    plant_reference: str | None
    severity: str
    current_usable_cover: Decimal | None
    earliest_breach_date: datetime | None
    operational_trust: str
    operational_trust_score: Decimal | None
    assessment_calibration: AssessmentCalibration | None
    recommended_priority: str
    why_escalating: list[str]
    inbound_protection: ExecutiveInboundProtection | None
    continuity_projection: ExecutiveContinuityProjection | None
    immediate_actions: list[str]
    short_term_actions: list[str]
    calibration_actions: list[str]


class ExecutiveHistoricalValidationEvidence(BaseModel):
    detection_rate: Decimal | None
    average_warning_lead_time_days: Decimal | None
    detected_incidents: int
    missed_incidents: int
    interpretation: str


class ExecutiveContinuityReport(BaseModel):
    summary: ExecutiveReportSummary
    critical_materials: list[ExecutiveMaterialRisk]
    historical_validation: ExecutiveHistoricalValidationEvidence
    recommended_actions: dict[str, list[str]]
    markdown_report: str
    pdf_ready_content: str


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


@dataclass
class RiskCluster:
    severity: str
    plant_reference: str
    material_reference: str
    exposure_basis: str
    days_of_cover: Decimal | str | None
    inbound_condition: str
    freshness_status: str
    owner: str
    status: str
    signal_count: int
    reasons: list[str]


def build_daily_continuity_brief_pdf(db: Session, context: RequestContext) -> bytes:
    generated_at = datetime.now(UTC)
    data = collect_report_data(db, context, generated_at)
    return render_daily_brief(data)


def daily_brief_filename(generated_at: datetime | None = None) -> str:
    value = generated_at or datetime.now(UTC)
    return f"{REPORT_FILENAME_PREFIX}-{value.date().isoformat()}.pdf"


def build_executive_continuity_report(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    generated_at: datetime | None = None,
) -> ExecutiveContinuityReport:
    report_time = generated_at or datetime.now(UTC)
    tenant = db.get(Tenant, context.tenant_id)
    rollups = list_material_risk_rollups(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        now=report_time,
    )
    priority_rollups = [
        rollup for rollup in rollups if rollup.highest_severity in {"critical", "high"}
    ]
    material_risks = [
        executive_material_risk_from_workspace(
            db,
            context,
            rollup,
            now=report_time,
        )
        for rollup in priority_rollups
    ]
    historical = build_historical_validation_report(db, context, limit=100)
    historical_evidence = executive_historical_evidence(historical)
    summary = executive_report_summary(
        tenant_name=tenant.name if tenant else context.tenant_slug,
        generated_at=report_time,
        plant_scope=plant_reference or "All plants",
        material_scope=material_reference,
        rollups=rollups,
        material_risks=material_risks,
        historical_detection_rate=historical_evidence.detection_rate,
    )
    actions = aggregate_executive_actions(material_risks)
    markdown = executive_report_markdown(summary, material_risks, historical_evidence, actions)
    return ExecutiveContinuityReport(
        summary=summary,
        critical_materials=material_risks,
        historical_validation=historical_evidence,
        recommended_actions=actions,
        markdown_report=markdown,
        pdf_ready_content=markdown,
    )


def executive_material_risk_from_workspace(
    db: Session,
    context: RequestContext,
    rollup: MaterialRiskRollup,
    *,
    now: datetime,
) -> ExecutiveMaterialRisk:
    workspace = get_risk_workspace(
        db,
        context,
        plant_reference=rollup.plant_reference,
        material_reference=rollup.material_reference,
        timeline_limit=12,
        timeline_offset=0,
        now=now,
    )
    risk = workspace.selected_risk
    inventory = first_or_none(workspace.inventory_continuity)
    plant_name, material_name = plant_material_labels(
        db,
        context,
        plant_reference=rollup.plant_reference,
        material_reference=rollup.material_reference,
    )
    operational_trust = risk.operational_trust if risk else None
    return ExecutiveMaterialRisk(
        material=material_name,
        material_reference=rollup.material_reference,
        plant=plant_name,
        plant_reference=rollup.plant_reference,
        severity=rollup.highest_severity,
        current_usable_cover=inventory.days_of_cover if inventory else None,
        earliest_breach_date=rollup.earliest_projected_exhaustion_date,
        operational_trust=(
            operational_trust.risk_precision_band if operational_trust else "unknown"
        ),
        operational_trust_score=(
            operational_trust.operational_trust_score if operational_trust else None
        ),
        assessment_calibration=workspace.assessment_calibration,
        recommended_priority=recommended_priority(rollup.highest_severity),
        why_escalating=why_escalating(workspace),
        inbound_protection=inbound_protection_summary(inventory),
        continuity_projection=continuity_projection_summary(inventory),
        immediate_actions=immediate_actions(risk),
        short_term_actions=short_term_actions(workspace),
        calibration_actions=(
            workspace.assessment_calibration.improvement_actions
            if workspace.assessment_calibration
            else []
        ),
    )


def executive_report_summary(
    *,
    tenant_name: str,
    generated_at: datetime,
    plant_scope: str,
    material_scope: str | None,
    rollups: list[MaterialRiskRollup],
    material_risks: list[ExecutiveMaterialRisk],
    historical_detection_rate: Decimal | None,
) -> ExecutiveReportSummary:
    calibration_scores = [
        item.assessment_calibration.score
        for item in material_risks
        if item.assessment_calibration is not None
    ]
    trust_scores = [
        item.operational_trust_score
        for item in material_risks
        if item.operational_trust_score is not None
    ]
    average_calibration = average_decimal(calibration_scores)
    average_trust = average_decimal(trust_scores)
    return ExecutiveReportSummary(
        generated_at=generated_at,
        tenant=tenant_name,
        plant_scope=plant_scope,
        material_scope=material_scope,
        materials_assessed=len(rollups),
        critical_materials=sum(1 for item in rollups if item.highest_severity == "critical"),
        high_risk_materials=sum(1 for item in rollups if item.highest_severity == "high"),
        average_assessment_calibration_score=average_calibration,
        average_assessment_calibration=calibration_band(average_calibration),
        average_operational_trust_score=average_trust,
        average_operational_trust=trust_band(average_trust),
        historical_validation_detection_rate=historical_detection_rate,
    )


def executive_historical_evidence(report) -> ExecutiveHistoricalValidationEvidence:
    summary = report.summary
    detection_rate = summary.detection_rate_percent if summary else None
    average_lead = summary.average_warning_lead_time_days if summary else None
    detected = summary.detected if summary else 0
    missed = summary.missed if summary else 0
    if detected > 0:
        interpretation = (
            "Historical validation detection evidence shows OpsDeck has detected prior continuity "
            "incidents before disruption occurred."
        )
    elif missed > 0:
        interpretation = (
            "Historical validation includes missed incidents; review data gaps before "
            "treating the model as proven."
        )
    else:
        interpretation = "No historical incident evidence is available yet."
    return ExecutiveHistoricalValidationEvidence(
        detection_rate=detection_rate,
        average_warning_lead_time_days=average_lead,
        detected_incidents=detected,
        missed_incidents=missed,
        interpretation=interpretation,
    )


def inbound_protection_summary(
    inventory,
) -> ExecutiveInboundProtection | None:
    if inventory is None:
        return None
    physical = inventory.physical_inbound_quantity_mt
    trusted = inventory.trusted_inbound_protection_mt
    uncertainty = inventory.visibility_uncertain_quantity_mt
    if physical and physical > 0 and trusted < physical:
        interpretation = (
            f"{physical} MT is physically inbound, but only {trusted} MT is trusted "
            "as continuity protection with current visibility."
        )
    elif trusted and trusted > 0:
        interpretation = "Inbound protection is currently trusted for continuity cover."
    else:
        interpretation = "No trusted inbound protection is available for this material."
    return ExecutiveInboundProtection(
        physical_inbound=physical,
        trusted_inbound=trusted,
        visibility_uncertainty=uncertainty,
        interpretation=interpretation,
    )


def continuity_projection_summary(
    inventory,
) -> ExecutiveContinuityProjection | None:
    if inventory is None:
        return None
    cover = inventory.time_phased_cover
    if cover is None:
        return ExecutiveContinuityProjection(
            warning_threshold_days=inventory.warning_days,
            reserve_threshold_days=inventory.minimum_buffer_stock_days,
            critical_threshold_days=inventory.threshold_days,
            interruption_threshold_days=None,
            warning_date=None,
            reserve_breach_date=None,
            critical_breach_date=None,
            interruption_date=inventory.projected_exhaustion_date,
            interpretation="Time-phased continuity projection is not available yet.",
        )
    return ExecutiveContinuityProjection(
        warning_threshold_days=inventory.warning_days,
        reserve_threshold_days=inventory.minimum_buffer_stock_days,
        critical_threshold_days=inventory.threshold_days,
        interruption_threshold_days=None,
        warning_date=cover.warning_date,
        reserve_breach_date=cover.reserve_breach_date,
        critical_breach_date=cover.critical_breach_date,
        interruption_date=cover.interruption_date,
        interpretation=projection_interpretation(cover.interruption_date or cover.warning_date),
    )


def aggregate_executive_actions(
    material_risks: list[ExecutiveMaterialRisk],
) -> dict[str, list[str]]:
    return {
        "immediate": dedupe(
            action for material in material_risks for action in material.immediate_actions
        )[:8],
        "short_term": dedupe(
            action for material in material_risks for action in material.short_term_actions
        )[:8],
        "calibration": dedupe(
            action for material in material_risks for action in material.calibration_actions
        )[:8],
    }


def executive_report_markdown(
    summary: ExecutiveReportSummary,
    material_risks: list[ExecutiveMaterialRisk],
    historical: ExecutiveHistoricalValidationEvidence,
    actions: dict[str, list[str]],
) -> str:
    lines = [
        f"# {EXECUTIVE_CONTINUITY_REPORT_TITLE}",
        "",
        "## Executive Summary",
        f"Generated Date: {summary.generated_at.date().isoformat()}",
        f"Tenant: {summary.tenant}",
        f"Plant Scope: {summary.plant_scope}",
        f"Materials Assessed: {summary.materials_assessed}",
        f"Critical Materials: {summary.critical_materials}",
        f"High Risk Materials: {summary.high_risk_materials}",
        f"Average Assessment Calibration: {summary.average_assessment_calibration}",
        f"Average Operational Trust: {summary.average_operational_trust}",
        (
            "Past Incident Analysis Detection Rate: "
            f"{summary.historical_validation_detection_rate or 'N/A'}%"
        ),
        "",
        "## Critical Materials",
    ]
    if not material_risks:
        lines.append("No critical or high material risks are active in the selected scope.")
    for material in material_risks:
        lines.extend(
            [
                "",
                f"### {material.material} at {material.plant}",
                f"Severity: {material.severity.title()}",
                f"Current Usable Cover: {material.current_usable_cover or 'N/A'} days",
                f"Earliest Breach Date: {date_or_na(material.earliest_breach_date)}",
                f"Operational Trust: {material.operational_trust}",
                (
                    "Assessment Calibration: "
                    f"{material.assessment_calibration.status}"
                    if material.assessment_calibration
                    else "Assessment Calibration: N/A"
                ),
                f"Recommended Priority: {material.recommended_priority}",
                "",
                "Why This Is Escalating:",
                *[f"- {item}" for item in material.why_escalating],
                "",
                "Inbound Protection Quality:",
                (
                    f"- {material.inbound_protection.interpretation}"
                    if material.inbound_protection
                    else "- Unavailable"
                ),
                "",
                "Assessment Calibration:",
                *[
                    f"- {item}"
                    for item in (
                        material.assessment_calibration.limitations
                        if material.assessment_calibration
                        else ["Calibration unavailable."]
                    )
                ],
            ]
        )
    lines.extend(
        [
            "",
            "## Past Incident Analysis",
            "Incident Replay",
            f"Detection Rate: {historical.detection_rate or 'N/A'}%",
            f"Average Warning Lead Time: {historical.average_warning_lead_time_days or 'N/A'} days",
            f"Detected Incidents: {historical.detected_incidents}",
            f"Missed Incidents: {historical.missed_incidents}",
            historical.interpretation,
            "",
            "## Recommended Actions",
            "Immediate Actions:",
            *[
                f"- {item}"
                for item in actions.get("immediate", [])
                or ["No immediate actions returned."]
            ],
            "Short-Term Actions:",
            *[
                f"- {item}"
                for item in actions.get("short_term", [])
                or ["No short-term actions returned."]
            ],
            "Data / Calibration Actions:",
            *[
                f"- {item}"
                for item in actions.get("calibration", [])
                or ["No calibration actions returned."]
            ],
        ]
    )
    return "\n".join(lines)


def plant_material_labels(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None,
    material_reference: str | None,
) -> tuple[str, str]:
    plant = (
        db.scalar(
            select(Plant).where(
                Plant.tenant_id == context.tenant_id,
                Plant.code == plant_reference,
            )
        )
        if plant_reference
        else None
    )
    material = (
        db.scalar(
            select(Material).where(
                Material.tenant_id == context.tenant_id,
                Material.code == material_reference,
            )
        )
        if material_reference
        else None
    )
    return (
        plant.name if plant else plant_reference or "All plants",
        material.name if material else material_reference or "Material",
    )


def recommended_priority(severity: str) -> str:
    if severity == "critical":
        return "Immediate Review"
    if severity == "high":
        return "Priority Review"
    return "Monitor"


def why_escalating(workspace: RiskWorkspaceResponse) -> list[str]:
    reasons = []
    if workspace.explainability is not None:
        reasons.extend(workspace.explainability.reason_chain[:5])
    if workspace.selected_risk is not None:
        reasons.extend(workspace.selected_risk.rule_reasons[:5])
    return dedupe(reasons)[:6] or ["OpsDeck returned an active continuity signal."]


def immediate_actions(risk: RiskCandidate | None) -> list[str]:
    if risk is None:
        return []
    actions = []
    for action in risk.operational_recommendations:
        urgency = action.urgency.lower()
        if urgency in {"immediate", "critical", "high"}:
            actions.append(action.operational_reason)
    if not actions and risk.severity in {"critical", "high"}:
        actions.append("Review this material risk in the Risk Workspace.")
    return dedupe(actions)


def short_term_actions(workspace: RiskWorkspaceResponse) -> list[str]:
    actions = []
    risk = workspace.selected_risk
    if risk is not None:
        for action in risk.operational_recommendations:
            urgency = action.urgency.lower()
            if urgency not in {"immediate", "critical", "high"}:
                actions.append(action.operational_reason)
    if workspace.inventory_continuity:
        actions.append("Review reserve strategy and confirm alternate sourcing options.")
    return dedupe(actions)


def projection_interpretation(date_value: datetime | None) -> str:
    if date_value is None:
        return "Projected continuity exposure date is not available yet."
    return f"Continuity becomes exposed around {date_value.date().isoformat()}."


def average_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return quantize_decimal(sum(values, start=Decimal("0")) / Decimal(len(values)))


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def calibration_band(score: Decimal | None) -> str:
    if score is None:
        return "Not Available"
    if score >= Decimal("80"):
        return "Calibrated"
    if score >= Decimal("55"):
        return "Partially Calibrated"
    if score > Decimal("0"):
        return "Uncalibrated"
    return "Insufficient Data"


def trust_band(score: Decimal | None) -> str:
    if score is None:
        return "Unknown"
    if score >= Decimal("75"):
        return "Strong"
    if score >= Decimal("50"):
        return "Moderate"
    return "Weak"


def date_or_na(value: datetime | None) -> str:
    return value.date().isoformat() if value is not None else "N/A"


def first_or_none(items: list):
    return items[0] if items else None


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
        source_label(source)
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
    draw_cover(pdf, data)
    draw_executive_summary(pdf, data)
    draw_highest_priority_risk(pdf, data)
    draw_continuity_position(pdf, data)
    pdf.new_page()
    y = draw_page_header(pdf, data, "Critical & Watch Exposure")
    y = draw_risk_clusters(pdf, data, y)
    draw_action_tracker(pdf, data, y)
    pdf.new_page()
    y = draw_page_header(pdf, data, "Change & Trust Review")
    y = draw_changes(pdf, data, y)
    y = draw_data_trust(pdf, data, y)
    draw_source_notes(pdf, data, y)
    return pdf.build()


def draw_cover(pdf: PdfDocument, data: ReportData) -> None:
    pdf.rect(0, 704, PAGE_WIDTH, 138, fill=NAVY)
    pdf.rect(0, 704, 10, 138, fill=BLUE)
    draw_opsdeck_brand(pdf, MARGIN_X, 790, dark=True)
    pdf.text(
        "Daily Continuity Brief",
        MARGIN_X,
        750,
        size=29,
        color=WHITE,
        bold=True,
    )
    pdf.text(
        "Operational continuity position based on available synced/uploaded data.",
        MARGIN_X,
        728,
        size=10,
        color=(0.75, 0.84, 0.94),
    )
    pdf.rect(PAGE_WIDTH - 210, 782, 166, 24, fill=(0.08, 0.16, 0.28), stroke=(0.18, 0.30, 0.45))
    pdf.text(
        "CONFIDENTIAL / INTERNAL USE",
        PAGE_WIDTH - 198,
        791,
        size=7.5,
        color=(0.78, 0.86, 0.94),
        bold=True,
    )
    pdf.text("Tenant / scope", MARGIN_X, 676, size=8, color=MUTED, bold=True)
    pdf.text(data.tenant_name, MARGIN_X, 656, size=15, color=NAVY, bold=True)
    pdf.text("Generated", PAGE_WIDTH - 196, 676, size=8, color=MUTED, bold=True)
    pdf.text(
        format_datetime(data.generated_at),
        PAGE_WIDTH - 196,
        656,
        size=11,
        color=NAVY,
        bold=True,
    )


def draw_executive_summary(pdf: PdfDocument, data: ReportData) -> None:
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
    pdf.text("Executive Summary", MARGIN_X, 612, size=15, color=NAVY, bold=True)
    pdf.line(MARGIN_X, 603, PAGE_WIDTH - MARGIN_X, 603, BORDER)
    x = MARGIN_X
    y = 522
    card_width = 158
    for index, (label, value, helper, color) in enumerate(cards):
        if index == 3:
            x = MARGIN_X
            y -= 84
        draw_kpi_card(pdf, x, y, card_width, label, value, helper, color)
        x += card_width + 14


def draw_highest_priority_risk(pdf: PdfDocument, data: ReportData) -> None:
    y = 338
    pdf.text("Highest Priority Risk", MARGIN_X, y, size=15, color=NAVY, bold=True)
    pdf.line(MARGIN_X, y - 9, PAGE_WIDTH - MARGIN_X, y - 9, BORDER)
    y -= 24
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
        return
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
        y - 162,
        PAGE_WIDTH - (MARGIN_X * 2),
        162,
        fill=(0.995, 0.985, 0.98),
        stroke=(0.92, 0.72, 0.72),
    )
    pdf.rect(MARGIN_X, y - 162, 5, 162, fill=severity_color(risk.severity))
    draw_severity(pdf, risk.severity, MARGIN_X + 18, y - 28, width=82, height=20)
    pdf.text(
        f"{risk.material_reference or 'Material'} at {risk.plant_reference or 'Plant'}",
        MARGIN_X + 16,
        y - 58,
        size=18,
        color=NAVY,
        bold=True,
    )
    metric_y = y - 102
    draw_risk_metric(
        pdf,
        MARGIN_X + 16,
        metric_y,
        "Days of cover",
        format_decimal(risk.days_of_cover),
    )
    draw_risk_metric(
        pdf,
        MARGIN_X + 142,
        metric_y,
        "Projected exhaustion",
        format_date(risk.projected_exhaustion_date),
    )
    draw_risk_metric(
        pdf,
        MARGIN_X + 300,
        metric_y,
        "Inbound condition",
        risk.continuity_status or "unknown",
    )
    draw_risk_metric(pdf, MARGIN_X + 414, metric_y, "Data trust", trust_label(risk))
    pdf.wrapped_text(
        f"Why it matters: {summary or 'Continuity risk detected by configured thresholds.'}",
        MARGIN_X + 16,
        y - 128,
        width_chars=88,
        size=9.2,
        color=MUTED,
        max_lines=2,
    )
    action = first_action_text(data.actions)
    pdf.wrapped_text(
        f"Recorded next action: {action}",
        MARGIN_X + 16,
        y - 152,
        width_chars=88,
        size=9.2,
        color=MUTED,
        max_lines=1,
    )


def draw_continuity_position(pdf: PdfDocument, data: ReportData) -> None:
    y = 124
    pdf.text("Today's Continuity Position", MARGIN_X, y, size=14, color=NAVY, bold=True)
    pdf.line(MARGIN_X, y - 8, PAGE_WIDTH - MARGIN_X, y - 8, BORDER)
    for line in continuity_position_lines(data)[:3]:
        pdf.rect(MARGIN_X, y - 38, 4, 22, fill=STEEL)
        pdf.wrapped_text(
            line,
            MARGIN_X + 14,
            y - 30,
            width_chars=92,
            size=9.5,
            color=NAVY,
            max_lines=1,
        )
        y -= 28


def draw_risk_clusters(pdf: PdfDocument, data: ReportData, y: float) -> float:
    clusters = build_risk_clusters(data)
    if not clusters:
        empty_state(
            pdf,
            y,
            "No critical or watch-level continuity risks are active in the current tenant view.",
        )
        return y - 52
    for cluster in clusters[:7]:
        y = pdf.ensure_space(y, 86)
        draw_cluster_card(pdf, cluster, y)
        y -= 96
    return y


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
        [
            action_priority(item),
            item.risk,
            item.owner,
            item.status,
            item.next_action,
            format_date(item.due_at),
        ]
        for item in data.actions[:8]
    ]
    y = draw_table(
        pdf,
        y,
        ["Priority", "Risk / material", "Owner", "Status", "Next action", "Due / age"],
        rows,
        [54, 88, 64, 54, 190, 58],
    )
    draw_disclaimer(pdf, y - 12)


def draw_source_notes(pdf: PdfDocument, data: ReportData, y: float) -> None:
    y = pdf.ensure_space(y, 95)
    y = section_title(pdf, "Source & Assumption Notes", y)
    notes = [
        "Risk severity and continuity exposure are based on configured thresholds.",
        "Data trust reflects freshness, confidence, and source completeness at report time.",
        "No AI-generated recommendations or forecasts are included in this brief.",
    ]
    for note in notes:
        pdf.text("•", MARGIN_X + 2, y - 14, size=10, color=STEEL, bold=True)
        pdf.wrapped_text(note, MARGIN_X + 16, y - 14, width_chars=88, size=9, color=MUTED)
        y -= 20
    draw_disclaimer(pdf, y - 6)


def draw_page_header(pdf: PdfDocument, data: ReportData, title: str) -> float:
    draw_opsdeck_brand(pdf, MARGIN_X, 794, dark=False)
    pdf.text(title, MARGIN_X, 742, size=21, color=NAVY, bold=True)
    pdf.text(data.tenant_name, MARGIN_X, 722, size=9, color=MUTED)
    pdf.text(format_datetime(data.generated_at), PAGE_WIDTH - 190, 794, size=8.5, color=MUTED)
    pdf.line(MARGIN_X, 706, PAGE_WIDTH - MARGIN_X, 706, BORDER)
    return 676


def draw_opsdeck_brand(pdf: PdfDocument, x: float, y: float, *, dark: bool) -> None:
    icon_fill = BLUE if not dark else (0.12, 0.35, 0.56)
    text_color = WHITE if dark else NAVY
    deck_color = (0.75, 0.86, 0.96) if dark else STEEL
    pdf.rect(x, y - 16, 28, 28, fill=icon_fill, stroke=(0.35, 0.55, 0.72))
    pdf.polygon(
        [
            (x + 17.5, y + 9),
            (x + 8, y - 3),
            (x + 15, y - 3),
            (x + 13, y - 14),
            (x + 23, y + 1),
            (x + 15.8, y + 1),
        ],
        fill=WHITE,
    )
    pdf.text("Ops", x + 38, y - 1, size=15, color=text_color, bold=True)
    pdf.text("Deck", x + 66, y - 1, size=15, color=deck_color, bold=True)


def draw_risk_metric(pdf: PdfDocument, x: float, y: float, label: str, value: str) -> None:
    pdf.rect(x, y - 34, 104, 38, fill=WHITE, stroke=(0.88, 0.78, 0.78), line_width=0.5)
    pdf.text(label, x + 7, y - 8, size=7.2, color=MUTED, bold=True)
    pdf.wrapped_text(value, x + 7, y - 24, width_chars=16, size=10, color=NAVY, bold=True)


def draw_cluster_card(pdf: PdfDocument, cluster: RiskCluster, y: float) -> None:
    color = severity_color(cluster.severity)
    pdf.rect(MARGIN_X, y - 78, PAGE_WIDTH - (MARGIN_X * 2), 78, fill=WHITE, stroke=BORDER)
    pdf.rect(MARGIN_X, y - 78, 5, 78, fill=color)
    draw_severity(pdf, cluster.severity, MARGIN_X + 14, y - 24)
    pdf.text(
        f"{cluster.material_reference} at {cluster.plant_reference}",
        MARGIN_X + 94,
        y - 18,
        size=13,
        color=NAVY,
        bold=True,
    )
    pdf.text(
        f"{cluster.exposure_basis.replace('_', ' ')} • {cluster.signal_count} contributing signals",
        MARGIN_X + 94,
        y - 34,
        size=8.5,
        color=MUTED,
    )
    draw_cluster_field(pdf, MARGIN_X + 14, y - 54, "Cover", format_decimal(cluster.days_of_cover))
    draw_cluster_field(pdf, MARGIN_X + 94, y - 54, "Inbound", cluster.inbound_condition)
    draw_cluster_field(pdf, MARGIN_X + 190, y - 54, "Freshness", cluster.freshness_status)
    draw_cluster_field(pdf, MARGIN_X + 286, y - 54, "Owner", cluster.owner)
    draw_cluster_field(pdf, MARGIN_X + 392, y - 54, "Status", cluster.status)


def draw_cluster_field(pdf: PdfDocument, x: float, y: float, label: str, value: str) -> None:
    pdf.text(label, x, y, size=7.2, color=MUTED, bold=True)
    pdf.wrapped_text(value, x, y - 13, width_chars=17, size=8.5, color=NAVY, max_lines=1)


def continuity_position_lines(data: ReportData) -> list[str]:
    selected = data.workspace.selected_risk
    delayed = sum(
        1
        for risk in data.risks
        if risk.risk_type in {"inbound_delay_against_cover", "shipment_degraded"}
    )
    trust_degradation = (
        data.trust_counts.get("stale", 0)
        + data.trust_counts.get("critical", 0)
        + data.low_confidence_signals
    )
    if selected:
        lines = [
            (
                f"Critical exposure exists in {selected.material_reference or 'material'} "
                f"at {selected.plant_reference or 'plant'} with "
                f"{format_decimal(selected.days_of_cover)} days of cover."
            )
        ]
    else:
        lines = ["No critical risks detected from available data."]
    lines.append(f"Delayed inbound movements are affecting {delayed} continuity signals.")
    if trust_degradation:
        lines.append(f"{trust_degradation} stale or low-confidence signals require caution.")
    else:
        lines.append("No stale or low-confidence signals are currently detected.")
    return lines


def build_risk_clusters(data: ReportData) -> list[RiskCluster]:
    grouped: dict[tuple[str, str, str], list[RiskCandidate]] = {}
    for risk in data.risks:
        if risk.severity not in {"critical", "high", "medium"}:
            continue
        key = (
            risk.plant_reference or "-",
            risk.material_reference or "-",
            exposure_basis_for(risk),
        )
        grouped.setdefault(key, []).append(risk)
    clusters = [
        cluster_from_risks(plant, material, basis, risks, data.actions)
        for (plant, material, basis), risks in grouped.items()
    ]
    return sorted(clusters, key=lambda item: (severity_rank(item.severity), item.plant_reference))


def cluster_from_risks(
    plant: str,
    material: str,
    basis: str,
    risks: list[RiskCandidate],
    actions: list[ReportAction],
) -> RiskCluster:
    worst = sorted(risks, key=lambda item: severity_rank(item.severity))[0]
    return RiskCluster(
        severity=worst.severity,
        plant_reference=plant,
        material_reference=material,
        exposure_basis=basis,
        days_of_cover=min_decimal([risk.days_of_cover for risk in risks]),
        inbound_condition=worst_value([risk.continuity_status for risk in risks], "unknown"),
        freshness_status=worst_freshness([risk.freshness_status for risk in risks]),
        owner=owner_for_risk(actions, worst),
        status="open signal",
        signal_count=sum(max(1, len(risk.source_event_ids)) for risk in risks),
        reasons=dedupe(reason for risk in risks for reason in risk.rule_reasons)[:3],
    )


def exposure_basis_for(risk: RiskCandidate) -> str:
    if risk.risk_type in {"days_of_cover_breach", "projected_stockout"}:
        return "available_cover"
    if risk.risk_type in {"inbound_delay_against_cover", "shipment_degraded"}:
        return "inbound_continuity"
    if risk.risk_type in {"stale_signal_risk", "low_confidence_signal_risk"}:
        return "signal_trust"
    return risk.risk_type


def severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 9)


def severity_color(value: str) -> tuple[float, float, float]:
    if value == "critical":
        return RED
    if value in {"high", "medium"}:
        return AMBER
    return STEEL


def worst_freshness(values: list[str | None]) -> str:
    order = {"critical": 0, "stale": 1, "delayed": 2, "unknown": 3, "fresh": 4}
    clean = [value or "unknown" for value in values]
    return sorted(clean, key=lambda item: order.get(item, 3))[0] if clean else "unknown"


def min_decimal(values: list[Decimal | str | None]) -> Decimal | str | None:
    parsed = [Decimal(str(value)) for value in values if value is not None]
    return min(parsed) if parsed else None


def worst_value(values: list[str | None], fallback: str) -> str:
    for preferred in ("degraded", "watch", "unknown", "on_track"):
        if preferred in values:
            return preferred
    return next((value for value in values if value), fallback)


def trust_label(risk: RiskCandidate) -> str:
    confidence = format_decimal(risk.confidence_score)
    freshness = risk.freshness_status or "unknown"
    return f"{confidence} / {freshness}"


def action_priority(item: ReportAction) -> str:
    if item.due_at and normalized_datetime(item.due_at) < datetime.now(UTC):
        return "overdue"
    if item.status == "in progress":
        return "active"
    return "open"


def source_label(source: ExternalDataSource) -> str:
    status = source.last_sync_status or "not synced"
    if source.last_synced_at:
        return f"{source.source_name} ({status}, last sync {format_date(source.last_synced_at)})"
    return f"{source.source_name} ({status})"


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
    pdf.rect(x, y, width, 66, fill=WHITE, stroke=BORDER)
    pdf.rect(x, y, 4, 66, fill=accent)
    pdf.text(label, x + 13, y + 47, size=8, color=MUTED, bold=True)
    pdf.text(value, x + 13, y + 24, size=19, color=NAVY, bold=True)
    pdf.wrapped_text(
        helper,
        x + 13,
        y + 11,
        width_chars=24,
        size=7.5,
        color=MUTED,
        max_lines=1,
    )


def section_title(pdf: PdfDocument, title: str, y: float) -> float:
    pdf.text(title, MARGIN_X, y, size=14, color=NAVY, bold=True)
    pdf.line(MARGIN_X, y - 8, PAGE_WIDTH - MARGIN_X, y - 8, BORDER)
    return y - 24


def draw_severity(
    pdf: PdfDocument,
    severity: str,
    x: float,
    y: float,
    *,
    width: float = 66,
    height: float = 16,
) -> None:
    pdf.rect(x, y, width, height, fill=severity_color(severity))
    pdf.text(severity.upper(), x + 8, y + (height / 2) - 3, size=7.5, color=WHITE, bold=True)


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
