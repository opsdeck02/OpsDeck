from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from app.modules.tracking.schemas import TrackingEventOut


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


def get_tracking_provider(source: str = "mock") -> TrackingProvider:
    if source != "mock":
        raise ValueError(f"Unsupported tracking provider: {source}")
    return MockTrackingProvider()
