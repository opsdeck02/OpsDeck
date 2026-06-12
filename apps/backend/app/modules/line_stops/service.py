from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    LineStopIncident,
    Material,
    Plant,
    PlantMaterialThreshold,
    Shipment,
    StockSnapshot,
    Tenant,
)
from app.modules.line_stops.schemas import (
    HistoricalValidationIncidentResult,
    HistoricalValidationReport,
    HistoricalValidationSummary,
    LineStopIncidentCreate,
    LineStopIncidentListResponse,
    LineStopIncidentOut,
)
from app.modules.stock.schemas import TimePhasedCoverResult
from app.modules.stock.time_phased_cover import (
    TimePhasedCoverInputs,
    TimePhasedInbound,
    evaluate_time_phased_cover,
)
from app.schemas.context import RequestContext


def create_line_stop_incident(
    db: Session,
    context: RequestContext,
    payload: LineStopIncidentCreate,
) -> LineStopIncidentOut:
    plant = db.scalar(
        select(Plant).where(Plant.id == payload.plant_id, Plant.tenant_id == context.tenant_id)
    )
    material = db.scalar(
        select(Material).where(
            Material.id == payload.material_id,
            Material.tenant_id == context.tenant_id,
        )
    )
    if plant is None or material is None:
        raise ValueError("Plant or material was not found for this tenant")

    incident = LineStopIncident(
        tenant_id=context.tenant_id,
        plant_id=plant.id,
        material_id=material.id,
        stopped_at=ensure_utc(payload.stopped_at),
        duration_hours=quantize_decimal(payload.duration_hours),
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return serialize_incident(db, incident)


def list_line_stop_incidents(
    db: Session,
    context: RequestContext,
    *,
    limit: int = 25,
) -> LineStopIncidentListResponse:
    items = list(
        db.scalars(
            select(LineStopIncident)
            .where(LineStopIncident.tenant_id == context.tenant_id)
            .order_by(LineStopIncident.stopped_at.desc())
            .limit(limit)
        )
    )
    total_duration = sum(
        (item.duration_hours for item in items),
        start=Decimal("0"),
    )
    return LineStopIncidentListResponse(
        total_incidents=len(items),
        total_duration_hours=quantize_decimal(total_duration),
        items=[serialize_incident(db, item) for item in items],
    )


def build_historical_validation_report(
    db: Session,
    context: RequestContext,
    *,
    limit: int = 25,
) -> HistoricalValidationReport:
    incidents = list(
        db.scalars(
            select(LineStopIncident)
            .where(LineStopIncident.tenant_id == context.tenant_id)
            .order_by(LineStopIncident.stopped_at.desc())
            .limit(limit)
        )
    )
    results = [
        validate_historical_incident(db, context, incident)
        for incident in incidents
    ]
    lead_times = [
        result.lead_time_gained_hours
        for result in results
        if result.lead_time_gained_hours is not None
    ]
    average_lead_time = (
        quantize_decimal(sum(lead_times, start=Decimal("0")) / Decimal(len(lead_times)))
        if lead_times
        else None
    )
    tenant = db.get(Tenant, context.tenant_id)
    summary = historical_validation_summary(results)
    return HistoricalValidationReport(
        total_incidents=len(results),
        incidents_with_warning=sum(
            1 for result in results if result.predicted_warning_date is not None
        ),
        incidents_missed=sum(1 for result in results if result.predicted_warning_date is None),
        average_lead_time_hours=average_lead_time,
        summary=summary,
        results=results,
        generated_at=datetime.now(UTC),
        tenant=tenant.name if tenant else context.tenant_slug,
        report_markdown=historical_validation_markdown(
            results,
            summary,
            tenant_name=tenant.name if tenant else context.tenant_slug,
        ),
    )


def validate_historical_incident(
    db: Session,
    context: RequestContext,
    incident: LineStopIncident,
) -> HistoricalValidationIncidentResult:
    plant = db.get(Plant, incident.plant_id)
    material = db.get(Material, incident.material_id)
    incident_time = ensure_utc(incident.stopped_at)
    missed_signals: list[str] = []
    snapshot = db.scalar(
        select(StockSnapshot)
        .where(
            StockSnapshot.tenant_id == context.tenant_id,
            StockSnapshot.plant_id == incident.plant_id,
            StockSnapshot.material_id == incident.material_id,
            StockSnapshot.snapshot_time <= incident_time,
        )
        .order_by(StockSnapshot.snapshot_time.desc())
    )
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == context.tenant_id,
            PlantMaterialThreshold.plant_id == incident.plant_id,
            PlantMaterialThreshold.material_id == incident.material_id,
        )
    )
    if snapshot is None:
        missed_signals.append("No stock snapshot existed before the incident date.")
        return incident_result(
            incident=incident,
            plant=plant,
            material=material,
            incident_time=incident_time,
            predicted_warning_date=None,
            lead_time_gained_hours=None,
            missed_signals=missed_signals,
            confidence_level="low",
            calibration_status="UNCALIBRATED",
            cover=None,
        )
    if threshold is None:
        missed_signals.append("Continuity thresholds were missing for the incident context.")
    if snapshot.daily_consumption_mt <= 0:
        missed_signals.append("Daily consumption was missing or invalid before the incident.")
        return incident_result(
            incident=incident,
            plant=plant,
            material=material,
            incident_time=incident_time,
            predicted_warning_date=None,
            lead_time_gained_hours=None,
            missed_signals=missed_signals,
            confidence_level="low",
            calibration_status="UNCALIBRATED",
            cover=None,
        )

    shipments = historical_inbounds(db, context, incident, incident_time)
    if not shipments:
        missed_signals.append("No linked inbound shipments were available before incident.")
    cover = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=snapshot.snapshot_time,
            usable_stock_mt=snapshot.available_to_consume_mt,
            daily_consumption_mt=snapshot.daily_consumption_mt,
            warning_days=threshold.warning_days if threshold else None,
            critical_days=threshold.threshold_days if threshold else None,
            reserve_days=threshold.minimum_buffer_stock_days if threshold else None,
            reserve_quantity_mt=threshold.minimum_buffer_stock_mt if threshold else None,
            supplier_context_complete=all(item.supplier_linked for item in shipments),
            inbounds=tuple(shipments),
        )
    )
    predicted = cover.warning_date
    lead_time = None
    if predicted is None:
        missed_signals.append("OpsDeck did not produce a warning date for this incident.")
    elif ensure_utc(predicted) > incident_time:
        missed_signals.append("Predicted warning date was after the recorded incident.")
    else:
        lead_time = quantize_decimal(
            Decimal(str((incident_time - ensure_utc(predicted)).total_seconds()))
            / Decimal("3600")
        )
    return incident_result(
        incident=incident,
        plant=plant,
        material=material,
        incident_time=incident_time,
        predicted_warning_date=predicted,
        lead_time_gained_hours=lead_time,
        missed_signals=missed_signals,
        confidence_level=confidence_from_score(cover.confidence_score),
        calibration_status=cover.calibration_status,
        cover=cover,
    )


def incident_result(
    *,
    incident: LineStopIncident,
    plant: Plant | None,
    material: Material | None,
    incident_time: datetime,
    predicted_warning_date: datetime | None,
    lead_time_gained_hours: Decimal | None,
    missed_signals: list[str],
    confidence_level: str,
    calibration_status: str,
    cover: TimePhasedCoverResult | None,
) -> HistoricalValidationIncidentResult:
    detection_result = detection_result_for(
        predicted_warning_date=predicted_warning_date,
        incident_time=incident_time,
        lead_time_gained_hours=lead_time_gained_hours,
        confidence_level=confidence_level,
        missed_signals=missed_signals,
    )
    confidence_classification, confidence_rationale = confidence_classification_for(
        confidence_level=confidence_level,
        calibration_status=calibration_status,
        missed_signals=missed_signals,
        cover=cover,
    )
    lead_days = hours_to_days(lead_time_gained_hours)
    detection_signals = detection_signals_for(cover, predicted_warning_date, incident_time)
    detection_chain = detection_chain_for(
        cover=cover,
        predicted_warning_date=predicted_warning_date,
        incident_time=incident_time,
        lead_time_gained_hours=lead_time_gained_hours,
        missed_signals=missed_signals,
    )
    recommended_actions = recommended_actions_for(detection_signals, confidence_classification)
    missed_analysis = missed_analysis_for(
        detection_result=detection_result,
        missed_signals=missed_signals,
        confidence_classification=confidence_classification,
    )
    return HistoricalValidationIncidentResult(
        incident_id=incident.id,
        plant_id=incident.plant_id,
        plant_reference=plant.code if plant else None,
        plant_name=plant.name if plant else f"Plant {incident.plant_id}",
        material_id=incident.material_id,
        material_reference=material.code if material else None,
        material_name=material.name if material else f"Material {incident.material_id}",
        incident_date=incident_time,
        incident_type="LINE_STOP",
        line_stop_duration_hours=quantize_decimal(incident.duration_hours),
        business_impact=None,
        opsdeck_detection_result=detection_result,
        incident_start_date=incident_time,
        earliest_detection_date=(
            ensure_utc(predicted_warning_date) if predicted_warning_date is not None else None
        ),
        warning_lead_time_hours=lead_time_gained_hours,
        warning_lead_time_days=lead_days,
        predicted_warning_date=predicted_warning_date,
        lead_time_gained_hours=lead_time_gained_hours,
        detection_signals=detection_signals,
        detection_chain=detection_chain,
        recommended_actions_replay=recommended_actions,
        missed_signals=missed_signals,
        missed_incident_analysis=missed_analysis,
        confidence_level=confidence_level,
        confidence_classification=confidence_classification,
        confidence_rationale=confidence_rationale,
        calibration_status=calibration_status,
    )


def historical_inbounds(
    db: Session,
    context: RequestContext,
    incident: LineStopIncident,
    incident_time: datetime,
) -> list[TimePhasedInbound]:
    shipments = db.scalars(
        select(Shipment)
        .where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.plant_id == incident.plant_id,
            Shipment.material_id == incident.material_id,
            Shipment.current_eta >= incident_time - timedelta(days=30),
            Shipment.latest_update_at <= incident_time,
        )
        .order_by(Shipment.current_eta.asc())
    )
    return [
        TimePhasedInbound(
            shipment_id=shipment.shipment_id,
            supplier_name=shipment.supplier_name,
            eta=shipment.current_eta,
            raw_quantity_mt=shipment.quantity_mt,
            effective_quantity_mt=shipment.quantity_mt,
            supplier_linked=shipment.supplier_id is not None,
        )
        for shipment in shipments
    ]


def confidence_from_score(score: Decimal) -> str:
    if score >= Decimal("0.80"):
        return "high"
    if score >= Decimal("0.55"):
        return "medium"
    return "low"


def detection_result_for(
    *,
    predicted_warning_date: datetime | None,
    incident_time: datetime,
    lead_time_gained_hours: Decimal | None,
    confidence_level: str,
    missed_signals: list[str],
) -> str:
    if predicted_warning_date is None or ensure_utc(predicted_warning_date) > incident_time:
        return "MISSED"
    if lead_time_gained_hours is None or lead_time_gained_hours <= 0:
        return "PARTIALLY DETECTED"
    if confidence_level == "low" or missed_signals:
        return "PARTIALLY DETECTED"
    return "DETECTED"


def confidence_classification_for(
    *,
    confidence_level: str,
    calibration_status: str,
    missed_signals: list[str],
    cover: TimePhasedCoverResult | None,
) -> tuple[str, list[str]]:
    rationale: list[str] = []
    if cover is None:
        rationale.append("Historical cover could not be reconstructed from available data.")
        return "LOW CONFIDENCE", rationale
    if calibration_status != "CALIBRATED":
        rationale.extend(cover.assumptions_used)
    if missed_signals:
        rationale.extend(missed_signals)
    if confidence_level == "high" and calibration_status == "CALIBRATED" and not missed_signals:
        rationale.append("Inventory history, thresholds, and inbound context were sufficient.")
        return "HIGH CONFIDENCE", rationale
    if confidence_level in {"high", "medium"}:
        rationale.append("Historical reconstruction is usable but contains operational caveats.")
        return "MEDIUM CONFIDENCE", rationale
    rationale.append("Historical data gaps materially reduce confidence.")
    return "LOW CONFIDENCE", rationale


def detection_signals_for(
    cover: TimePhasedCoverResult | None,
    predicted_warning_date: datetime | None,
    incident_time: datetime,
) -> list[str]:
    if (
        cover is None
        or predicted_warning_date is None
        or ensure_utc(predicted_warning_date) > incident_time
    ):
        return []
    signals = ["Days of Cover Breach"]
    if (
        cover.reserve_breach_date is not None
        and ensure_utc(cover.reserve_breach_date) <= incident_time
    ):
        signals.append("Protected Reserve Breach")
    if (
        cover.critical_breach_date is not None
        and ensure_utc(cover.critical_breach_date) <= incident_time
    ):
        signals.append("Critical Cover Breach")
    if cover.interruption_date is not None and ensure_utc(cover.interruption_date) <= incident_time:
        signals.append("Projected Stockout")
    if any(
        item.protection_status in {"LATE_AFTER_RESERVE", "TOO_LATE", "CRITICAL_ON_ARRIVAL"}
        for item in cover.shipment_evaluations
    ):
        signals.append("Inbound Delay Against Cover")
        signals.append("Shipment Degraded")
    if any(not item.protects_reserve_breach for item in cover.shipment_evaluations):
        signals.append("Trusted Inbound Reduction")
    if any("supplier" in reason.lower() for reason in cover.assumptions_used):
        signals.append("Supplier Reliability Weak")
    return sorted(set(signals), key=signals.index)


def detection_chain_for(
    *,
    cover: TimePhasedCoverResult | None,
    predicted_warning_date: datetime | None,
    incident_time: datetime,
    lead_time_gained_hours: Decimal | None,
    missed_signals: list[str],
) -> list[str]:
    if cover is None:
        return missed_signals
    chain = list(cover.reasoning[:4])
    if predicted_warning_date is not None and ensure_utc(predicted_warning_date) <= incident_time:
        chain.append(
            "OpsDeck would have produced the first warning on "
            f"{ensure_utc(predicted_warning_date).date().isoformat()}."
        )
        if lead_time_gained_hours is not None:
            lead_days = hours_to_days(lead_time_gained_hours)
            chain.append(
                "Warning lead time before the recorded incident was "
                f"{lead_days} days."
            )
    for shipment in cover.shipment_evaluations[:3]:
        chain.append(
            f"Inbound {shipment.shipment_id}: {format_label(shipment.protection_status)}. "
            + " ".join(shipment.reasoning[:2])
        )
    if missed_signals:
        chain.append("Caveats: " + " ".join(missed_signals))
    return chain


def recommended_actions_for(
    detection_signals: list[str],
    confidence_classification: str,
) -> list[str]:
    if not detection_signals:
        return [
            "Improve historical inventory, threshold, and inbound data before relying on replay."
        ]
    actions = ["Validate stock position and threshold assumptions"]
    if (
        "Inbound Delay Against Cover" in detection_signals
        or "Shipment Degraded" in detection_signals
    ):
        actions.extend(["Verify inbound shipment status", "Validate ETA", "Expedite transport"])
    if "Supplier Reliability Weak" in detection_signals:
        actions.append("Escalate supplier reliability review")
    if "Protected Reserve Breach" in detection_signals:
        actions.append("Activate reserve material review")
    if "Critical Cover Breach" in detection_signals or "Projected Stockout" in detection_signals:
        actions.extend(["Review substitution options", "Escalate continuity recovery plan"])
    if confidence_classification != "HIGH CONFIDENCE":
        actions.append("Validate missing historical context before executive sign-off")
    return sorted(set(actions), key=actions.index)


def missed_analysis_for(
    *,
    detection_result: str,
    missed_signals: list[str],
    confidence_classification: str,
) -> list[str]:
    if detection_result == "MISSED":
        return missed_signals or ["Signal not modeled from available historical data."]
    if detection_result == "PARTIALLY DETECTED":
        return missed_signals or [f"Detection was limited by {confidence_classification.lower()}."]
    return []


def historical_validation_summary(
    results: list[HistoricalValidationIncidentResult],
) -> HistoricalValidationSummary:
    detected = sum(1 for result in results if result.opsdeck_detection_result == "DETECTED")
    partial = sum(
        1 for result in results if result.opsdeck_detection_result == "PARTIALLY DETECTED"
    )
    missed = sum(1 for result in results if result.opsdeck_detection_result == "MISSED")
    lead_days = [
        result.warning_lead_time_days
        for result in results
        if result.warning_lead_time_days is not None
        and result.opsdeck_detection_result in {"DETECTED", "PARTIALLY DETECTED"}
    ]
    total = len(results)
    detection_rate = (
        quantize_decimal((Decimal(detected) / Decimal(total)) * Decimal("100"))
        if total
        else Decimal("0.00")
    )
    return HistoricalValidationSummary(
        incidents_analyzed=total,
        detected=detected,
        partially_detected=partial,
        missed=missed,
        detection_rate_percent=detection_rate,
        average_warning_lead_time_days=average_decimal(lead_days),
        longest_warning_lead_time_days=max(lead_days) if lead_days else None,
        shortest_warning_lead_time_days=min(lead_days) if lead_days else None,
    )


def historical_validation_markdown(
    results: list[HistoricalValidationIncidentResult],
    summary: HistoricalValidationSummary,
    *,
    tenant_name: str,
) -> str:
    lines = [
        "# Historical Validation Report",
        "",
        f"Generated Date: {datetime.now(UTC).date().isoformat()}",
        f"Tenant: {tenant_name}",
        "",
        "## Executive Summary",
        f"Incidents Analyzed: {summary.incidents_analyzed}",
        f"Detected: {summary.detected}",
        f"Partially Detected: {summary.partially_detected}",
        f"Missed: {summary.missed}",
        f"Detection Rate: {summary.detection_rate_percent}%",
        f"Average Warning Lead Time: {summary.average_warning_lead_time_days or 'N/A'} days",
        "",
        "## Incident Breakdown",
    ]
    for result in results:
        lines.extend(
            [
                "",
                f"### {result.material_name} at {result.plant_name}",
                f"Incident Date: {result.incident_date.date().isoformat()}",
                f"Incident Type: {format_label(result.incident_type)}",
                f"Line Stop Duration: {result.line_stop_duration_hours or 'Unavailable'} hours",
                f"Detection Result: {result.opsdeck_detection_result}",
                f"Warning Lead Time: {result.warning_lead_time_days or 'N/A'} days",
                f"Confidence: {result.confidence_classification}",
                "Detection Evidence:",
                *[
                    f"- {item}"
                    for item in result.detection_signals
                    or ["No modeled detection signal."]
                ],
                "Recommended Actions Replay:",
                *[f"- {item}" for item in result.recommended_actions_replay],
            ]
        )
        if result.missed_incident_analysis:
            lines.extend(
                [
                    "Missed / Caveat Analysis:",
                    *[f"- {item}" for item in result.missed_incident_analysis],
                ]
            )
    return "\n".join(lines)


def average_decimal(values: list[Decimal | None]) -> Decimal | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return quantize_decimal(sum(clean, start=Decimal("0")) / Decimal(len(clean)))


def hours_to_days(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return quantize_decimal(value / Decimal("24"))


def format_label(value: str) -> str:
    return value.replace("_", " ").title()


def serialize_incident(db: Session, incident: LineStopIncident) -> LineStopIncidentOut:
    plant = db.get(Plant, incident.plant_id)
    material = db.get(Material, incident.material_id)
    return LineStopIncidentOut(
        id=incident.id,
        plant_id=incident.plant_id,
        plant_name=plant.name if plant else f"Plant {incident.plant_id}",
        material_id=incident.material_id,
        material_name=material.name if material else f"Material {incident.material_id}",
        stopped_at=ensure_utc(incident.stopped_at),
        duration_hours=quantize_decimal(incident.duration_hours),
        notes=incident.notes,
        created_at=ensure_utc(incident.created_at),
    )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
