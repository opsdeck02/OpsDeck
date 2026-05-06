from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import sleep
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.modules.tracking.schemas import TrackingEventOut


class TrackingProviderConfigurationError(ValueError):
    pass


class TrackingProviderRequestError(ValueError):
    pass


class TrackingProvider(ABC):
    @abstractmethod
    def search_container(self, container_no: str, carrier_code: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_tracking_events(self, container_no: str, carrier_code: str) -> list[TrackingEventOut]:
        raise NotImplementedError


class MockTrackingProvider(TrackingProvider):
    source = "mock"

    def search_container(self, container_no: str, carrier_code: str) -> dict[str, Any]:
        return {
            "container_no": container_no,
            "carrier_code": carrier_code,
            "source": self.source,
            "status": "found",
        }

    def get_tracking_events(self, container_no: str, carrier_code: str) -> list[TrackingEventOut]:
        seed = int(sha256(f"{container_no}:{carrier_code}".encode()).hexdigest()[:8], 16)
        base_day = 1 + seed % 20
        now = datetime(2026, 5, base_day, 8, 0, tzinfo=UTC)
        vessel = "MV Mock Horizon"
        voyage = f"{carrier_code[:3].upper()}42E"
        raw_base = {
            "container_no": container_no,
            "carrier_code": carrier_code,
            "provider": self.source,
        }
        timeline = [
            ("Gate in", now - timedelta(days=17), "Nhava Sheva Terminal", "INNSA", "port"),
            ("Loaded on vessel", now - timedelta(days=16), "Nhava Sheva", "INNSA", "ocean"),
            ("Vessel departure", now - timedelta(days=15), "Nhava Sheva", "INNSA", "ocean"),
            ("Transshipment", now - timedelta(days=9), "Colombo", "LKCMB", "ocean"),
            ("Vessel arrival", now + timedelta(days=2), "Paradip Port", "INPRT", "port"),
            ("Discharged", now + timedelta(days=3), "Paradip Port", "INPRT", "port"),
            ("Customs hold", now + timedelta(days=3, hours=4), "Paradip Customs", "INPRT", "port"),
            ("Available for pickup", now + timedelta(days=4), "Paradip CFS", "INPRT", "port"),
            ("Gate out", now + timedelta(days=5), "Paradip CFS", "INPRT", "truck"),
            (
                "Rail departure",
                now + timedelta(days=5, hours=6),
                "Paradip Rail Yard",
                "INPRT",
                "rail",
            ),
            ("Rail arrival", now + timedelta(days=7), "Jamshedpur Rail Terminal", "INIXW", "rail"),
            (
                "Truck appointment",
                now + timedelta(days=7, hours=8),
                "Jamshedpur Plant Gate",
                "INIXW",
                "truck",
            ),
            ("Delivered", now + timedelta(days=8), "Jamshedpur Plant", "INIXW", "truck"),
        ]
        return [
            TrackingEventOut(
                event_type=event_type,
                event_datetime=event_time,
                location_name=location_name,
                location_code=location_code,
                transport_mode=transport_mode,
                vessel_name=vessel if transport_mode in {"ocean", "port"} else None,
                voyage_no=voyage if transport_mode in {"ocean", "port"} else None,
                source=self.source,
                raw_payload={**raw_base, "sequence": index, "event": event_type},
            )
            for index, (
                event_type,
                event_time,
                location_name,
                location_code,
                transport_mode,
            ) in enumerate(timeline, start=1)
        ]


class DcsaTrackingProvider(TrackingProvider):
    source = "dcsa"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        events_path: str = "/v2/events",
        timeout_seconds: int = 20,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.25,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise TrackingProviderConfigurationError("DCSA tracking provider is not configured")
        if not api_key:
            raise TrackingProviderConfigurationError("DCSA tracking API key is not configured")
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.events_path = events_path
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0, retry_backoff_seconds)
        self.client = client
        self._payload_cache: dict[tuple[str, str], dict[str, Any] | list[Any]] = {}

    def search_container(self, container_no: str, carrier_code: str) -> dict[str, Any]:
        payload = self._fetch_events_payload(container_no, carrier_code)
        events = self._events_from_payload(payload)
        return {
            "container_no": container_no,
            "carrier_code": carrier_code,
            "source": self.source,
            "status": "found" if events else "not_found",
            "event_count": len(events),
        }

    def get_tracking_events(self, container_no: str, carrier_code: str) -> list[TrackingEventOut]:
        payload = self._fetch_events_payload(container_no, carrier_code)
        return [
            event
            for event in (
                self._tracking_event_from_payload(raw_event, index)
                for index, raw_event in enumerate(self._events_from_payload(payload), start=1)
            )
            if event is not None
        ]

    def _fetch_events_payload(
        self,
        container_no: str,
        carrier_code: str,
    ) -> dict[str, Any] | list[Any]:
        key = (container_no, carrier_code)
        if key in self._payload_cache:
            return self._payload_cache[key]
        url = urljoin(self.base_url, self.events_path.lstrip("/"))
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        params = {
            "equipmentReference": container_no,
            "carrierCode": carrier_code,
        }
        payload = self._request_json(url, headers, params)
        if not isinstance(payload, dict | list):
            raise TrackingProviderRequestError("DCSA tracking response was not JSON")
        self._payload_cache[key] = payload
        return payload

    def _request_json(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> dict[str, Any] | list[Any]:
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                if self.client is not None:
                    response = self.client.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=self.timeout_seconds,
                    )
                else:
                    response = httpx.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=self.timeout_seconds,
                    )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                if attempt == attempts - 1:
                    raise TrackingProviderRequestError("DCSA tracking request timed out") from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code < 500 or attempt == attempts - 1:
                    raise TrackingProviderRequestError(
                        f"DCSA tracking request failed with status {status_code}"
                    ) from exc
            except httpx.HTTPError as exc:
                if attempt == attempts - 1:
                    raise TrackingProviderRequestError("DCSA tracking request failed") from exc
            except ValueError as exc:
                raise TrackingProviderRequestError(
                    "DCSA tracking response was not valid JSON"
                ) from exc
            if self.retry_backoff_seconds:
                sleep(self.retry_backoff_seconds * (attempt + 1))
        raise TrackingProviderRequestError("DCSA tracking request failed")

    def _events_from_payload(self, payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [event for event in payload if isinstance(event, dict)]
        for key in ("events", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [event for event in value if isinstance(event, dict)]
        return []

    def _tracking_event_from_payload(
        self,
        raw_event: dict[str, Any],
        index: int,
    ) -> TrackingEventOut | None:
        event_datetime = parse_event_datetime(raw_event)
        if event_datetime is None:
            return None
        event_type = map_dcsa_event_type(raw_event)
        location = first_dict(raw_event, "eventLocation", "location")
        transport_call = raw_event.get("transportCall")
        transport_call = transport_call if isinstance(transport_call, dict) else {}
        transport_location = first_dict(transport_call, "eventLocation", "location")
        vessel = first_dict(transport_call, "vessel") or first_dict(raw_event, "vessel")
        mode = transport_mode_from_dcsa(raw_event, event_type)
        raw_payload = {**raw_event, "provider": self.source, "sequence": index}
        return TrackingEventOut(
            event_type=event_type,
            event_datetime=event_datetime,
            location_name=string_or_none(
                location.get("locationName")
                or location.get("name")
                or transport_location.get("locationName")
                or transport_location.get("name")
                or transport_call.get("UNLocationCode")
            ),
            location_code=string_or_none(
                location.get("UNLocationCode")
                or location.get("locationCode")
                or transport_location.get("UNLocationCode")
                or transport_location.get("locationCode")
                or transport_call.get("UNLocationCode")
            ),
            transport_mode=mode,
            vessel_name=string_or_none(
                vessel.get("vesselName")
                or vessel.get("name")
                or transport_call.get("vesselName")
                or raw_event.get("vesselName")
            ),
            voyage_no=string_or_none(
                transport_call.get("exportVoyageNumber")
                or transport_call.get("importVoyageNumber")
                or raw_event.get("exportVoyageNumber")
                or raw_event.get("voyageNumber")
            ),
            source=self.source,
            raw_payload=raw_payload,
        )


def parse_event_datetime(raw_event: dict[str, Any]) -> datetime | None:
    value = first_string(
        raw_event,
        "eventDateTime",
        "eventCreatedDateTime",
        "eventTime",
        "actualTimeOfArrival",
        "plannedTimeOfArrival",
        "actualTimeOfDeparture",
        "plannedTimeOfDeparture",
    )
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def map_dcsa_event_type(raw_event: dict[str, Any]) -> str:
    journey_event = first_dict(raw_event, "journey_event", "journeyEvent")
    code = (
        first_string(
            raw_event,
            "equipmentEventTypeCode",
            "transportEventTypeCode",
            "shipmentEventTypeCode",
            "eventTypeCode",
        )
        or first_string(
            journey_event,
            "equipmentEventTypeCode",
            "transportEventTypeCode",
            "shipmentEventTypeCode",
            "event_type_code",
            "eventTypeCode",
            "code",
        )
        or ""
    ).upper()
    event_type = first_string(raw_event, "eventType", "eventTypeName") or first_string(
        journey_event,
        "event_type",
        "eventType",
        "name",
    )
    mapping = {
        "GTIN": "Gate in",
        "GTOT": "Gate out",
        "LOAD": "Loaded on vessel",
        "DISC": "Discharged",
        "DEPA": "Vessel departure",
        "ARRI": "Vessel arrival",
        "INSP": "Customs hold",
        "AVPU": "Available for pickup",
        "PICK": "Gate out",
        "DROP": "Gate in",
        "RDEP": "Rail departure",
        "RARR": "Rail arrival",
        "DELV": "Delivered",
        "RECE": "Received",
        "PENC": "Pending confirmation",
        "CONF": "Confirmed",
        "REJE": "Rejected",
        "CANC": "Cancelled",
    }
    if code in mapping:
        return mapping[code]
    if event_type:
        return event_type
    return code or "Tracking event"


def transport_mode_from_dcsa(raw_event: dict[str, Any], event_type: str) -> str:
    mode = (
        first_string(raw_event, "modeOfTransport", "transportMode")
        or nested_string(raw_event, "transportCall", "modeOfTransport")
        or ""
    ).lower()
    if "rail" in mode:
        return "rail"
    if "truck" in mode or "road" in mode:
        return "truck"
    if "barge" in mode or "inland water" in mode:
        return "barge"
    if "vessel" in mode or "sea" in mode or "ocean" in mode:
        return "ocean"
    if event_type in {"Rail departure", "Rail arrival"}:
        return "rail"
    if event_type in {"Truck appointment", "Delivered"}:
        return "truck"
    if event_type in {"Loaded on vessel", "Vessel departure", "Vessel arrival"}:
        return "ocean"
    return "port"


def first_string(raw_event: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw_event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def nested_string(raw_event: dict[str, Any], parent_key: str, child_key: str) -> str | None:
    parent = raw_event.get(parent_key)
    if not isinstance(parent, dict):
        return None
    value = parent.get(child_key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def first_dict(raw_event: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = raw_event.get(key)
        if isinstance(value, dict):
            return value
    return {}


def string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def get_tracking_provider(source: str = "mock") -> TrackingProvider:
    normalized = source.strip().lower()
    if normalized == "mock":
        return MockTrackingProvider()
    if normalized == "dcsa":
        return DcsaTrackingProvider(
            base_url=settings.tracking_dcsa_base_url,
            api_key=settings.tracking_dcsa_api_key,
            events_path=settings.tracking_dcsa_events_path,
            timeout_seconds=settings.tracking_dcsa_timeout_seconds,
            max_retries=settings.tracking_dcsa_max_retries,
        )
    raise ValueError(f"Unsupported tracking provider: {source}")
