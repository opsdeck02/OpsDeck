from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Role, Tenant, TenantMembership, User
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password


def test_superadmin_can_create_and_list_milestone(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    response = client.post(
        "/api/v1/operational-history/tenants/1/milestones",
        headers=headers,
        json={
            "title": "Pilot kickoff",
            "description": "Evaluation launched with plant leadership.",
            "milestone_type": "kickoff",
            "status": "complete",
            "occurred_at": "2026-07-01T09:00:00Z",
        },
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Pilot kickoff"

    list_response = client.get(
        "/api/v1/operational-history/tenants/1/milestones",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_tenant_admin_cannot_access_operational_history(client: TestClient) -> None:
    headers = auth_headers(client, "tenant-admin@test.local")
    response = client.get(
        "/api/v1/operational-history/tenants/1",
        headers=headers,
    )
    assert response.status_code == 403


def test_superadmin_can_create_and_list_notes(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    response = client.post(
        "/api/v1/operational-history/tenants/1/notes",
        headers=headers,
        json={
            "note_type": "weekly_review",
            "title": "Week 1 review",
            "body": "Shipment context was sufficient for pilot review.",
            "attendees": ["Plant Head", "OpsDeck"],
            "actions": ["Confirm next data upload"],
            "note_date": "2026-07-08T09:00:00Z",
        },
    )
    assert response.status_code == 200
    assert response.json()["attendees"] == ["Plant Head", "OpsDeck"]

    list_response = client.get(
        "/api/v1/operational-history/tenants/1/notes",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["title"] == "Week 1 review"


def test_generate_report_creates_immutable_versioned_snapshots(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    payload = {
        "report_type": "pilot",
        "period_start": "2026-07-01",
        "period_end": "2026-08-26",
        "title": "Focused Evaluation Report",
    }
    first = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json=payload,
    )
    second = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["snapshot_payload"]["period"] == {
        "start": "2026-07-01",
        "end": "2026-08-26",
    }


def test_pdf_download_returns_application_pdf(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    created = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={"report_type": "pilot", "title": "Pilot Report"},
    )
    report_id = created.json()["id"]

    response = client.get(
        f"/api/v1/operational-history/tenants/1/reports/{report_id}/pdf",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.content.startswith(b"%PDF")


def test_report_list_is_tenant_scoped(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={"report_type": "pilot", "title": "Tenant A Report"},
    )
    client.post(
        "/api/v1/operational-history/tenants/2/reports/generate",
        headers=headers,
        json={"report_type": "pilot", "title": "Tenant B Report"},
    )

    tenant_a = client.get("/api/v1/operational-history/tenants/1/reports", headers=headers)
    tenant_b = client.get("/api/v1/operational-history/tenants/2/reports", headers=headers)

    assert tenant_a.status_code == 200
    assert tenant_b.status_code == 200
    assert [item["title"] for item in tenant_a.json()] == ["Tenant A Report"]
    assert [item["title"] for item in tenant_b.json()] == ["Tenant B Report"]


def test_superadmin_can_create_weekly_review_and_timeline_entry(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    response = client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["week_number"] == 3
    assert body["actions"][0]["description"] == "Historical replay"

    timeline = client.get(
        "/api/v1/operational-history/tenants/1/milestones",
        headers=headers,
    )
    assert timeline.status_code == 200
    assert any(item["title"] == "Week 3 Review Completed" for item in timeline.json())


def test_weekly_review_action_status_creates_completion_timeline(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    created = client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    ).json()
    action_id = created["actions"][0]["id"]

    updated = client.patch(
        f"/api/v1/operational-reviews/tenants/1/weekly-reviews/{created['id']}/actions/{action_id}",
        headers=headers,
        json={"status": "Completed"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "Completed"

    timeline = client.get(
        "/api/v1/operational-history/tenants/1/milestones",
        headers=headers,
    )
    assert any(
        item["title"] == "Action Completed: Historical replay"
        for item in timeline.json()
    )


def test_report_snapshot_includes_weekly_review_summary(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )
    report = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={"report_type": "pilot", "title": "Pilot Report"},
    )

    assert report.status_code == 200
    weekly_reviews = report.json()["snapshot_payload"]["weekly_reviews"]
    assert weekly_reviews[0]["week_number"] == 3
    assert weekly_reviews[0]["meeting_summary"] == "Historical replay validated."


def test_weekly_reviews_are_tenant_scoped(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )

    tenant_a = client.get(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
    )
    tenant_b = client.get(
        "/api/v1/operational-reviews/tenants/2/weekly-reviews",
        headers=headers,
    )

    assert len(tenant_a.json()) == 1
    assert tenant_b.json() == []


def test_tenant_admin_cannot_access_weekly_reviews(client: TestClient) -> None:
    headers = auth_headers(client, "tenant-admin@test.local")
    response = client.get(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
    )
    assert response.status_code == 403


def test_customer_health_not_started_for_empty_tenant(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    response = client.get("/api/v1/customer-health/tenants/2", headers=headers)

    assert response.status_code == 200
    assert response.json()["readiness_status"] == "not_started"
    assert response.json()["pilot_progress_percent"] == 0


def test_customer_health_in_progress_without_report(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-history/tenants/1/milestones",
        headers=headers,
        json={
            "title": "Data collection started",
            "milestone_type": "data_collection",
            "status": "pending",
        },
    )

    response = client.get("/api/v1/customer-health/tenants/1", headers=headers)

    assert response.status_code == 200
    assert response.json()["readiness_status"] == "in_progress"
    assert response.json()["has_pilot_report"] is False


def test_customer_health_blocked_with_blockers_or_overdue_actions(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    payload = weekly_review_payload()
    payload["blockers"] = "Supplier mapping is incomplete."
    payload["agreed_actions"][0]["due_date"] = "2020-01-01"
    client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=payload,
    )

    response = client.get("/api/v1/customer-health/tenants/1", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["readiness_status"] == "blocked"
    assert body["overdue_actions_count"] == 1
    assert body["has_open_blockers"] is True
    assert body["blockers"]


def test_customer_health_ready_for_final_review_without_pilot_report(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )

    response = client.get("/api/v1/customer-health/tenants/1", headers=headers)

    assert response.status_code == 200
    assert response.json()["readiness_status"] == "ready_for_final_review"
    assert "Generate pilot report" in " ".join(response.json()["next_best_actions"])


def test_customer_health_ready_for_proposal_with_pilot_report(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )
    client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={"report_type": "pilot", "title": "Pilot Report"},
    )

    response = client.get("/api/v1/customer-health/tenants/1", headers=headers)

    assert response.status_code == 200
    assert response.json()["readiness_status"] == "ready_for_proposal"
    assert response.json()["has_pilot_report"] is True


def test_tenant_admin_cannot_access_customer_health(client: TestClient) -> None:
    headers = auth_headers(client, "tenant-admin@test.local")
    response = client.get("/api/v1/customer-health/tenants", headers=headers)
    assert response.status_code == 403


def test_customer_health_list_is_tenant_scoped(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )

    response = client.get("/api/v1/customer-health/tenants", headers=headers)

    assert response.status_code == 200
    by_tenant = {item["tenant_id"]: item for item in response.json()}
    assert by_tenant[1]["weekly_reviews_count"] == 1
    assert by_tenant[2]["weekly_reviews_count"] == 0


def test_end_to_end_pilot_workflow_persists_and_versions_cleanly(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "superadmin@test.local")

    for index, title in enumerate(
        [
            "Kickoff",
            "Inventory received",
            "Shipment file received",
            "Thresholds configured",
        ],
        start=1,
    ):
        response = client.post(
            "/api/v1/operational-history/tenants/1/milestones",
            headers=headers,
            json={
                "title": title,
                "milestone_type": "configuration" if index == 4 else "kickoff",
                "status": "complete",
                "occurred_at": f"2026-07-0{index}T09:00:00Z",
            },
        )
        assert response.status_code == 200

    for week in range(1, 5):
        payload = weekly_review_payload(
            week_number=week,
            review_date=f"2026-07-{week + 7:02d}T09:00:00Z",
            action_description=f"Week {week} action",
        )
        if week == 2:
            payload["agreed_actions"][0]["status"] = "Completed"
        created = client.post(
            "/api/v1/operational-reviews/tenants/1/weekly-reviews",
            headers=headers,
            json=payload,
        )
        assert created.status_code == 200

    reviews = client.get(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
    )
    assert reviews.status_code == 200
    assert [item["week_number"] for item in reviews.json()] == [1, 2, 3, 4]

    note = client.post(
        "/api/v1/operational-history/tenants/1/notes",
        headers=headers,
        json={
            "note_type": "data_quality",
            "title": "Data Quality",
            "body": "Inventory and shipment files were usable for review.",
            "attendees": ["OpsDeck", "Customer"],
            "actions": ["Continue weekly cadence"],
            "note_date": "2026-07-15T09:00:00Z",
        },
    )
    assert note.status_code == 200
    note_id = note.json()["id"]
    updated_note = client.patch(
        f"/api/v1/operational-history/tenants/1/notes/{note_id}",
        headers=headers,
        json={"body": "Inventory, threshold, and shipment files were usable."},
    )
    assert updated_note.status_code == 200

    first_report = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={
            "report_type": "pilot",
            "period_start": "2026-07-01",
            "period_end": "2026-08-26",
            "title": "Focused Evaluation Report",
        },
    )
    assert first_report.status_code == 200
    first_payload = first_report.json()["snapshot_payload"]
    assert first_report.json()["version"] == 1
    assert [item["week_number"] for item in first_payload["weekly_reviews"]] == [1, 2, 3, 4]
    assert first_payload["milestones"]
    assert first_payload["notes"]
    assert first_payload["continuity_summary"]
    assert first_payload["next_steps"]

    note_delete = client.delete(
        f"/api/v1/operational-history/tenants/1/notes/{note_id}",
        headers=headers,
    )
    assert note_delete.status_code == 204

    second_report = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={
            "report_type": "pilot",
            "period_start": "2026-07-01",
            "period_end": "2026-08-26",
            "title": "Focused Evaluation Report",
        },
    )
    assert second_report.status_code == 200
    assert second_report.json()["version"] == 2
    assert first_report.json()["snapshot_payload"]["notes"]
    assert second_report.json()["snapshot_payload"]["notes"] == []

    pdf = client.get(
        f"/api/v1/operational-history/tenants/1/reports/{first_report.json()['id']}/pdf",
        headers=headers,
    )
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    health = client.get("/api/v1/customer-health/tenants/1", headers=headers)
    assert health.status_code == 200
    assert health.json()["readiness_status"] == "ready_for_proposal"
    assert health.json()["weekly_reviews_count"] == 4
    assert health.json()["completed_actions_count"] == 1


def test_report_and_review_endpoints_are_superadmin_only(client: TestClient) -> None:
    headers = auth_headers(client, "tenant-admin@test.local")

    report_response = client.post(
        "/api/v1/operational-history/tenants/1/reports/generate",
        headers=headers,
        json={"report_type": "pilot", "title": "Focused Evaluation Report"},
    )
    reviews_response = client.post(
        "/api/v1/operational-reviews/tenants/1/weekly-reviews",
        headers=headers,
        json=weekly_review_payload(),
    )
    health_response = client.get("/api/v1/customer-health/tenants/1", headers=headers)

    assert report_response.status_code == 403
    assert reviews_response.status_code == 403
    assert health_response.status_code == 403


def test_note_delete_does_not_leave_orphaned_records(client: TestClient) -> None:
    headers = auth_headers(client, "superadmin@test.local")
    created = client.post(
        "/api/v1/operational-history/tenants/1/notes",
        headers=headers,
        json={
            "note_type": "risk_observation",
            "title": "Risk Observation",
            "body": "Customer highlighted inbound visibility concerns.",
        },
    )
    assert created.status_code == 200
    note_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/operational-history/tenants/1/notes/{note_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    notes = client.get("/api/v1/operational-history/tenants/1/notes", headers=headers)
    summary = client.get("/api/v1/operational-history/tenants/1", headers=headers)

    assert notes.status_code == 200
    assert notes.json() == []
    assert summary.status_code == 200
    assert summary.json()["note_count"] == 0


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def weekly_review_payload(
    *,
    week_number: int = 3,
    review_date: str = "2026-08-12T09:00:00Z",
    action_description: str = "Historical replay",
) -> dict:
    return {
        "week_number": week_number,
        "review_date": review_date,
        "review_title": f"Week {week_number} Review",
        "attendees": ["OpsDeck", "Customer"],
        "meeting_summary": "Historical replay validated.",
        "operational_observations": ["Supplier mapping improved"],
        "customer_feedback": "Review format is useful.",
        "agreed_actions": [
            {
                "description": action_description,
                "owner": "OpsDeck",
                "due_date": "2099-08-15",
                "status": "Open",
            }
        ],
        "blockers": "",
        "next_focus": "Operational review established.",
    }


def seed_operational_history_data(db: Session) -> None:
    role = Role(name=TENANT_ADMIN, description="Tenant admin")
    tenant_a = Tenant(
        name="Tenant A",
        slug="tenant-a",
        plan_tier="pilot",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    tenant_b = Tenant(
        name="Tenant B",
        slug="tenant-b",
        plan_tier="pilot",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    superadmin = User(
        email="superadmin@test.local",
        full_name="Super Admin",
        password_hash=hash_password("Password123!"),
        is_active=True,
        is_superadmin=True,
    )
    tenant_admin = User(
        email="tenant-admin@test.local",
        full_name="Tenant Admin",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add_all([role, tenant_a, tenant_b, superadmin, tenant_admin])
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_a.id,
            user_id=tenant_admin.id,
            role_id=role.id,
            is_active=True,
        )
    )
    db.commit()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with testing_session() as db:
        seed_operational_history_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
