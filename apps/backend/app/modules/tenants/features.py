from __future__ import annotations

TENANT_PLAN_VALUES = ("pilot", "paid", "enterprise")
AUTOMATED_DATA_SOURCES = "automated_data_sources"


def normalize_plan_tier(plan_tier: str) -> str:
    normalized = plan_tier.strip().lower()
    if normalized not in TENANT_PLAN_VALUES:
        raise ValueError("Invalid tenant plan. Expected pilot, paid, or enterprise.")
    return normalized


def automated_data_sources_enabled(plan_tier: str) -> bool:
    return normalize_plan_tier(plan_tier) in {"paid", "enterprise"}


def build_capabilities(plan_tier: str) -> dict[str, bool]:
    normalized = normalize_plan_tier(plan_tier)
    return {
        AUTOMATED_DATA_SOURCES: automated_data_sources_enabled(normalized),
    }
