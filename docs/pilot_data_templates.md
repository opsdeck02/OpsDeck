# OpsDeck Pilot Data Templates

Use these lightweight templates for a guided steel/heavy manufacturing pilot. CSV or XLSX files are fine. Keep plant, material, and supplier names consistent across files.

## 1. Stock Snapshot

Required columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Plant | Plant/site name or code | JAM |
| Material | Material name or code | COKING_COAL |
| Snapshot Time | Time the stock position was valid | 2026-06-15 08:00 |
| Available Stock | Stock that can be consumed | 1200 |
| Daily Consumption | Average daily consumption | 150 |

Optional columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Closing Stock | Total stock position | 1350 |
| Quality Hold | Quantity blocked for quality | 100 |
| Blocked Stock | Quantity not usable | 50 |
| UOM | Unit of measure | MT |

Example row:

| Plant | Material | Snapshot Time | Available Stock | Daily Consumption | Quality Hold |
| --- | --- | --- | ---: | ---: | ---: |
| JAM | COKING_COAL | 2026-06-15 08:00 | 1200 | 150 | 100 |

## 2. Inbound Shipments

Required columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Shipment ID | Unique shipment reference | RK-2026-001 |
| Plant | Receiving plant/site | JAM |
| Material | Material being received | COKING_COAL |
| Quantity | Inbound quantity | 500 |
| ETA | Expected arrival at plant | 2026-06-19 |

Optional columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Supplier Name | Supplier/vendor | ABC Minerals |
| PO No | Purchase order | PO-4481 |
| Rake No | Rail/rake reference | Rake-77 |
| Truck No | Truck reference | MH-01-AB-1234 |
| LR No | Logistics receipt | LR-9901 |
| Dispatch Date | Dispatch date | 2026-06-13 |
| Gate Entry Date | Gate entry date | 2026-06-19 |

Example row:

| Shipment ID | Plant | Material | Quantity | ETA | Supplier Name | Rake No |
| --- | --- | --- | ---: | --- | --- | --- |
| RK-2026-001 | JAM | COKING_COAL | 500 | 2026-06-19 | ABC Minerals | Rake-77 |

ETA is required because OpsDeck cannot judge whether inbound protects production without arrival timing.

## 3. Continuity Thresholds

Required columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Plant | Plant/site name or code | JAM |
| Material | Material name or code | COKING_COAL |
| Critical Days | Days of cover where risk is critical | 3 |
| Warning Days | Days of cover where risk needs attention | 7 |

Optional columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Minimum Stock | Minimum physical stock | 450 |
| Safety Stock | Safety stock target | 700 |
| Reorder Level | Reorder trigger | 900 |

Example row:

| Plant | Material | Critical Days | Warning Days | Safety Stock |
| --- | --- | ---: | ---: | ---: |
| JAM | COKING_COAL | 3 | 7 | 700 |

Thresholds are required before OpsDeck can classify material risk as Critical, High, Medium, or Low.

## 4. Incident History

Required columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Incident Date | Date of known disruption | 2026-05-12 |
| Plant | Affected plant/site | JAM |
| Material | Affected material | COKING_COAL |
| Incident Type | Short description | Stockout |

Recommended columns:

| Column | Meaning | Example |
| --- | --- | --- |
| Impact | Operational impact | Blast furnace slowdown |
| Root Cause | Known reason | Late rake arrival |
| Notes | Any context | ETA changed twice |

Example row:

| Incident Date | Plant | Material | Incident Type | Impact | Root Cause |
| --- | --- | --- | --- | --- | --- |
| 2026-05-12 | JAM | COKING_COAL | Stockout | Production slowdown | Late rake arrival |

Incident Replay is strongest when historical stock snapshots, thresholds, and inbound shipment records exist before the incident date.
