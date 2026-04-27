TEMPLATES: dict[str, str] = {
    "shipment": "\n".join(
        [
            ",".join(
                [
                    "shipment_id",
                    "plant_code",
                    "material_code",
                    "supplier_name",
                    "quantity_mt",
                    "planned_eta",
                    "current_eta",
                    "current_state",
                    "latest_update_at",
                    "vessel_name",
                    "imo_number",
                    "mmsi",
                    "origin_port",
                    "destination_port",
                    "eta_confidence",
                ]
            ),
            ",".join(
                [
                    "SHP-COAL-001",
                    "JAM",
                    "COKING_COAL",
                    "BHP Mitsubishi Alliance",
                    "74000",
                    "2026-04-20T08:00:00Z",
                    "2026-04-21T08:00:00Z",
                    "in_transit",
                    "2026-04-15T09:00:00Z",
                    "MV Eastern Furnace",
                    "9876543",
                    "419000123",
                    "Hay Point",
                    "Paradip",
                    "82.5",
                ]
            ),
        ]
    ),
    "stock": "\n".join(
        [
            "plant_code,material_code,on_hand_mt,quality_held_mt,available_to_consume_mt,daily_consumption_mt,snapshot_time",
            "JAM,COKING_COAL,180000,10000,170000,24000,2026-04-15T08:00:00Z",
        ]
    ),
    "threshold": "\n".join(
        [
            "plant_code,material_code,threshold_days,warning_days",
            "JAM,COKING_COAL,7,10",
        ]
    ),
}
