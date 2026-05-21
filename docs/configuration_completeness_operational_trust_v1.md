# Configuration Completeness & Operational Trust V1

OpsDeck now separates two ideas that can look similar in a dashboard:

- **Risk existence** means a continuity exposure was detected.
- **Risk precision** means OpsDeck has enough calibrated operational assumptions and fresh signals to trust the exact reasoning behind that exposure.

This layer does not suppress risks when confidence is weak. It attaches deterministic trust and completeness context so users can see where operational precision is strong, partial, or weak.

## Configuration Completeness

Configuration completeness is scored for each plant-material context. V1 uses deterministic area weights:

- `continuity_thresholds`: 20%
- `interruption_impact`: 20%
- `product_process_dependency`: 20%
- `shipment_inbound_trust`: 15%
- `supplier_context`: 10%
- `inventory_visibility`: 10%
- `shipment_visibility`: 5%

The score maps to confidence bands:

- `>= 85`: high
- `>= 65`: moderate
- `>= 40`: low
- otherwise: unknown

## Area Rules

`continuity_thresholds` is complete when a plant-material threshold exists.

`interruption_impact` is complete when an active production interruption impact config exists.

`product_process_dependency` is complete when material-process dependency and process-product mix both exist. If only the material-process link exists, the area is partial.

`shipment_inbound_trust` is complete when a shipment inbound trust config exists for the plant-material context.

`supplier_context` uses existing shipment evidence. It does not require manual supplier configuration. V1 treats three or more supplier-context shipment samples as complete, one or two as partial, and none as missing.

`inventory_visibility` uses the current inventory continuity result. Fresh visibility with acceptable cover confidence is complete; stale, critical, or low-confidence visibility degrades precision.

`shipment_visibility` is complete when active inbound shipments have tracking or update timestamps.

## Operational Trust

Operational trust is attached per risk. It starts from the configuration completeness score, then applies deterministic penalties and boosts from the actual risk context.

Trust penalties include:

- missing interruption config
- missing product/process dependency
- missing shipment trust calibration
- stale inventory visibility
- weak inbound visibility
- visibility uncertainty in inbound protection
- insufficient supplier-context history
- fallback interruption economics

Trust boosts include:

- fully calculated interruption impact
- configured process dependency
- configured shipment trust calibration
- strong visibility confidence
- strong supplier-context history

The final operational trust score is clamped to `0–100` and mapped to the same high, moderate, low, or unknown precision bands.

## Fallback Reasoning

Fallback logic is explicit in reason chains. For example:

- “Interruption impact uses fallback weighted output value because no process dependency is configured.”
- “Shipment trust calibration exists for this plant-material context.”
- “Supplier-context evidence insufficient; neutral reliability fallback may apply.”

This prevents false precision while preserving continuity risk detection.

## API Exposure

Signal Engine risk candidates can now include:

- `configuration_completeness`
- `operational_trust`

These are additive fields and do not change the existing risk formulas or existing response shape.

## Product Boundary

This layer is not machine learning, workflow automation, or remediation. It does not create tasks, change thresholds, or recommend procurement. It only explains how complete and trustworthy the operational assumptions behind a risk are.
