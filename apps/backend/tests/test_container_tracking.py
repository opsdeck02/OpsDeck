from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    Container,
    Material,
    Plant,
    Role,
    Shipment,
    ShipmentContainer,
    Tenant,
    TenantMembership,
    TrackingEvent,
    User,
)
from app.models.enums import ShipmentState
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password
from app.modules.tracking.providers import (
    DcsaTrackingProvider,
    TrackingProviderConfigurationError,
    TrackingProviderRequestError,
)
from app.modules.tracking.schemas import TrackingEventOut
from app.modules.tracking.service import calculate_delay_status, normalize_container_no


@pytest.fixture()
def client_and_session() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_tracking_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_container_validation() -> None:
    assert normalize_container_no("mscu1234567") == "MSCU1234567"
    with pytest.raises(ValueError):
        normalize_container_no("MSCU123456")
    with pytest.raises(ValueError):
        normalize_container_no("MSC12345678")


def test_delay_calculation() -> None:
    planned = datetime(2026, 5, 10, tzinfo=UTC)
    assert calculate_delay_status(planned, datetime(2026, 5, 12, tzinfo=UTC)) == (2, "delayed")
    assert calculate_delay_status(planned, datetime(2026, 5, 9, tzinfo=UTC)) == (-1, "early")
    assert calculate_delay_status(planned, datetime(2026, 5, 10, tzinfo=UTC)) == (0, "on_time")
    assert calculate_delay_status(planned, None) == (None, "unknown")


def test_search_detects_carrier_and_returns_port_inland_events(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["carrier_detection"]["carrier_code"] == "MSC"
    assert body["carrier_detection"]["requires_manual_selection"] is False
    event_types = {event["event_type"] for event in body["events"]}
    assert {"Gate in", "Vessel arrival", "Rail arrival", "Delivered"}.issubset(event_types)


def test_unknown_carrier_requires_manual_selection(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "ZZZU1234567"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["carrier_detection"]["requires_manual_selection"] is True
    assert body["events"] == []


def test_dcsa_missing_config_returns_structured_error(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={
            "container_no": "MSCU1234567",
            "carrier_code": "MSC",
            "tracking_source": "dcsa",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "tracking_provider_not_configured"


def test_manual_carrier_search_persists_selection_without_updating_shipment(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "ZZZU1234567", "carrier_code": "MSC"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["carrier_detection"]["confidence"] == "manual"
    assert body["events"]

    with SessionLocal() as db:
        container = db.scalar(select(Container).where(Container.container_no == "ZZZU1234567"))
        shipment = db.get(Shipment, 1)
        assert container is not None
        assert container.carrier_code == "MSC"
        assert container.tracking_source == "mock"
        assert container.detection_confidence == "manual"
        assert shipment is not None
        assert shipment.latest_eta is None
        assert shipment.current_milestone is None


def test_linking_container_updates_shipment_tracking_status(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567", "carrier_code": "MSC", "shipment_id": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["container_no"] == "MSCU1234567"
    assert body["current_milestone"] == "Delivered"
    assert body["current_location"] == "Jamshedpur Plant"
    assert body["delay_status"] in {"delayed", "on_time", "early"}

    with SessionLocal() as db:
        shipment = db.get(Shipment, 1)
        container = db.scalar(select(Container).where(Container.container_no == "MSCU1234567"))
        assert shipment is not None
        assert container is not None
        assert shipment.latest_eta is not None
        assert shipment.current_eta == shipment.latest_eta
        assert shipment.current_milestone == "Delivered"
        assert shipment.last_tracking_update_at is not None


def test_repeated_link_does_not_duplicate_tracking_events(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    payload = {"container_no": "MSCU1234567", "carrier_code": "MSC", "shipment_id": 1}
    first = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["already_linked"] is False

    with SessionLocal() as db:
        first_event_ids = [
            row.id
            for row in db.scalars(
                select(TrackingEvent).order_by(
                    TrackingEvent.event_datetime,
                    TrackingEvent.event_type,
                )
            )
        ]
        first_linked_at = db.scalar(select(ShipmentContainer.linked_at))

    second = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json=payload,
    )
    assert second.status_code == 200
    assert second.json()["already_linked"] is True

    with SessionLocal() as db:
        second_event_ids = [
            row.id
            for row in db.scalars(
                select(TrackingEvent).order_by(
                    TrackingEvent.event_datetime,
                    TrackingEvent.event_type,
                )
            )
        ]
        second_linked_at = db.scalar(select(ShipmentContainer.linked_at))
        assert len(second_event_ids) == 13
        assert second_event_ids == first_event_ids
        assert second_linked_at == first_linked_at


def test_search_returns_linked_status_and_deterministic_timeline(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    link = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567", "carrier_code": "MSC", "shipment_id": 1},
    )
    assert link.status_code == 200

    first = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567"},
    )
    second = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    event_times = [event["event_datetime"] for event in first_body["events"]]
    assert event_times == sorted(event_times)
    assert first_body["events"] == second_body["events"]
    assert first_body["linked_statuses"][0]["shipment_ref"] == "SHIP-CONTAINER-1"
    assert first_body["linked_statuses"][0]["already_linked"] is True


def test_dcsa_link_repeated_payload_does_not_duplicate_events(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, SessionLocal = client_and_session

    class FixedDcsaProvider:
        def search_container(self, container_no: str, carrier_code: str) -> dict[str, object]:
            return {"container_no": container_no, "carrier_code": carrier_code, "status": "found"}

        def get_tracking_events(
            self,
            container_no: str,
            carrier_code: str,
        ) -> list[TrackingEventOut]:
            return [
                TrackingEventOut(
                    event_type="Vessel arrival",
                    event_datetime=datetime(2026, 5, 14, 8, tzinfo=UTC),
                    location_name="Paradip Port",
                    location_code="INPRT",
                    transport_mode="ocean",
                    vessel_name="MV Horizon",
                    voyage_no="042W",
                    source="dcsa",
                    raw_payload={
                        "equipmentReference": container_no,
                        "carrierCode": carrier_code,
                        "sequence": 1,
                    },
                )
            ]

    monkeypatch.setattr(
        "app.modules.tracking.service.get_tracking_provider",
        lambda source: FixedDcsaProvider(),
    )
    payload = {
        "container_no": "MSCU1234567",
        "carrier_code": "MSC",
        "shipment_id": 1,
        "tracking_source": "dcsa",
    }
    first = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json=payload,
    )
    second = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200

    with SessionLocal() as db:
        assert len(list(db.scalars(select(TrackingEvent)))) == 1
        shipment = db.get(Shipment, 1)
        assert shipment is not None
        assert shipment.latest_eta is not None
        assert shipment.latest_eta.date().isoformat() == "2026-05-14"


def test_dcsa_provider_maps_tracking_events() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "equipmentEventTypeCode": "GTIN",
                        "eventDateTime": "2026-05-01T10:00:00Z",
                        "eventLocation": {
                            "locationName": "Nhava Sheva Terminal",
                            "UNLocationCode": "INNSA",
                        },
                    },
                    {
                        "shipmentEventTypeCode": "CONF",
                        "eventDateTime": "2026-05-02T10:00:00Z",
                        "location": {"name": "Carrier desk", "UNLocationCode": "INNSA"},
                    },
                    {
                        "transportEventTypeCode": "ARRI",
                        "eventDateTime": "2026-05-10T12:00:00+05:30",
                        "transportCall": {
                            "modeOfTransport": "VESSEL",
                            "location": {"UNLocationCode": "INPRT"},
                            "vessel": {"name": "MV Horizon"},
                            "importVoyageNumber": "042W",
                        },
                    },
                    {
                        "journey_event": {"event_type": "Carrier-specific hold"},
                        "eventDateTime": "2026-05-11T09:00:00Z",
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DcsaTrackingProvider(
        base_url="https://tracking.example.test",
        api_key="test-key",
        client=client,
    )

    search = provider.search_container("MSCU1234567", "MSC")
    events = provider.get_tracking_events("MSCU1234567", "MSC")

    assert search["status"] == "found"
    assert [event.event_type for event in events] == [
        "Gate in",
        "Confirmed",
        "Vessel arrival",
        "Carrier-specific hold",
    ]
    assert events[0].transport_mode == "port"
    assert events[2].transport_mode == "ocean"
    assert events[2].location_code == "INPRT"
    assert events[2].vessel_name == "MV Horizon"
    assert events[2].voyage_no == "042W"
    assert events[2].event_datetime.isoformat() == "2026-05-10T06:30:00+00:00"
    assert len(requests) == 1
    assert requests[0].url.params["equipmentReference"] == "MSCU1234567"
    assert requests[0].url.params["carrierCode"] == "MSC"
    assert requests[0].headers["Authorization"] == "Bearer test-key"


def test_dcsa_provider_requires_api_key() -> None:
    with pytest.raises(TrackingProviderConfigurationError):
        DcsaTrackingProvider(base_url="https://tracking.example.test")


def test_dcsa_provider_empty_data_is_clean_no_data_response() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    provider = DcsaTrackingProvider(
        base_url="https://tracking.example.test",
        api_key="test-key",
        client=client,
    )

    search = provider.search_container("MSCU1234567", "MSC")

    assert search["status"] == "not_found"
    assert provider.get_tracking_events("MSCU1234567", "MSC") == []


def test_dcsa_provider_retries_transient_errors() -> None:
    responses = [httpx.Response(503), httpx.Response(200, json=[])]

    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        response.request = request
        return response

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DcsaTrackingProvider(
        base_url="https://tracking.example.test",
        api_key="test-key",
        max_retries=1,
        retry_backoff_seconds=0,
        client=client,
    )

    assert provider.search_container("MSCU1234567", "MSC")["status"] == "not_found"
    assert responses == []


def test_dcsa_provider_returns_structured_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(401)
        response.request = request
        return response

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DcsaTrackingProvider(
        base_url="https://tracking.example.test",
        api_key="test-key",
        client=client,
    )

    with pytest.raises(TrackingProviderRequestError, match="status 401"):
        provider.search_container("MSCU1234567", "MSC")


def seed_tracking_data(db: Session) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant, role])
    db.flush()

    user = User(
        email="ops@test.local",
        full_name="Ops User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )

    plant = Plant(tenant_id=tenant.id, code="JAM", name="Jamshedpur", location="Jharkhand")
    material = Material(
        tenant_id=tenant.id,
        code="COAL",
        name="Coking Coal",
        category="coal",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    now = datetime.now(UTC)
    db.add(
        Shipment(
            tenant_id=tenant.id,
            shipment_id="SHIP-CONTAINER-1",
            material_id=material.id,
            plant_id=plant.id,
            supplier_name="Supplier A",
            quantity_mt=Decimal("1000"),
            vessel_name="MV Original",
            imo_number=None,
            mmsi=None,
            origin_port="Nhava Sheva",
            destination_port="Jamshedpur",
            planned_eta=now + timedelta(days=6),
            current_eta=now + timedelta(days=6),
            eta_confidence=Decimal("80"),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=now,
        )
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Tenant-Slug": "tenant-a",
    }
