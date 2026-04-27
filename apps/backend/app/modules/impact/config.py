from __future__ import annotations

from decimal import Decimal

# Safe defaults for V1. This file is intentionally config-driven so it can be
# swapped later for tenant-managed settings without changing the calculation API.
# Manual updates to value-per-MT and criticality assumptions should be made here
# until a tenant-configurable admin flow is introduced.
DEFAULT_VALUE_PER_MT = Decimal("250.00")
DEFAULT_CRITICALITY_MULTIPLIER = Decimal("1.00")

MATERIAL_IMPACT_DEFAULTS: dict[str, dict[str, Decimal]] = {
    "COKING_COAL": {
        "value_per_mt": Decimal("320.00"),
        "criticality_multiplier": Decimal("1.30"),
    },
    "PCI_COAL": {
        "value_per_mt": Decimal("280.00"),
        "criticality_multiplier": Decimal("1.15"),
    },
    "IRON_ORE_FINES": {
        "value_per_mt": Decimal("140.00"),
        "criticality_multiplier": Decimal("1.05"),
    },
    "LIMESTONE": {
        "value_per_mt": Decimal("75.00"),
        "criticality_multiplier": Decimal("0.90"),
    },
}

PLANT_MATERIAL_IMPACT_DEFAULTS: dict[tuple[str, str], dict[str, Decimal]] = {}


def get_impact_config(plant_code: str, material_code: str) -> dict[str, Decimal]:
    scoped = PLANT_MATERIAL_IMPACT_DEFAULTS.get((plant_code.upper(), material_code.upper()))
    if scoped is not None:
        return scoped

    material = MATERIAL_IMPACT_DEFAULTS.get(material_code.upper())
    if material is not None:
        return material

    return {
        "value_per_mt": DEFAULT_VALUE_PER_MT,
        "criticality_multiplier": DEFAULT_CRITICALITY_MULTIPLIER,
    }
