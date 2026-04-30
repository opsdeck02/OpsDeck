from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, ExternalDataSource, IngestionJob, MicrosoftDataSource, UploadedFile
from app.modules.exceptions.service import list_exceptions, serialize_exception
from app.modules.shipments.confidence import assess_freshness, ensure_utc
from app.modules.shipments.movement import list_inland_monitoring, list_port_monitoring
from app.modules.shipments.service import list_shipments
from app.modules.stock.service import calculate_stock_cover_summary
from app.schemas.context import RequestContext
from app.schemas.dashboard import (
    AttentionItem,
    AutomatedDataFreshness,
    DashboardFreshness,
    ExecutiveDashboardResponse,
    ExecutiveExceptionItem,
    ExecutiveKpis,
    ExecutiveMovementItem,
    ExecutiveSupplierPerformanceSummary,
    ExecutiveSupplierSummaryItem,
    LastSyncSummary,
    ExecutiveRiskItem,
    PilotReadinessCheck,
    PilotReadinessCounts,
    PilotReadinessResponse,
    SupplierPerformanceItem,
)
from app.modules.tenants.service import classify_data_freshness
from app.modules.suppliers.service import performance_summary


def build_executive_dashboard(
    db: Session,
    context: RequestContext,
) -> ExecutiveDashboardResponse:
    stock_summary = calculate_stock_cover_summary(db, context)
    exception_cases, _ = list_exceptions(db, context)
    serialized_exceptions = [serialize_exception(db, context, item) for item in exception_cases]
    shipment_items = list_shipments(db, context)
    port_items = list_port_monitoring(db, context)
    inland_items = list_inland_monitoring(db, context)

    top_risks = build_top_risks(stock_summary.rows, shipment_items)
    critical_open = [
        executive_exception_item(item)
        for item in serialized_exceptions
        if item["severity"] == "critical" and item["status"] in {"open", "in_progress"}
    ][:5]
    unassigned = [
        executive_exception_item(item)
        for item in serialized_exceptions
        if item["status"] in {"open", "in_progress"} and item["current_owner"] is None
    ][:5]
    recent = [
        executive_exception_item(item)
        for item in sorted(
            serialized_exceptions,
            key=lambda exc: exc["updated_at"],
            reverse=True,
        )
        if item["status"] in {"open", "in_progress", "resolved"}
    ][:5]

    movement_snapshot = build_movement_snapshot(shipment_items, port_items, inland_items)
    supplier_performance = build_supplier_performance(shipment_items, port_items, inland_items)
    supplier_summary = performance_summary(db, context)
    needs_attention = build_needs_attention(top_risks, serialized_exceptions, movement_snapshot)
    automated_freshness = build_automated_data_freshness(db, context)

    return ExecutiveDashboardResponse(
        tenant=context.tenant_slug,
        kpis=ExecutiveKpis(
            tracked_combinations=stock_summary.total_combinations,
            critical_risks=stock_summary.critical_risks,
            warning_risks=stock_summary.warnings,
            open_exceptions=sum(
                1 for item in serialized_exceptions if item["status"] in {"open", "in_progress"}
            ),
            unassigned_exceptions=sum(
                1
                for item in serialized_exceptions
                if item["status"] in {"open", "in_progress"} and item["current_owner"] is None
            ),
            total_estimated_value_at_risk=sum_critical_value_at_risk(stock_summary.rows),
        ),
        automated_data_freshness=automated_freshness,
        stock_freshness=freshness_for_stock(stock_summary.rows),
        exception_freshness=freshness_for_exceptions(serialized_exceptions),
        movement_freshness=freshness_for_movements(port_items, inland_items, shipment_items),
        top_risks=top_risks,
        critical_open_exceptions=critical_open,
        unassigned_exceptions=unassigned,
        recently_updated_exceptions=recent,
        stale_movement_shipments=movement_snapshot["stale"][:5],
        low_confidence_shipments=movement_snapshot["low_confidence"][:5],
        likely_delayed_shipments=movement_snapshot["delayed"][:5],
        supplier_performance=supplier_performance[:10],
        supplier_performance_summary=ExecutiveSupplierPerformanceSummary(
            top_suppliers=[
                executive_supplier_summary_item(item)
                for item in supplier_summary.top_suppliers[:3]
            ],
            bottom_suppliers=[
                executive_supplier_summary_item(item)
                for item in supplier_summary.bottom_suppliers[:3]
            ],
            grade_d_count=supplier_summary.grade_d_count,
            high_risk_supplier_count=supplier_summary.high_risk_supplier_count,
        ),
        needs_attention=needs_attention[:5],
    )


def build_automated_data_freshness(
    db: Session,
    context: RequestContext,
) -> AutomatedDataFreshness | None:
    external_sources = list(
        db.scalars(
            select(ExternalDataSource)
            .where(
                ExternalDataSource.tenant_id == context.tenant_id,
                ExternalDataSource.is_active.is_(True),
            )
        )
    )
    microsoft_sources = list(
        db.scalars(
            select(MicrosoftDataSource).where(
                MicrosoftDataSource.tenant_id == context.tenant_id,
                MicrosoftDataSource.is_active.is_(True),
            )
        )
    )
    sources = [
        {
            "last_synced_at": source.last_synced_at,
            "created_at": source.created_at,
            "sync_status": source.last_sync_status,
            "sync_frequency_minutes": source.sync_frequency_minutes,
            "new_critical_risks_count": source.new_critical_risks_count,
            "resolved_risks_count": source.resolved_risks_count,
            "newly_breached_actions_count": source.newly_breached_actions_count,
            "source_type": "external_url",
            "source_key": f"external:{source.dataset_type}:{source.source_name}",
        }
        for source in external_sources
    ] + [
        {
            "last_synced_at": source.last_successful_sync_at,
            "created_at": source.created_at,
            "sync_status": source.sync_status,
            "sync_frequency_minutes": source.sync_frequency_minutes,
            "new_critical_risks_count": 0,
            "resolved_risks_count": 0,
            "newly_breached_actions_count": 0,
            "source_type": "microsoft_graph",
            "source_key": f"microsoft:{source.file_type}:{source.display_name or source.item_id}",
        }
        for source in microsoft_sources
    ]
    sources = latest_sources_by_key(sources)
    if not sources:
        return None

    latest_source = max(
        sources,
        key=lambda source: source["last_synced_at"] or source["created_at"],
    )
    freshness_states = [
        classify_data_freshness(source["last_synced_at"], source["sync_frequency_minutes"])
        for source in sources
    ]
    status_priority = {"fresh": 0, "aging": 1, "stale": 2}
    worst_status, worst_age = max(
        freshness_states,
        key=lambda item: (status_priority[item[0]], item[1] or -1),
    )
    return AutomatedDataFreshness(
        last_sync_summary=LastSyncSummary(
            last_synced_at=latest_source["last_synced_at"],
            last_sync_status=latest_source["sync_status"],
            new_critical_risks_count=latest_source["new_critical_risks_count"],
            resolved_risks_count=latest_source["resolved_risks_count"],
            newly_breached_actions_count=latest_source["newly_breached_actions_count"],
            source_type=latest_source["source_type"],
        ),
        data_freshness_status=worst_status,
        data_freshness_age_minutes=worst_age,
    )


def latest_sources_by_key(sources: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for source in sources:
        key = source["source_key"]
        existing = latest.get(key)
        source_time = source["last_synced_at"] or source["created_at"]
        existing_time = (existing["last_synced_at"] or existing["created_at"]) if existing else None
        if existing is None or source_time > existing_time:
            latest[key] = source
    return list(latest.values())


def build_pilot_readiness(
    db: Session,
    context: RequestContext,
) -> PilotReadinessResponse:
    executive = build_executive_dashboard(db, context)
    uploaded_files = list(
        db.scalars(
            select(UploadedFile)
            .where(UploadedFile.tenant_id == context.tenant_id)
            .order_by(UploadedFile.created_at.desc())
        )
    )
    ingestion_jobs = list(
        db.scalars(
            select(IngestionJob)
            .where(IngestionJob.tenant_id == context.tenant_id)
            .order_by(IngestionJob.created_at.desc())
        )
    )
    exception_eval_audit = db.scalar(
        select(AuditLog.id).where(
            AuditLog.tenant_id == context.tenant_id,
            AuditLog.action == "exception.evaluation_triggered",
        )
    )
    stale_signals = (
        len(executive.stale_movement_shipments)
        + (1 if executive.stock_freshness.freshness_label == "stale" else 0)
        + (1 if executive.exception_freshness.freshness_label == "stale" else 0)
    )
    checks = [
        PilotReadinessCheck(
            key="onboarding_uploads",
            label="Onboarding uploads received",
            ready=bool(uploaded_files),
            detail=(
                f"{len(uploaded_files)} uploaded files tracked."
                if uploaded_files
                else "Upload shipment, stock, and threshold files to start the tenant."
            ),
            last_updated_at=uploaded_files[0].created_at if uploaded_files else None,
        ),
        PilotReadinessCheck(
            key="stock_cover_results",
            label="Stock-cover results available",
            ready=executive.kpis.tracked_combinations > 0,
            detail=(
                f"{executive.kpis.tracked_combinations} plant/material combinations calculated."
                if executive.kpis.tracked_combinations > 0
                else "No stock-cover combinations are available yet."
            ),
            last_updated_at=executive.stock_freshness.last_updated_at,
        ),
        PilotReadinessCheck(
            key="exception_evaluation",
            label="Exception rules evaluated",
            ready=exception_eval_audit is not None,
            detail=(
                f"{executive.kpis.open_exceptions} open exceptions currently tracked."
                if exception_eval_audit is not None
                else "Run manual exception evaluation after onboarding data is loaded."
            ),
            last_updated_at=executive.exception_freshness.last_updated_at,
        ),
        PilotReadinessCheck(
            key="executive_dashboard",
            label="Executive dashboard usable",
            ready=executive_dashboard_usable(executive),
            detail=(
                "Executive dashboard has enough stock, movement, or exception data for review."
                if executive_dashboard_usable(executive)
                else "Executive dashboard is still waiting on usable onboarding signals."
            ),
            last_updated_at=latest_dashboard_timestamp(executive),
        ),
        PilotReadinessCheck(
            key="freshness_watch",
            label="Key data freshness not stale",
            ready=not has_stale_freshness(executive),
            detail=(
                "Stock, movement, and exception sections are still fresh enough for pilot use."
                if not has_stale_freshness(executive)
                else "One or more sections are stale and should be refreshed before go-live review."
            ),
            last_updated_at=latest_dashboard_timestamp(executive),
        ),
    ]

    return PilotReadinessResponse(
        tenant=context.tenant_slug,
        counts=PilotReadinessCounts(
            uploaded_files=len(uploaded_files),
            ingestion_jobs=len(ingestion_jobs),
            stock_cover_rows=executive.kpis.tracked_combinations,
            open_exceptions=executive.kpis.open_exceptions,
            stale_signals=stale_signals,
        ),
        last_upload_at=uploaded_files[0].created_at if uploaded_files else None,
        last_stock_update_at=executive.stock_freshness.last_updated_at,
        last_exception_update_at=executive.exception_freshness.last_updated_at,
        last_movement_update_at=executive.movement_freshness.last_updated_at,
        checks=checks,
    )


def build_top_risks(rows: list, shipments: list) -> list[ExecutiveRiskItem]:
    filtered = [
        row
        for row in rows
        if row.calculation.status in {"critical", "warning"}
    ]
    filtered.sort(
        key=lambda row: (
            0 if row.calculation.status == "critical" else 1,
            (
                row.calculation.days_of_cover
                if row.calculation.days_of_cover is not None
                else Decimal("9999")
            ),
        )
    )
    return [
        ExecutiveRiskItem(
            plant_id=row.plant_id,
            plant_name=row.plant_name,
            material_id=row.material_id,
            material_name=row.material_name,
            days_of_cover=row.calculation.days_of_cover,
            threshold_days=row.calculation.threshold_days,
            status=row.calculation.status,
            confidence=row.calculation.confidence_level,
            current_stock_mt=row.calculation.current_stock_mt,
            usable_stock_mt=row.calculation.total_considered_mt,
            blocked_stock_mt=blocked_stock_for(
                row.calculation.current_stock_mt,
                row.calculation.total_considered_mt,
            ),
            next_inbound_eta=next_inbound_eta_for(row, shipments),
            raw_inbound_pipeline_mt=row.calculation.raw_inbound_pipeline_mt,
            effective_inbound_pipeline_mt=row.calculation.effective_inbound_pipeline_mt,
            inbound_protection_indicator=protection_indicator(
                row.calculation.raw_inbound_pipeline_mt,
                row.calculation.effective_inbound_pipeline_mt,
            ),
            risk_hours_remaining=row.calculation.risk_hours_remaining,
            estimated_production_exposure_mt=row.calculation.estimated_production_exposure_mt,
            estimated_value_at_risk=row.calculation.estimated_value_at_risk,
            value_per_mt_used=row.calculation.value_per_mt_used,
            criticality_multiplier_used=row.calculation.criticality_multiplier_used,
            urgency_band=row.calculation.urgency_band,
            recommended_action_code=row.calculation.recommended_action_code,
            recommended_action_text=row.calculation.recommended_action_text,
            owner_role_recommended=row.calculation.owner_role_recommended,
            action_deadline_hours=row.calculation.action_deadline_hours,
            action_priority=row.calculation.action_priority,
            action_status=row.calculation.action_status,
            action_sla_breach=row.calculation.action_sla_breach,
            action_age_hours=row.calculation.action_age_hours,
        )
        for row in filtered[:10]
    ]


def blocked_stock_for(current_stock: Decimal | None, usable_stock: Decimal | None) -> Decimal | None:
    if current_stock is None or usable_stock is None:
        return None
    return max(current_stock - usable_stock, Decimal("0"))


def next_inbound_eta_for(row, shipments: list):
    active_states = {"planned", "on_water", "at_port", "discharging", "in_transit", "delayed"}
    etas = [
        shipment.current_eta
        for shipment in shipments
        if shipment.plant_id == row.plant_id
        and shipment.material_id == row.material_id
        and shipment.shipment_state in active_states
        and shipment.current_eta is not None
    ]
    return min(etas) if etas else None


def sum_critical_value_at_risk(rows: list) -> Decimal:
    total = Decimal("0")
    for row in rows:
        if row.calculation.status != "critical":
            continue
        total += row.calculation.estimated_value_at_risk or Decimal("0")
    return total


def protection_indicator(raw_inbound: Decimal, effective_inbound: Decimal) -> str:
    if raw_inbound <= 0:
        return "no_pipeline"
    ratio = effective_inbound / raw_inbound
    if ratio >= Decimal("0.75"):
        return "strong"
    if ratio >= Decimal("0.40"):
        return "reduced"
    return "weak"


def executive_exception_item(item: dict) -> ExecutiveExceptionItem:
    return ExecutiveExceptionItem(
        id=item["id"],
        title=item["title"],
        severity=item["severity"],
        status=item["status"],
        owner_name=item["current_owner"]["full_name"] if item["current_owner"] else None,
        updated_at=item["updated_at"],
        recommended_next_step=item["recommended_next_step"],
    )


def build_movement_snapshot(
    shipment_items: list,
    port_items: list,
    inland_items: list,
) -> dict[str, list[ExecutiveMovementItem]]:
    by_shipment: dict[str, ExecutiveMovementItem] = {}
    stale: list[ExecutiveMovementItem] = []
    low_confidence: list[ExecutiveMovementItem] = []
    delayed: list[ExecutiveMovementItem] = []

    for item in shipment_items:
        if item.confidence == "low":
            low_confidence.append(
                ExecutiveMovementItem(
                    shipment_id=item.shipment_id,
                    plant_name=item.plant_name,
                    material_name=item.material_name,
                    confidence=item.confidence,
                    freshness_label=assess_freshness(item.last_update_at).freshness_label,
                    issue_label="Low shipment confidence",
                )
            )

    for item in port_items:
        if item.stale_record:
            stale_item = ExecutiveMovementItem(
                shipment_id=item.shipment_id,
                plant_name=item.plant_name,
                material_name=item.material_name,
                confidence=item.confidence,
                freshness_label=item.freshness.freshness_label,
                issue_label="Stale port movement data",
            )
            by_shipment.setdefault(item.shipment_id, stale_item)
        if item.likely_port_delay:
            delayed.append(
                ExecutiveMovementItem(
                    shipment_id=item.shipment_id,
                    plant_name=item.plant_name,
                    material_name=item.material_name,
                    confidence=item.confidence,
                    freshness_label=item.freshness.freshness_label,
                    issue_label="Likely port delay",
                )
            )

    for item in inland_items:
        if item.stale_record:
            stale_item = ExecutiveMovementItem(
                shipment_id=item.shipment_id,
                plant_name=item.plant_name,
                material_name=item.material_name,
                confidence=item.confidence,
                freshness_label=item.freshness.freshness_label,
                issue_label="Stale inland movement data",
            )
            by_shipment.setdefault(item.shipment_id, stale_item)
        if item.inland_delay_flag:
            delayed.append(
                ExecutiveMovementItem(
                    shipment_id=item.shipment_id,
                    plant_name=item.plant_name,
                    material_name=item.material_name,
                    confidence=item.confidence,
                    freshness_label=item.freshness.freshness_label,
                    issue_label="Likely inland delay",
                )
            )

    stale.extend(by_shipment.values())
    return {"stale": stale, "low_confidence": low_confidence, "delayed": delayed}


def build_supplier_performance(
    shipment_items: list,
    port_items: list,
    inland_items: list,
) -> list[SupplierPerformanceItem]:
    supplier_rows: dict[str, dict[str, Decimal | int | set[str]]] = {}
    stale_ids = {
        item.shipment_id
        for item in [*port_items, *inland_items]
        if item.stale_record
    }
    delayed_ids = {
        item.shipment_id
        for item in port_items
        if item.likely_port_delay
    }
    delayed_ids.update(
        item.shipment_id
        for item in inland_items
        if item.inland_delay_flag
    )

    for item in shipment_items:
        supplier = getattr(item, "supplier_name", None) or "Unknown supplier"
        row = supplier_rows.setdefault(
            supplier,
            {
                "total": 0,
                "on_time": 0,
                "active": 0,
                "risk": 0,
            },
        )
        row["total"] = int(row["total"]) + 1
        planned_eta = ensure_utc(item.planned_eta)
        current_eta = ensure_utc(item.current_eta)
        eta_delta_hours = abs(
            Decimal(str((current_eta - planned_eta).total_seconds())) / Decimal("3600")
        )
        if eta_delta_hours <= Decimal("24"):
            row["on_time"] = int(row["on_time"]) + 1

        if item.shipment_state not in {"delivered", "cancelled"}:
            row["active"] = int(row["active"]) + 1
            has_risk_signal = (
                item.confidence == "low"
                or assess_freshness(item.last_update_at).freshness_label == "stale"
                or item.shipment_id in stale_ids
                or item.shipment_id in delayed_ids
            )
            if has_risk_signal:
                row["risk"] = int(row["risk"]) + 1

    results = [
        SupplierPerformanceItem(
            supplier_name=supplier,
            total_shipments=int(row["total"]),
            on_time_shipments=int(row["on_time"]),
            on_time_reliability_pct=percentage(int(row["on_time"]), int(row["total"])),
            active_shipments=int(row["active"]),
            active_shipments_with_risk_signal=int(row["risk"]),
            risk_signal_pct=percentage(int(row["risk"]), int(row["active"])),
        )
        for supplier, row in supplier_rows.items()
    ]
    results.sort(
        key=lambda item: (
            -item.risk_signal_pct,
            item.on_time_reliability_pct,
            item.supplier_name.lower(),
        )
    )
    return results


def executive_supplier_summary_item(item) -> ExecutiveSupplierSummaryItem:
    return ExecutiveSupplierSummaryItem(
        supplier_id=item.id,
        supplier_name=item.name,
        reliability_grade=item.performance.reliability_grade,
        on_time_reliability_pct=item.performance.on_time_reliability_pct,
        risk_signal_pct=item.performance.risk_signal_pct,
        active_shipments=item.performance.active_shipments,
    )


def build_needs_attention(
    top_risks: list[ExecutiveRiskItem],
    exceptions: list[dict],
    movement_snapshot: dict[str, list[ExecutiveMovementItem]],
) -> list[AttentionItem]:
    items: list[AttentionItem] = []

    critical_open = [
        item
        for item in exceptions
        if item["severity"] == "critical" and item["status"] in {"open", "in_progress"}
    ]
    critical_open.sort(
        key=lambda item: (0 if item["current_owner"] is None else 1, item["updated_at"])
    )
    for item in critical_open[:2]:
        if item["action_status"] == "completed":
            continue
        items.append(
            AttentionItem(
                kind="exception",
                description=item["title"],
                linked_label=item["linked_shipment"]["label"] if item["linked_shipment"] else (
                    f'{item["linked_plant"]["label"]} / {item["linked_material"]["label"]}'
                    if item["linked_plant"] and item["linked_material"]
                    else "Exception"
                ),
                href=f'/dashboard/exceptions/{item["id"]}',
                current_owner=(
                    item["current_owner"]["full_name"]
                    if item["current_owner"]
                    else "Unassigned"
                ),
                recommended_next_step=(
                    item["recommended_next_step"]
                    or "Review the exception and assign an owner."
                ),
                owner_role_recommended=(
                    item["current_owner"]["role"]
                    if item["current_owner"] and item["current_owner"]["role"]
                    else "tenant_admin"
                ),
                action_deadline_hours=12,
                action_priority="high",
                action_status=item["action_status"],
                action_sla_breach=item["action_sla_breach"],
                action_age_hours=item["action_age_hours"],
            )
        )

    for risk in [item for item in top_risks if item.status == "critical" and item.action_status != "completed"][:2]:
        matched_exception = matching_exception_for_risk(risk, exceptions)
        items.append(
            AttentionItem(
                kind="stock_risk",
                description=(
                    f"{risk.plant_name} / {risk.material_name} is below cover threshold "
                    f"at {format_decimal(risk.days_of_cover)} days."
                ),
                linked_label=f"{risk.plant_name} / {risk.material_name}",
                href=f"/dashboard/stock-cover/{risk.plant_id}/{risk.material_id}",
                current_owner=(
                    matched_exception["current_owner"]["full_name"]
                    if matched_exception and matched_exception["current_owner"]
                    else "Unassigned"
                ),
                recommended_next_step=(
                    risk.recommended_action_text
                    or "Validate stock position and confirm inbound recovery actions."
                ),
                owner_role_recommended=risk.owner_role_recommended,
                action_deadline_hours=risk.action_deadline_hours,
                action_priority=risk.action_priority,
                action_status=risk.action_status,
                action_sla_breach=risk.action_sla_breach,
                action_age_hours=risk.action_age_hours,
            )
        )

    for item in movement_snapshot["delayed"][:1]:
        items.append(
            AttentionItem(
                kind="shipment",
                description=item.issue_label,
                linked_label=item.shipment_id,
                href=f"/dashboard/shipments/{item.shipment_id}",
                current_owner="Unassigned",
                recommended_next_step="Review movement status and refresh ETA with logistics.",
                owner_role_recommended="logistics_user",
                action_deadline_hours=12,
                action_priority="high",
                action_status="pending",
                action_sla_breach=False,
                action_age_hours=Decimal("0.00"),
            )
        )

    items.sort(key=attention_sort_key)
    return items


def matching_exception_for_risk(risk: ExecutiveRiskItem, exceptions: list[dict]) -> dict | None:
    active = [
        item
        for item in exceptions
        if item["status"] in {"open", "in_progress"}
        and item["linked_plant"]
        and item["linked_material"]
        and item["linked_plant"]["id"] == risk.plant_id
        and item["linked_material"]["id"] == risk.material_id
    ]
    active.sort(key=lambda item: (0 if item["current_owner"] else 1, item["updated_at"]))
    return active[0] if active else None


def attention_sort_key(item: AttentionItem) -> tuple[int, int, int]:
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3, None: 4}
    status_order = {"pending": 0, "in_progress": 1, "completed": 2, None: 3}
    return (
        0 if item.action_sla_breach else 1,
        priority_order.get(item.action_priority, 4),
        status_order.get(item.action_status, 3),
    )


def freshness_for_stock(rows: list) -> DashboardFreshness:
    latest = max(
        (row.latest_snapshot_time for row in rows if row.latest_snapshot_time),
        default=None,
    )
    assessment = assess_freshness(latest)
    return DashboardFreshness(
        last_updated_at=assessment.last_updated_at,
        freshness_label=assessment.freshness_label,
    )


def freshness_for_exceptions(items: list[dict]) -> DashboardFreshness:
    latest = max((item["updated_at"] for item in items), default=None)
    assessment = assess_freshness(latest)
    return DashboardFreshness(
        last_updated_at=assessment.last_updated_at,
        freshness_label=assessment.freshness_label,
    )


def freshness_for_movements(
    port_items: list,
    inland_items: list,
    shipment_items: list,
) -> DashboardFreshness:
    timestamps = [item.last_update_at for item in shipment_items]
    timestamps.extend(
        item.freshness.last_updated_at
        for item in port_items
        if item.freshness.last_updated_at is not None
    )
    timestamps.extend(
        item.freshness.last_updated_at
        for item in inland_items
        if item.freshness.last_updated_at is not None
    )
    latest = max((ensure_utc(ts) for ts in timestamps if ts is not None), default=None)
    assessment = assess_freshness(latest)
    return DashboardFreshness(
        last_updated_at=assessment.last_updated_at,
        freshness_label=assessment.freshness_label,
    )


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{value.quantize(Decimal('0.01'))}"


def percentage(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return ((Decimal(numerator) / Decimal(denominator)) * Decimal("100")).quantize(
        Decimal("0.01")
    )


def latest_dashboard_timestamp(executive: ExecutiveDashboardResponse):
    timestamps = [
        executive.stock_freshness.last_updated_at,
        executive.exception_freshness.last_updated_at,
        executive.movement_freshness.last_updated_at,
    ]
    return max((timestamp for timestamp in timestamps if timestamp is not None), default=None)


def executive_dashboard_usable(executive: ExecutiveDashboardResponse) -> bool:
    return any(
        [
            executive.kpis.tracked_combinations > 0,
            executive.kpis.open_exceptions > 0,
            bool(executive.top_risks),
            bool(executive.stale_movement_shipments),
            bool(executive.low_confidence_shipments),
            bool(executive.likely_delayed_shipments),
        ]
    )


def has_stale_freshness(executive: ExecutiveDashboardResponse) -> bool:
    return any(
        freshness.freshness_label == "stale"
        for freshness in (
            executive.stock_freshness,
            executive.exception_freshness,
            executive.movement_freshness,
        )
    )
