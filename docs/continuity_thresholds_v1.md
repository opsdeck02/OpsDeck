# Continuity Thresholds V1

Continuity Thresholds let tenant admins calibrate when OpsDeck marks a plant-material context as warning or critical.

Route:

```text
Admin -> Operational Configuration -> Continuity Thresholds
```

## Purpose

Thresholds are operational continuity boundaries. They are not procurement workflows, supplier settings, or interruption economics.

The configuration answers:

- When should OpsDeck start warning about a material?
- When should the material be considered operationally critical?
- Does the material require protected reserve stock?
- How early should projected stockout risk be escalated?

## Fields

`warning_days` is the earlier warning boundary. If days of cover is at or below this value, OpsDeck can classify the material as a warning risk.

`threshold_days` is the critical boundary. In the UI this is labeled **Critical threshold**. If days of cover is at or below this value, OpsDeck can classify the material as critical.

`warning_days` must be greater than or equal to `threshold_days`.

## Protected Reserve

Protected reserve fields are optional:

- `minimum_buffer_stock_days`
- `minimum_buffer_stock_mt`

They describe a client-specific operating buffer that should not be consumed in normal operations. V1 stores these values on the existing `plant_material_thresholds` record.

The rule engine consumes both fields:

- If `days_of_cover <= minimum_buffer_stock_days`, OpsDeck elevates the material to at least a medium protected reserve warning and adds a reason explaining that the protected reserve days threshold was breached.
- If `usable_quantity <= minimum_buffer_stock_mt`, OpsDeck elevates the material to at least a medium protected reserve warning and adds a reason explaining that the protected reserve quantity threshold was breached.

## Projected Stockout Alert Horizon

`stockout_alert_horizon_days` controls when OpsDeck emits a projected stockout risk for the configured plant-material context.

If projected exhaustion is within the configured horizon, OpsDeck emits a `projected_stockout` risk and includes the configured horizon in the reason chain. If no value is configured, OpsDeck preserves the existing fallback horizon of 48 hours.

## Consumed Fields

The backend consumes the fields as follows:

- `warning_days`: stock-cover status and signal-engine days-of-cover severity use this as the warning boundary.
- `threshold_days`: stock-cover status and signal-engine days-of-cover severity use this as the critical boundary.
- `minimum_buffer_stock_days`: signal-engine inventory rules elevate protected reserve risk when days of cover breaches this buffer.
- `minimum_buffer_stock_mt`: signal-engine inventory rules elevate protected reserve risk when usable quantity breaches this buffer.
- `stockout_alert_horizon_days`: signal-engine projected stockout rules use this horizon instead of the 48-hour fallback.

## Backend Behavior

The admin endpoint is tenant-scoped and tenant-admin only:

```text
GET /api/v1/impact/continuity-thresholds?plant_id=&material_id=
PUT /api/v1/impact/continuity-thresholds
```

The `PUT` endpoint upserts a single threshold record for the tenant, plant, and material. Missing configuration returns `null` from `GET`.
