from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from hashlib import sha256

from app.modules.tracking.schemas import VesselPositionOut


class VesselTrackingProvider(ABC):
    @abstractmethod
    def get_vessel_position(self, vessel_name: str) -> VesselPositionOut | None:
        raise NotImplementedError


class MockAISProvider(VesselTrackingProvider):
    source = "mock_ais"

    def get_vessel_position(self, vessel_name: str) -> VesselPositionOut | None:
        normalized = vessel_name.strip()
        if not normalized:
            return None
        seed = int(sha256(normalized.upper().encode()).hexdigest()[:12], 16)
        lat = 5 + (seed % 2500) / 100
        lon = 55 + ((seed // 100) % 4500) / 100
        speed = 8 + ((seed // 10_000) % 100) / 10
        heading = (seed // 1_000_000) % 360
        return VesselPositionOut(
            vessel_name=normalized,
            lat=round(lat, 4),
            lon=round(lon, 4),
            speed_knots=round(speed, 1),
            heading_degrees=float(heading),
            timestamp=datetime(2026, 5, 6, 8, 0, tzinfo=UTC),
            source=self.source,
            is_mock=True,
        )


def get_vessel_tracking_provider(source: str = "mock_ais") -> VesselTrackingProvider:
    normalized = source.strip().lower()
    if normalized == "mock_ais":
        return MockAISProvider()
    raise ValueError(f"Unsupported vessel tracking provider: {source}")
