from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ContinuityRiskSnapshot,
    NotificationDeliveryLog,
    NotificationSettings,
    Role,
    Tenant,
    TenantMembership,
    User,
)
from app.modules.notifications.schemas import (
    NotificationDispatchResult,
    NotificationSettingsPayload,
    NotificationSettingsRead,
)
from app.modules.reports.service import (
    ExecutiveContinuityReport,
    ExecutiveMaterialRisk,
    build_executive_continuity_report,
)
from app.schemas.context import RequestContext

STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"
TYPE_CRITICAL_ALERT = "critical_alert"
TYPE_WEEKLY_DIGEST = "weekly_digest"
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class EmailMessage:
    subject: str
    body: str
    recipients_to: list[str]
    recipients_cc: list[str]


class ConsoleEmailSender:
    def send(self, message: EmailMessage) -> None:
        print(
            f"[OpsDeck email] {message.subject} "
            f"to={message.recipients_to} cc={message.recipients_cc}"
        )


def get_notification_settings(db: Session, context: RequestContext) -> NotificationSettings:
    settings = db.scalar(
        select(NotificationSettings).where(NotificationSettings.tenant_id == context.tenant_id)
    )
    if settings is not None:
        return settings
    settings = NotificationSettings(
        tenant_id=context.tenant_id,
        recipients_to=tenant_admin_emails(db, context.tenant_id),
        recipients_cc=[],
        pilot_contacts=[],
        critical_alerts_enabled=True,
        weekly_digest_enabled=True,
        digest_day="monday",
        digest_time="08:00",
        tenant_timezone="Asia/Kolkata",
        cooldown_hours=24,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_notification_settings(
    db: Session,
    context: RequestContext,
    payload: NotificationSettingsPayload,
) -> NotificationSettingsRead:
    settings = get_notification_settings(db, context)
    settings.critical_alerts_enabled = payload.critical_alerts_enabled
    settings.weekly_digest_enabled = payload.weekly_digest_enabled
    settings.recipients_to = normalized_emails(payload.recipients_to)
    settings.recipients_cc = normalized_emails(payload.recipients_cc)
    settings.pilot_contacts = normalized_emails(payload.pilot_contacts)
    settings.digest_day = payload.digest_day.lower()
    settings.digest_time = payload.digest_time
    settings.tenant_timezone = payload.tenant_timezone
    settings.cooldown_hours = payload.cooldown_hours
    db.commit()
    db.refresh(settings)
    return NotificationSettingsRead.model_validate(settings)


def send_test_weekly_digest(
    db: Session,
    context: RequestContext,
    *,
    sender: ConsoleEmailSender | None = None,
) -> NotificationDispatchResult:
    report = build_executive_continuity_report(db, context)
    return send_weekly_digest(db, context, report=report, sender=sender, force=True)


def send_weekly_digest(
    db: Session,
    context: RequestContext,
    *,
    report: ExecutiveContinuityReport | None = None,
    sender: ConsoleEmailSender | None = None,
    force: bool = False,
    now: datetime | None = None,
    condition_key: str | None = None,
) -> NotificationDispatchResult:
    settings = get_notification_settings(db, context)
    sent_at = now or datetime.now(UTC)
    if not settings.weekly_digest_enabled and not force:
        return skipped_result(
            db,
            context,
            settings,
            notification_type=TYPE_WEEKLY_DIGEST,
            subject="OpsDeck Weekly Continuity Digest",
            reason="Weekly digest is disabled.",
            sent_at=sent_at,
        )
    report = report or build_executive_continuity_report(db, context, generated_at=sent_at)
    changes = risk_changes_for_digest(db, context, report.critical_materials, sent_at=sent_at)
    body = weekly_digest_body(report, changes)
    digest_condition_key = condition_key or f"weekly:{sent_at.date().isoformat()}"
    return deliver_email(
        db,
        context,
        settings,
        EmailMessage(
            subject="OpsDeck Weekly Continuity Digest",
            body=body,
            recipients_to=all_to_recipients(settings),
            recipients_cc=settings.recipients_cc or [],
        ),
        notification_type=TYPE_WEEKLY_DIGEST,
        condition_key=digest_condition_key,
        sender=sender,
        sent_at=sent_at,
        metadata={"changes": changes, "markdown": body},
    )


def send_due_weekly_digests_once(db: Session, *, now: datetime | None = None) -> int:
    sent = 0
    current_time = now or datetime.now(UTC)
    settings_rows = list(
        db.scalars(
            select(NotificationSettings)
            .where(NotificationSettings.weekly_digest_enabled.is_(True))
            .order_by(NotificationSettings.tenant_id.asc())
        )
    )
    for settings in settings_rows:
        if not weekly_digest_due(db, settings, current_time):
            continue
        tenant = db.get(Tenant, settings.tenant_id)
        context = RequestContext(
            tenant_id=settings.tenant_id,
            tenant_slug=tenant.slug if tenant else f"tenant-{settings.tenant_id}",
            role="tenant_admin",
            user_id=resolve_notification_user_id(db, settings.tenant_id) or 0,
        )
        local_now = current_time.astimezone(resolve_timezone(settings.tenant_timezone))
        send_weekly_digest(
            db,
            context,
            now=current_time,
            condition_key=f"weekly:{local_now.date().isoformat()}",
        )
        sent += 1
    return sent


def send_due_critical_alerts_once(db: Session, *, now: datetime | None = None) -> int:
    sent = 0
    current_time = now or datetime.now(UTC)
    settings_rows = list(
        db.scalars(
            select(NotificationSettings)
            .where(NotificationSettings.critical_alerts_enabled.is_(True))
            .order_by(NotificationSettings.tenant_id.asc())
        )
    )
    for settings in settings_rows:
        if not all_to_recipients(settings):
            continue
        tenant = db.get(Tenant, settings.tenant_id)
        context = RequestContext(
            tenant_id=settings.tenant_id,
            tenant_slug=tenant.slug if tenant else f"tenant-{settings.tenant_id}",
            role="tenant_admin",
            user_id=resolve_notification_user_id(db, settings.tenant_id) or 0,
        )
        result = send_critical_alerts(
            db,
            context,
            now=current_time,
            log_skips=False,
        )
        if result.status == STATUS_SENT:
            sent += 1
    return sent


def weekly_digest_due(
    db: Session,
    settings: NotificationSettings,
    now: datetime,
) -> bool:
    local_now = now.astimezone(resolve_timezone(settings.tenant_timezone))
    if local_now.strftime("%A").lower() != settings.digest_day.lower():
        return False
    hour, minute = digest_hour_minute(settings.digest_time)
    if (local_now.hour, local_now.minute) < (hour, minute):
        return False
    condition_key = f"weekly:{local_now.date().isoformat()}"
    return not recently_sent(
        db,
        RequestContext(
            tenant_id=settings.tenant_id,
            tenant_slug="scheduler",
            role="tenant_admin",
            user_id=0,
        ),
        notification_type=TYPE_WEEKLY_DIGEST,
        condition_key=condition_key,
        since=local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC),
    )


def send_test_critical_alert(
    db: Session,
    context: RequestContext,
    *,
    sender: ConsoleEmailSender | None = None,
) -> NotificationDispatchResult:
    return send_critical_alerts(db, context, sender=sender, force=True)


def send_critical_alerts(
    db: Session,
    context: RequestContext,
    *,
    sender: ConsoleEmailSender | None = None,
    force: bool = False,
    now: datetime | None = None,
    log_skips: bool = True,
) -> NotificationDispatchResult:
    settings = get_notification_settings(db, context)
    sent_at = now or datetime.now(UTC)
    if not settings.critical_alerts_enabled and not force:
        return critical_skipped_result(
            db=db,
            context=context,
            settings=settings,
            reason="Critical alerts are disabled.",
            sent_at=sent_at,
            log_skips=log_skips,
        )
    report = build_executive_continuity_report(db, context, generated_at=sent_at)
    critical_materials = [
        item for item in report.critical_materials if item.severity == "critical"
    ]
    if not critical_materials:
        return critical_skipped_result(
            db=db,
            context=context,
            settings=settings,
            reason="No critical material exposure is active.",
            sent_at=sent_at,
            log_skips=log_skips,
        )
    results: list[NotificationDispatchResult] = []
    suppressed = 0
    for material in critical_materials:
        condition_key = critical_condition_key(material)
        if not force and recently_sent(
            db,
            context,
            notification_type=TYPE_CRITICAL_ALERT,
            condition_key=condition_key,
            since=sent_at - timedelta(hours=settings.cooldown_hours),
        ):
            suppressed += 1
            continue
        body = critical_alert_body(material)
        results.append(
            deliver_email(
                db,
                context,
                settings,
                EmailMessage(
                    subject="[OpsDeck] Critical Continuity Exposure Detected",
                    body=body,
                    recipients_to=all_to_recipients(settings),
                    recipients_cc=settings.recipients_cc or [],
                ),
                notification_type=TYPE_CRITICAL_ALERT,
                condition_key=condition_key,
                sender=sender,
                sent_at=sent_at,
                metadata={"material": material.model_dump(mode="json"), "markdown": body},
            )
        )
    if not results:
        return critical_skipped_result(
            db=db,
            context=context,
            settings=settings,
            reason="Critical alert suppressed during cooldown.",
            sent_at=sent_at,
            log_skips=log_skips,
            condition_key=None,
        )
    logs = [log for result in results for log in result.logs]
    status = (
        STATUS_FAILED
        if any(result.status == STATUS_FAILED for result in results)
        else STATUS_SENT
    )
    skipped_reason = None
    if suppressed:
        skipped_reason = f"{suppressed} critical material alert(s) suppressed during cooldown."
    return NotificationDispatchResult(
        subject="[OpsDeck] Critical Continuity Exposure Detected",
        notification_type=TYPE_CRITICAL_ALERT,
        status=status,
        recipients_to=all_to_recipients(settings),
        recipients_cc=settings.recipients_cc or [],
        skipped_reason=skipped_reason,
        logs=logs,
    )


def deliver_email(
    db: Session,
    context: RequestContext,
    settings: NotificationSettings,
    message: EmailMessage,
    *,
    notification_type: str,
    condition_key: str | None,
    sender: ConsoleEmailSender | None,
    sent_at: datetime,
    metadata: dict,
) -> NotificationDispatchResult:
    recipients = normalized_emails(message.recipients_to)
    cc = normalized_emails(message.recipients_cc)
    if not recipients:
        return skipped_result(
            db,
            context,
            settings,
            notification_type=notification_type,
            subject=message.subject,
            reason="No notification recipients are configured.",
            sent_at=sent_at,
            condition_key=condition_key,
        )
    sender = sender or ConsoleEmailSender()
    status = STATUS_SENT
    error = None
    try:
        sender.send(message)
    except Exception as exc:  # pragma: no cover - defensive for future senders
        status = STATUS_FAILED
        error = str(exc)

    logs = [
        create_delivery_log(
            db,
            context,
            recipient=recipient,
            subject=message.subject,
            notification_type=notification_type,
            status=status,
            sent_at=sent_at,
            condition_key=condition_key,
            error_message=error,
            metadata=metadata,
        )
        for recipient in [*recipients, *cc]
    ]
    db.commit()
    return NotificationDispatchResult(
        subject=message.subject,
        notification_type=notification_type,
        status=status,
        recipients_to=recipients,
        recipients_cc=cc,
        skipped_reason=None,
        logs=logs,
    )


def skipped_result(
    db: Session,
    context: RequestContext,
    settings: NotificationSettings,
    *,
    notification_type: str,
    subject: str,
    reason: str,
    sent_at: datetime,
    condition_key: str | None = None,
) -> NotificationDispatchResult:
    logs = [
        create_delivery_log(
            db,
            context,
            recipient=recipient,
            subject=subject,
            notification_type=notification_type,
            status=STATUS_SKIPPED,
            sent_at=sent_at,
            condition_key=condition_key,
            error_message=reason,
            metadata={"reason": reason},
        )
        for recipient in all_to_recipients(settings)
    ]
    db.commit()
    return NotificationDispatchResult(
        subject=subject,
        notification_type=notification_type,
        status=STATUS_SKIPPED,
        recipients_to=all_to_recipients(settings),
        recipients_cc=settings.recipients_cc or [],
        skipped_reason=reason,
        logs=logs,
    )


def critical_skipped_result(
    *,
    db: Session,
    context: RequestContext,
    settings: NotificationSettings,
    reason: str,
    sent_at: datetime,
    log_skips: bool,
    condition_key: str | None = None,
) -> NotificationDispatchResult:
    if log_skips:
        return skipped_result(
            db,
            context,
            settings,
            notification_type=TYPE_CRITICAL_ALERT,
            subject="[OpsDeck] Critical Continuity Exposure Detected",
            reason=reason,
            sent_at=sent_at,
            condition_key=condition_key,
        )
    return NotificationDispatchResult(
        subject="[OpsDeck] Critical Continuity Exposure Detected",
        notification_type=TYPE_CRITICAL_ALERT,
        status=STATUS_SKIPPED,
        recipients_to=all_to_recipients(settings),
        recipients_cc=settings.recipients_cc or [],
        skipped_reason=reason,
        logs=[],
    )


def create_delivery_log(
    db: Session,
    context: RequestContext,
    *,
    recipient: str,
    subject: str,
    notification_type: str,
    status: str,
    sent_at: datetime,
    condition_key: str | None,
    error_message: str | None,
    metadata: dict | None,
) -> NotificationDeliveryLog:
    log = NotificationDeliveryLog(
        tenant_id=context.tenant_id,
        notification_type=notification_type,
        recipient=recipient,
        subject=subject,
        sent_at=sent_at,
        status=status,
        condition_key=condition_key,
        error_message=error_message,
        metadata_json=metadata,
    )
    db.add(log)
    db.flush()
    return log


def recently_sent(
    db: Session,
    context: RequestContext,
    *,
    notification_type: str,
    condition_key: str,
    since: datetime,
) -> bool:
    return (
        db.scalar(
            select(NotificationDeliveryLog.id)
            .where(
                NotificationDeliveryLog.tenant_id == context.tenant_id,
                NotificationDeliveryLog.notification_type == notification_type,
                NotificationDeliveryLog.condition_key == condition_key,
                NotificationDeliveryLog.status == STATUS_SENT,
                NotificationDeliveryLog.sent_at >= since,
            )
            .limit(1)
        )
        is not None
    )


def risk_changes_for_digest(
    db: Session,
    context: RequestContext,
    current_materials: list[ExecutiveMaterialRisk],
    *,
    sent_at: datetime,
) -> dict[str, list[str]]:
    period_start = sent_at - timedelta(days=7)
    current_keys = {
        (item.plant_reference, item.material_reference): item for item in current_materials
    }
    changes = {"new": [], "escalated": [], "resolved": []}
    for key, material in current_keys.items():
        prior = latest_prior_snapshot(db, context, key, period_start)
        label = (
            f"{material.material_reference or material.material} "
            f"at {material.plant_reference or material.plant}"
        )
        if prior is None:
            changes["new"].append(f"NEW: {label}")
        elif SEVERITY_ORDER.get(material.severity, 0) > SEVERITY_ORDER.get(prior.severity, 0):
            changes["escalated"].append(f"ESCALATED: {label}")

    prior_high = list(
        db.scalars(
            select(ContinuityRiskSnapshot).where(
                ContinuityRiskSnapshot.tenant_id == context.tenant_id,
                ContinuityRiskSnapshot.snapshot_time < period_start,
                ContinuityRiskSnapshot.severity.in_(["critical", "high"]),
            )
        )
    )
    for snapshot in prior_high:
        key = (snapshot.plant_reference, snapshot.material_reference)
        if key not in current_keys:
            label = (
                f"{snapshot.material_reference or 'material'} "
                f"at {snapshot.plant_reference or 'plant'}"
            )
            changes["resolved"].append(f"RESOLVED: {label}")
    return {key: dedupe(values) for key, values in changes.items()}


def latest_prior_snapshot(
    db: Session,
    context: RequestContext,
    key: tuple[str | None, str | None],
    period_start: datetime,
) -> ContinuityRiskSnapshot | None:
    return db.scalar(
        select(ContinuityRiskSnapshot)
        .where(
            ContinuityRiskSnapshot.tenant_id == context.tenant_id,
            ContinuityRiskSnapshot.plant_reference == key[0],
            ContinuityRiskSnapshot.material_reference == key[1],
            ContinuityRiskSnapshot.snapshot_time < period_start,
        )
        .order_by(ContinuityRiskSnapshot.snapshot_time.desc())
        .limit(1)
    )


def critical_alert_body(material: ExecutiveMaterialRisk) -> str:
    actions = material.immediate_actions or ["Review this risk in OpsDeck immediately."]
    calibration = (
        material.assessment_calibration.status if material.assessment_calibration else "N/A"
    )
    investigation_link = (
        "/dashboard/risk-workspace?"
        f"plant_reference={material.plant_reference}&"
        f"material_reference={material.material_reference}"
    )
    return "\n".join(
        [
            "# Critical Continuity Exposure Detected",
            "",
            f"Plant: {material.plant}",
            f"Material: {material.material}",
            f"Severity: {material.severity.title()}",
            f"Current Usable Cover: {material.current_usable_cover or 'N/A'} days",
            f"Projected Breach: {date_or_na(material.earliest_breach_date)}",
            f"Assessment Calibration: {calibration}",
            f"Operational Trust: {material.operational_trust}",
            "",
            "Why Escalating:",
            *[f"- {item}" for item in material.why_escalating[:5]],
            "",
            "Top Recommended Actions:",
            *[f"- {item}" for item in actions[:5]],
            "",
            f"Investigation: {investigation_link}",
        ]
    )


def weekly_digest_body(
    report: ExecutiveContinuityReport,
    changes: dict[str, list[str]],
) -> str:
    summary = report.summary
    lines = [
        "# OpsDeck Weekly Continuity Digest",
        "",
        "## Executive Summary",
        f"Materials Assessed: {summary.materials_assessed}",
        f"Critical: {summary.critical_materials}",
        f"High: {summary.high_risk_materials}",
        f"Average Calibration: {summary.average_assessment_calibration}",
        f"Average Operational Trust: {summary.average_operational_trust}",
        f"Detection Rate: {summary.historical_validation_detection_rate or 'N/A'}%",
        "",
        "## Risk Changes This Week",
        *[f"- {item}" for item in changes.get("new", []) or ["No new risks."]],
        *[f"- {item}" for item in changes.get("escalated", []) or ["No escalated risks."]],
        *[f"- {item}" for item in changes.get("resolved", []) or ["No resolved risks."]],
        "",
        "## Critical Materials",
    ]
    for material in report.critical_materials:
        calibration = (
            material.assessment_calibration.status if material.assessment_calibration else "N/A"
        )
        lines.extend(
            [
                (
                    f"- {material.material} at {material.plant}: "
                    f"{material.severity.title()}, "
                    f"{material.current_usable_cover or 'N/A'} days cover, "
                    f"{calibration}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Recommended Executive Actions",
            *[
                f"- {item}"
                for item in report.recommended_actions.get("immediate", [])
                or ["No immediate executive actions returned."]
            ],
            "",
            "## Past Incident Analysis Summary",
            "Incident Replay",
            report.historical_validation.interpretation,
        ]
    )
    return "\n".join(lines)


def critical_condition_key(material: ExecutiveMaterialRisk) -> str:
    return f"critical:{material.plant_reference}:{material.material_reference}"


def tenant_admin_emails(db: Session, tenant_id: int) -> list[str]:
    rows = db.execute(
        select(User.email, Role.name)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .join(Role, Role.id == TenantMembership.role_id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.is_active.is_(True),
            User.is_active.is_(True),
        )
    )
    emails = [email for email, role in rows if role in {"tenant_admin", "admin", "logistics_user"}]
    return normalized_emails(emails)


def resolve_notification_user_id(db: Session, tenant_id: int) -> int | None:
    return db.scalar(
        select(TenantMembership.user_id)
        .join(Role, Role.id == TenantMembership.role_id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.is_active.is_(True),
            Role.name == "tenant_admin",
        )
    )


def resolve_timezone(value: str):
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return UTC


def digest_hour_minute(value: str) -> tuple[int, int]:
    try:
        hour, minute = value.split(":", 1)
        return int(hour), int(minute)
    except ValueError:
        return 8, 0


def all_to_recipients(settings: NotificationSettings) -> list[str]:
    return normalized_emails([*(settings.recipients_to or []), *(settings.pilot_contacts or [])])


def normalized_emails(values: list[str]) -> list[str]:
    return dedupe([value.strip().lower() for value in values if value and "@" in value])


def date_or_na(value) -> str:
    if value is None:
        return "N/A"
    return value.date().isoformat()


def dedupe(values) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
