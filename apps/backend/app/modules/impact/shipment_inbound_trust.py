from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ShipmentInboundTrustConfig


def get_active_shipment_inbound_trust_config(
    db: Session,
    *,
    tenant_id: int,
    plant_id: int,
    material_id: int,
) -> ShipmentInboundTrustConfig | None:
    return db.scalar(
        select(ShipmentInboundTrustConfig)
        .where(
            ShipmentInboundTrustConfig.tenant_id == tenant_id,
            ShipmentInboundTrustConfig.plant_id == plant_id,
            ShipmentInboundTrustConfig.material_id == material_id,
            ShipmentInboundTrustConfig.is_active.is_(True),
        )
        .order_by(ShipmentInboundTrustConfig.updated_at.desc())
    )
