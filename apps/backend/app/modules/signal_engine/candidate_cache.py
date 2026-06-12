from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.modules.rules.engine import RiskCandidate

logger = logging.getLogger(__name__)

DEFAULT_SIGNAL_CANDIDATE_CACHE_TTL_SECONDS = 60


@dataclass
class SignalCandidateCacheEntry:
    expires_at: float
    candidates: list[RiskCandidate]


_CACHE: dict[int, SignalCandidateCacheEntry] = {}


def get_cached_signal_candidates(
    tenant_id: int,
    compute: Callable[[], list[RiskCandidate]],
    *,
    ttl_seconds: int = DEFAULT_SIGNAL_CANDIDATE_CACHE_TTL_SECONDS,
    bypass: bool = False,
) -> list[RiskCandidate]:
    if bypass:
        logger.debug("signal candidate cache bypass", extra={"tenant_id": tenant_id})
        return clone_candidates(strip_cached_enrichment(compute()))

    now = time.monotonic()
    entry = _CACHE.get(tenant_id)
    if entry is not None and entry.expires_at > now:
        logger.debug("signal candidate cache hit", extra={"tenant_id": tenant_id})
        return clone_candidates(entry.candidates)

    logger.debug("signal candidate cache miss", extra={"tenant_id": tenant_id})
    candidates = strip_cached_enrichment(compute())
    _CACHE[tenant_id] = SignalCandidateCacheEntry(
        expires_at=now + ttl_seconds,
        candidates=clone_candidates(candidates),
    )
    return clone_candidates(candidates)


def invalidate_signal_candidate_cache(tenant_id: int) -> None:
    removed = _CACHE.pop(tenant_id, None)
    logger.debug(
        "signal candidate cache invalidated",
        extra={"tenant_id": tenant_id, "removed": removed is not None},
    )


def clear_signal_candidate_cache() -> None:
    _CACHE.clear()


def clone_candidates(candidates: list[RiskCandidate]) -> list[RiskCandidate]:
    return [candidate.model_copy(deep=True) for candidate in candidates]


def strip_cached_enrichment(candidates: list[RiskCandidate]) -> list[RiskCandidate]:
    return [
        candidate.model_copy(
            deep=True,
            update={
                "explainability": None,
                "operational_interruption_impact": None,
                "operational_recommendations": [],
                "configuration_completeness": None,
                "operational_trust": None,
            },
        )
        for candidate in candidates
    ]
