from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    ExceptionCase,
    ExceptionComment,
    Material,
    Plant,
    Shipment,
    TenantMembership,
    User,
)
from app.models.enums import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.modules.shipments.movement import (
    build_context as build_movement_context,
)
from app.modules.shipments.movement import (
    build_inland_summary,
)
from app.modules.shipments.service import build_shipment_item, shipment_confidence_reasons
from app.modules.stock.service import build_stock_cover_rows
from app.schemas.context import RequestContext

TRIGGER_PREFIX = "[trigger_source:"
ACTIVE_EXCEPTION_STATUSES = {
    ExceptionStatus.OPEN,
    ExceptionStatus.ACKNOWLEDGED,
    ExceptionStatus.IN_PROGRESS,
}
RECENTLY_RESOLVED_WINDOW = timedelta(days=7)
ETA_DELAY_THRESHOLD_HOURS = 24
VALID_ACTION_STATUSES = {"pending", "in_progress", "completed"}

API_STATUS_MAP = {
    "open": ExceptionStatus.OPEN,
    "in_progress": ExceptionStatus.IN_PROGRESS,
    "resolved": ExceptionStatus.RESOLVED,
    "closed": ExceptionStatus.DISMISSED,
}

TYPE_LABELS = {
    "stock_cover_critical": "stock_cover_critical",
    "stock_cover_warning": "stock_cover_warning",
    "shipment_eta_delay": "shipment_eta_delay",
    "shipment_stale_update": "shipment_stale_update",
    "inland_delay_risk": "inland_delay_risk",
}
VALID_TRIGGER_TYPES = set(TYPE_LABELS.values())
AUTO_RESOLVED_STATUSES = {ExceptionStatus.RESOLVED, ExceptionStatus.DISMISSED}
MANUAL_SYSTEM_STATUS_FLOW = {ExceptionStatus.OPEN, ExceptionStatus.IN_PROGRESS}
SYSTEM_CONTROLLED_RESOLUTION_MESSAGE = (
    "System-generated exceptions can only be resolved by fresh data recomputation."
)


@dataclass
class ExceptionCandidate:
    trigger_source: str
    type: ExceptionType
    severity: ExceptionSeverity
    title: str
    summary: str
    linked_shipment_id: int | None = None
    linked_plant_id: int | None = None
    linked_material_id: int | None = None
    due_at: datetime | None = None
    next_action: str | None = None


def list_exceptions(
    db: Session,
    context: RequestContext,
    *,
    status: str | None = None,
    severity: str | None = None,
    type: str | None = None,
    plant_id: int | None = None,
    material_id: int | None = None,
    shipment_id: str | None = None,
    owner_user_id: int | None = None,
    unassigned_only: bool = False,
) -> tuple[list[ExceptionCase], int]:
    query = select(ExceptionCase).where(ExceptionCase.tenant_id == context.tenant_id)
    if status:
        mapped = API_STATUS_MAP.get(status)
        if mapped:
            query = query.where(ExceptionCase.status == mapped)
    if severity:
        query = query.where(ExceptionCase.severity == ExceptionSeverity(severity))
    if type:
        query = query.where(ExceptionCase.summary.like(f"{TRIGGER_PREFIX}{type}]%"))
    if plant_id is not None:
        query = query.where(ExceptionCase.linked_plant_id == plant_id)
    if material_id is not None:
        query = query.where(ExceptionCase.linked_material_id == material_id)
    if owner_user_id is not None:
        query = query.where(ExceptionCase.owner_user_id == owner_user_id)
    if unassigned_only:
        query = query.where(ExceptionCase.owner_user_id.is_(None))

    if shipment_id:
        shipment = db.scalar(
            select(Shipment.id).where(
                Shipment.tenant_id == context.tenant_id,
                Shipment.shipment_id == shipment_id,
            )
        )
        if shipment is None:
            return [], 0
        query = query.where(ExceptionCase.linked_shipment_id == shipment)

    items = list(
        db.scalars(
            query.order_by(
                ExceptionCase.triggered_at.desc(),
                ExceptionCase.updated_at.desc(),
            )
        )
    )
    open_after = count_open_exceptions(items)
    return items, open_after


def get_exception_detail(
    db: Session,
    context: RequestContext,
    exception_id: int,
) -> ExceptionCase | None:
    return db.scalar(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id == context.tenant_id,
            ExceptionCase.id == exception_id,
        )
    )


def assign_exception_owner(
    db: Session,
    context: RequestContext,
    exception_case: ExceptionCase,
    owner_user_id: int | None,
) -> ExceptionCase:
    if owner_user_id is None:
        exception_case.owner_user_id = None
    else:
        membership = db.scalar(
            select(TenantMembership)
            .where(
                TenantMembership.tenant_id == context.tenant_id,
                TenantMembership.user_id == owner_user_id,
                TenantMembership.is_active.is_(True),
            )
        )
        if membership is None:
            raise ValueError("Selected owner is not an active tenant member")
        exception_case.owner_user_id = owner_user_id

    create_audit_log(
        db,
        context,
        action="exception.owner_updated",
        entity_id=str(exception_case.id),
        metadata={"owner_user_id": owner_user_id},
    )
    db.commit()
    db.refresh(exception_case)
    return exception_case


def update_exception_status(
    db: Session,
    context: RequestContext,
    exception_case: ExceptionCase,
    status: str,
) -> ExceptionCase:
    mapped = API_STATUS_MAP.get(status)
    if mapped is None:
        raise ValueError("Unsupported exception status")
    if is_system_generated_exception(exception_case) and mapped in AUTO_RESOLVED_STATUSES:
        raise ValueError(SYSTEM_CONTROLLED_RESOLUTION_MESSAGE)

    exception_case.status = mapped
    create_audit_log(
        db,
        context,
        action="exception.status_updated",
        entity_id=str(exception_case.id),
        metadata={"status": status},
    )
    db.commit()
    db.refresh(exception_case)
    return exception_case


def update_exception_action_status(
    db: Session,
    context: RequestContext,
    exception_case: ExceptionCase,
    action_status: str,
) -> ExceptionCase:
    if action_status not in VALID_ACTION_STATUSES:
        raise ValueError("Unsupported action status")

    now = datetime.now(UTC)
    exception_case.action_status = action_status
    if action_status == "pending":
        exception_case.action_started_at = None
        exception_case.action_completed_at = None
    elif action_status == "in_progress":
        exception_case.action_started_at = exception_case.action_started_at or now
        exception_case.action_completed_at = None
    else:
        exception_case.action_started_at = exception_case.action_started_at or exception_case.triggered_at
        exception_case.action_completed_at = now

    create_audit_log(
        db,
        context,
        action="exception.action_updated",
        entity_id=str(exception_case.id),
        metadata={"action_status": action_status},
    )
    db.commit()
    db.refresh(exception_case)
    return exception_case


def add_exception_comment(
    db: Session,
    context: RequestContext,
    exception_case: ExceptionCase,
    comment: str,
) -> ExceptionComment:
    record = ExceptionComment(
        tenant_id=context.tenant_id,
        exception_case_id=exception_case.id,
        author_user_id=context.user_id,
        comment=comment.strip(),
    )
    db.add(record)
    create_audit_log(
        db,
        context,
        action="exception.comment_added",
        entity_id=str(exception_case.id),
        metadata={"comment_length": len(record.comment)},
    )
    db.commit()
    db.refresh(record)
    return record


def evaluate_exceptions(
    db: Session,
    context: RequestContext,
) -> tuple[int, int, int, int]:
    create_audit_log(
        db,
        context,
        action="exception.evaluation_triggered",
        entity_type="exception_evaluation",
        entity_id=context.tenant_slug,
        metadata={"tenant_id": context.tenant_id},
    )
    candidates = build_candidates(db, context)
    active_cases = list(
        db.scalars(
            select(ExceptionCase).where(
                ExceptionCase.tenant_id == context.tenant_id,
                ExceptionCase.status.in_(ACTIVE_EXCEPTION_STATUSES),
            )
        )
    )
    matched_ids: set[int] = set()
    created = 0
    updated = 0

    for candidate in candidates:
        existing = find_matching_exception(active_cases, candidate)
        if existing is None:
            record = ExceptionCase(
                tenant_id=context.tenant_id,
                type=candidate.type,
                severity=candidate.severity,
                status=ExceptionStatus.OPEN,
                title=candidate.title,
                summary=encode_summary(candidate.trigger_source, candidate.summary),
                linked_shipment_id=candidate.linked_shipment_id,
                linked_plant_id=candidate.linked_plant_id,
                linked_material_id=candidate.linked_material_id,
                triggered_at=datetime.now(UTC),
                due_at=candidate.due_at,
                next_action=candidate.next_action,
                action_status="pending",
                action_started_at=None,
                action_completed_at=None,
            )
            db.add(record)
            db.flush()
            active_cases.append(record)
            matched_ids.add(record.id)
            created += 1
            create_audit_log(
                db,
                context,
                action="exception.created",
                entity_id=str(record.id),
                metadata={"trigger_source": candidate.trigger_source},
            )
            continue

        matched_ids.add(existing.id)
        changed = False
        if existing.severity != candidate.severity:
            existing.severity = candidate.severity
            changed = True
        if existing.title != candidate.title:
            existing.title = candidate.title
            changed = True
        encoded_summary = encode_summary(candidate.trigger_source, candidate.summary)
        if existing.summary != encoded_summary:
            existing.summary = encoded_summary
            changed = True
        if existing.due_at != candidate.due_at:
            existing.due_at = candidate.due_at
            changed = True
        if existing.next_action != candidate.next_action:
            existing.next_action = candidate.next_action
            changed = True
        if not existing.action_status:
            existing.action_status = "pending"
            changed = True
        if changed:
            updated += 1
            create_audit_log(
                db,
                context,
                action="exception.updated",
                entity_id=str(existing.id),
                metadata={"trigger_source": candidate.trigger_source},
            )

    resolved = 0
    for record in active_cases:
        if record.id in matched_ids:
            continue
        trigger_source = extract_trigger_source(record.summary)
        if trigger_source not in VALID_TRIGGER_TYPES:
            continue
        record.status = ExceptionStatus.RESOLVED
        resolved += 1
        create_audit_log(
            db,
            context,
            action="exception.resolved",
            entity_id=str(record.id),
            metadata={"trigger_source": trigger_source},
        )

    db.commit()
    open_after = count_open_exceptions(
        list_exceptions(db, context)[0]
    )
    return created, updated, resolved, open_after


def build_candidates(db: Session, context: RequestContext) -> list[ExceptionCandidate]:
    candidates: list[ExceptionCandidate] = []
    candidates.extend(stock_cover_candidates(db, context))
    candidates.extend(shipment_signal_candidates(db, context))
    return candidates


def stock_cover_candidates(db: Session, context: RequestContext) -> list[ExceptionCandidate]:
    now = datetime.now(UTC)
    candidates: list[ExceptionCandidate] = []
    for row in build_stock_cover_rows(db, context):
        status = row.calculation.status
        if status not in {"critical", "warning"}:
            continue

        trigger_source = (
            "stock_cover_critical" if status == "critical" else "stock_cover_warning"
        )
        severity = (
            ExceptionSeverity.CRITICAL if status == "critical" else ExceptionSeverity.HIGH
        )
        title = f"{row.plant_name} {row.material_name} stock cover is {status}"
        days = row.calculation.days_of_cover
        threshold = row.calculation.threshold_days
        summary = (
            f"Days of cover is {format_decimal(days)} days for {row.plant_name} / "
            f"{row.material_name}. Threshold is {format_decimal(threshold)} days."
        )
        candidates.append(
            ExceptionCandidate(
                trigger_source=trigger_source,
                type=ExceptionType.STOCKOUT_RISK,
                severity=severity,
                title=title,
                summary=summary,
                linked_plant_id=row.plant_id,
                linked_material_id=row.material_id,
                due_at=now + timedelta(hours=4 if status == "critical" else 12),
                next_action=(
                    "Validate stock position and expedite inbound supply or rebalance demand."
                ),
            )
        )
    return candidates


def shipment_signal_candidates(db: Session, context: RequestContext) -> list[ExceptionCandidate]:
    now = datetime.now(UTC)
    shipments = list(
        db.scalars(select(Shipment).where(Shipment.tenant_id == context.tenant_id))
    )
    candidates: list[ExceptionCandidate] = []
    for shipment in shipments:
        shipment_item = build_shipment_item(db, shipment)
        if shipment_item.shipment_state in {"delivered", "cancelled"}:
            continue

        eta_delay = shipment.current_eta - shipment.planned_eta
        if eta_delay > timedelta(hours=ETA_DELAY_THRESHOLD_HOURS):
            delay_hours = int(eta_delay.total_seconds() // 3600)
            severity = (
                ExceptionSeverity.HIGH if delay_hours >= 72 else ExceptionSeverity.MEDIUM
            )
            candidates.append(
                ExceptionCandidate(
                    trigger_source="shipment_eta_delay",
                    type=ExceptionType.ETA_RISK,
                    severity=severity,
                    title=f"Shipment {shipment.shipment_id} ETA drift exceeds threshold",
                    summary=(
                        f"Current ETA is delayed by {delay_hours} hours versus plan for "
                        f"{shipment.shipment_id}."
                    ),
                    linked_shipment_id=shipment.id,
                    linked_plant_id=shipment.plant_id,
                    linked_material_id=shipment.material_id,
                    due_at=now + timedelta(hours=12),
                    next_action="Review ETA drift with logistics and update receiving plan.",
                )
            )

        age = now - ensure_utc(shipment_item.last_update_at)
        if shipment_item.confidence == "low" and (
            age > timedelta(days=7)
            or len(shipment_item.contributing_data_sources) <= 1
        ):
            reason = (
                "updates are stale"
                if age > timedelta(days=7)
                else "supporting updates are missing"
            )
            candidates.append(
                ExceptionCandidate(
                    trigger_source="shipment_stale_update",
                    type=ExceptionType.DATA_QUALITY,
                    severity=ExceptionSeverity.MEDIUM,
                    title=f"Shipment {shipment.shipment_id} has stale tracking data",
                    summary=(
                        f"Shipment confidence is low because {reason}. Last update is "
                        f"{shipment_item.last_update_at.isoformat()}."
                    ),
                    linked_shipment_id=shipment.id,
                    linked_plant_id=shipment.plant_id,
                    linked_material_id=shipment.material_id,
                    due_at=now + timedelta(hours=24),
                    next_action=(
                        "Request a fresh ETA or event update from the current source of truth."
                    ),
                )
            )

        inland_summary = build_inland_summary(build_movement_context(db, shipment))
        if inland_summary and inland_summary.inland_delay_flag:
            candidates.append(
                ExceptionCandidate(
                    trigger_source="inland_delay_risk",
                    type=ExceptionType.ETA_RISK,
                    severity=(
                        ExceptionSeverity.HIGH
                        if inland_summary.stale_record
                        or inland_summary.dispatch_status == "delivered"
                        else ExceptionSeverity.MEDIUM
                    ),
                    title=f"Inland leg risk for shipment {shipment.shipment_id}",
                    summary=(
                        f"Inland movement for {shipment.shipment_id} is flagged as delayed "
                        f"with {inland_summary.confidence} confidence."
                    ),
                    linked_shipment_id=shipment.id,
                    linked_plant_id=shipment.plant_id,
                    linked_material_id=shipment.material_id,
                    due_at=now + timedelta(hours=8),
                    next_action=(
                        "Validate carrier status and refresh inland ETA before plant receipt "
                        "is impacted."
                    ),
                )
            )
    return candidates


def find_matching_exception(
    existing_cases: list[ExceptionCase],
    candidate: ExceptionCandidate,
) -> ExceptionCase | None:
    for record in existing_cases:
        if record.type != candidate.type:
            continue
        if record.linked_shipment_id != candidate.linked_shipment_id:
            continue
        if record.linked_plant_id != candidate.linked_plant_id:
            continue
        if record.linked_material_id != candidate.linked_material_id:
            continue
        if extract_trigger_source(record.summary) != candidate.trigger_source:
            continue
        return record
    return None


def serialize_exception(
    db: Session,
    context: RequestContext,
    exception_case: ExceptionCase,
) -> dict:
    plant = (
        db.get(Plant, exception_case.linked_plant_id)
        if exception_case.linked_plant_id
        else None
    )
    material = (
        db.get(Material, exception_case.linked_material_id)
        if exception_case.linked_material_id
        else None
    )
    shipment = (
        db.get(Shipment, exception_case.linked_shipment_id)
        if exception_case.linked_shipment_id
        else None
    )
    owner = db.get(User, exception_case.owner_user_id) if exception_case.owner_user_id else None
    owner_membership = None
    if owner:
        owner_membership = db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == context.tenant_id,
                TenantMembership.user_id == owner.id,
                TenantMembership.is_active.is_(True),
            )
        )

    return {
        "id": exception_case.id,
        "tenant_id": exception_case.tenant_id,
        "type": extract_trigger_source(exception_case.summary),
        "severity": exception_case.severity.value,
        "status": api_status(exception_case.status),
        "title": exception_case.title,
        "summary": clean_summary(exception_case.summary),
        "trigger_source": extract_trigger_source(exception_case.summary),
        "linked_shipment": linked_entity(
            shipment.id, shipment.shipment_id
        ) if shipment else None,
        "linked_plant": linked_entity(plant.id, plant.name) if plant else None,
        "linked_material": linked_entity(material.id, material.name) if material else None,
        "current_owner": (
            {
                "id": owner.id,
                "full_name": owner.full_name,
                "email": owner.email,
                "role": owner_membership.role.name if owner_membership else None,
            }
            if owner
            else None
        ),
        "created_at": ensure_utc(exception_case.created_at),
        "updated_at": ensure_utc(exception_case.updated_at),
        "triggered_at": ensure_utc(exception_case.triggered_at),
        "due_at": ensure_optional_utc(exception_case.due_at),
        "recommended_next_step": exception_case.next_action,
        "action_status": exception_case.action_status or "pending",
        "action_started_at": ensure_optional_utc(exception_case.action_started_at),
        "action_completed_at": ensure_optional_utc(exception_case.action_completed_at),
        "action_sla_breach": action_sla_breach_for(exception_case),
        "action_age_hours": action_age_hours_for(exception_case),
    }


def detail_context_notes(
    db: Session,
    context: RequestContext,
    exception_case: ExceptionCase,
) -> list[str]:
    notes: list[str] = []
    trigger = extract_trigger_source(exception_case.summary)
    if trigger in {"stock_cover_critical", "stock_cover_warning"}:
        notes.append("Exception came from the stock-cover engine using the latest stock snapshot.")
    if trigger == "shipment_eta_delay":
        notes.append("ETA delay is measured against planned ETA using the current shipment ETA.")
    if trigger == "shipment_stale_update":
        notes.append("Low shipment confidence was caused by stale or missing update signals.")
    if trigger == "inland_delay_risk":
        notes.append("Inland risk is based on the latest inland movement arrival signal.")
    if exception_case.linked_shipment_id:
        shipment = db.get(Shipment, exception_case.linked_shipment_id)
        if shipment:
            item = build_shipment_item(db, shipment)
            reasons = shipment_confidence_reasons(load_shipment_context(db, shipment), item)
            notes.extend(reasons[:2])
    if exception_case.owner_user_id is None:
        notes.append("This exception is currently unassigned.")
    return notes


def is_system_generated_exception(exception_case: ExceptionCase) -> bool:
    return extract_trigger_source(exception_case.summary) in VALID_TRIGGER_TYPES


def action_sla_breach_for(exception_case: ExceptionCase) -> bool:
    if exception_case.action_status == "completed" or exception_case.due_at is None:
        return False
    return ensure_utc(exception_case.due_at) < datetime.now(UTC)


def action_age_hours_for(exception_case: ExceptionCase) -> Decimal | None:
    started_at = exception_case.action_started_at or exception_case.triggered_at
    end_at = (
        exception_case.action_completed_at
        if exception_case.action_status == "completed" and exception_case.action_completed_at
        else datetime.now(UTC)
    )
    if started_at is None:
        return None
    delta = ensure_utc(end_at) - ensure_utc(started_at)
    return (Decimal(str(delta.total_seconds())) / Decimal("3600")).quantize(Decimal("0.01"))


def load_shipment_context(db: Session, shipment: Shipment):
    from app.modules.shipments.service import load_context

    return load_context(db, shipment)


def list_comments(
    db: Session,
    context: RequestContext,
    exception_id: int,
) -> list[dict]:
    comments = list(
        db.scalars(
            select(ExceptionComment)
            .where(
                ExceptionComment.tenant_id == context.tenant_id,
                ExceptionComment.exception_case_id == exception_id,
            )
            .order_by(ExceptionComment.created_at.asc())
        )
    )
    rows: list[dict] = []
    for record in comments:
        author = db.get(User, record.author_user_id) if record.author_user_id else None
        membership = None
        if author:
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == context.tenant_id,
                    TenantMembership.user_id == author.id,
                    TenantMembership.is_active.is_(True),
                )
            )
        rows.append(
            {
                "id": record.id,
                "author": (
                    {
                        "id": author.id,
                        "full_name": author.full_name,
                        "email": author.email,
                        "role": membership.role.name if membership else None,
                    }
                    if author
                    else None
                ),
                "comment": record.comment,
                "created_at": ensure_utc(record.created_at),
            }
        )
    return rows


def linked_shipment_detail(
    db: Session,
    exception_case: ExceptionCase,
) -> dict[str, str | int | None] | None:
    if exception_case.linked_shipment_id is None:
        return None
    shipment = db.get(Shipment, exception_case.linked_shipment_id)
    if shipment is None:
        return None
    item = build_shipment_item(db, shipment)
    return {
        "shipment_id": item.shipment_id,
        "shipment_state": item.shipment_state,
        "confidence": item.confidence,
        "last_update_at": item.last_update_at.isoformat(),
        "latest_status_source": item.latest_status_source,
        "contribution_band": item.contribution_band,
    }


def list_tenant_users(db: Session, context: RequestContext) -> list[dict]:
    memberships = list(
        db.scalars(
            select(TenantMembership)
            .where(
                TenantMembership.tenant_id == context.tenant_id,
                TenantMembership.is_active.is_(True),
            )
            .order_by(TenantMembership.user_id.asc())
        )
    )
    rows: list[dict] = []
    for membership in memberships:
        user = db.get(User, membership.user_id)
        if user is None:
            continue
        rows.append(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": membership.role.name,
            }
        )
    return rows


def create_audit_log(
    db: Session,
    context: RequestContext,
    *,
    action: str,
    entity_type: str = "exception_case",
    entity_id: str,
    metadata: dict,
) -> None:
    db.add(
        AuditLog(
            tenant_id=context.tenant_id,
            actor_user_id=context.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def api_status(status: ExceptionStatus) -> str:
    if status == ExceptionStatus.DISMISSED:
        return "closed"
    if status == ExceptionStatus.ACKNOWLEDGED:
        return "in_progress"
    return status.value


def encode_summary(trigger_source: str, summary: str | None) -> str | None:
    if summary is None:
        return None
    return f"{TRIGGER_PREFIX}{trigger_source}] {summary}"


def clean_summary(summary: str | None) -> str | None:
    if summary is None:
        return None
    if summary.startswith(TRIGGER_PREFIX) and "] " in summary:
        return summary.split("] ", maxsplit=1)[1]
    return summary


def extract_trigger_source(summary: str | None) -> str:
    if summary and summary.startswith(TRIGGER_PREFIX) and "]" in summary:
        return summary[len(TRIGGER_PREFIX) : summary.index("]")]
    return "unknown"


def count_open_exceptions(items: list[ExceptionCase]) -> int:
    return sum(
        1
        for item in items
        if item.status in ACTIVE_EXCEPTION_STATUSES
    )


def count_resolved_recently(items: list[ExceptionCase]) -> int:
    cutoff = datetime.now(UTC) - RECENTLY_RESOLVED_WINDOW
    return sum(
        1
        for item in items
        if item.status == ExceptionStatus.RESOLVED and ensure_utc(item.updated_at) >= cutoff
    )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_optional_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(value)


def linked_entity(entity_id: int, label: str) -> dict[str, str | int]:
    return {"id": entity_id, "label": label}


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"{value.quantize(Decimal('0.01'))}"
