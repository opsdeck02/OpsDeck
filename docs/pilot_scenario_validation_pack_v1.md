# Pilot Scenario Validation Pack V1

This pack validates OpsDeck continuity reasoning against realistic pilot situations before customer use. It is not demo decoration and does not add product features. The scenarios prove that the backend engines keep physical inbound quantity, operational trust, ETA behavior, thresholds, supplier context, and interruption impact explainable and deterministic.

## Safety Boundary

Across all scenarios, OpsDeck must not:

- Treat physical inbound quantity as missing when visibility confidence is weak.
- Generate reorder, buy, purchase approval, or automatic procurement actions.
- Panic on a stable ocean shipment only because it has not updated recently.
- Suppress risk creation just because configuration is incomplete.
- Present fallback economics as high-precision operational impact.

## Scenario 1: Ocean Shipment Stable Visibility

Operational situation:
An ocean/import shipment has not updated for 48 hours, but ETA remains stable and the profile is ocean.

Why it matters:
Ocean shipments can have longer normal visibility gaps than inland movements.

Expected OpsDeck behavior:
Visibility confidence remains high, most inbound protection remains trusted, and inbound delay against cover does not apply when cover is normal.

Should not happen:
OpsDeck should not escalate, imply material disappeared, or generate procurement-style action.

Engine layers involved:
Visibility Confidence, ETA Confidence Behavior, Inbound Delay vs Cover Intelligence, Action Recommendation.

## Scenario 2: Inland Shipment Degraded

Operational situation:
An inland shipment has stale visibility, material ETA drift, and near-plant/final-mile context.

Why it matters:
A 12-hour ETA drift near a plant is more serious than the same drift at sea.

Expected OpsDeck behavior:
Visibility confidence degrades, trusted inbound protection weakens, inbound delay against cover escalates when cover is tight, and actions focus on confirming inland movement or validating ETA.

Should not happen:
OpsDeck should not treat the physical shipment quantity as gone.

Engine layers involved:
Visibility Confidence, ETA Confidence Behavior, Inbound Delay vs Cover Intelligence, Action Recommendation.

## Scenario 3: Imported Critical Material Early Warning

Operational situation:
A critical/import-dependent material has long configured warning and critical thresholds.

Why it matters:
Generic short fallback thresholds are too late for some industrial import materials.

Expected OpsDeck behavior:
Risk is generated earlier than fallback thresholds, and the reason chain shows configured thresholds were used.

Should not happen:
OpsDeck should not silently fall back to generic timing when configured thresholds exist.

Engine layers involved:
Continuity Thresholds, Rule Engine.

## Scenario 4: Protected Reserve Breach

Operational situation:
A material has protected reserve days or quantity configured, and available stock breaches that reserve.

Why it matters:
Some materials should never consume below a protected operating buffer.

Expected OpsDeck behavior:
A reserve warning is created or the continuity risk is elevated, with reasons explaining the reserve breach.

Should not happen:
OpsDeck should not hide reserve exposure just because normal warning/critical timing has not been crossed.

Engine layers involved:
Continuity Thresholds, Rule Engine.

## Scenario 5: Physical Inbound Exists But Trusted Protection Is Weak

Operational situation:
Shipment quantity exists physically, but visibility confidence and trusted protection are weak.

Why it matters:
Users need to know the shipment still exists, while understanding that it is not fully reliable for continuity protection.

Expected OpsDeck behavior:
Physical inbound quantity remains unchanged, trusted inbound protection is reduced, uncertainty is shown separately, and the action is verify inbound or validate tracking.

Should not happen:
OpsDeck should not generate reorder language or imply missing material.

Engine layers involved:
Visibility Confidence, Inbound Delay vs Cover Intelligence, Action Recommendation.

## Scenario 6: Product / Process Dependency Impact

Operational situation:
A material is linked to a production process, and that process has a product mix.

Why it matters:
Interruption impact should reflect process/product exposure rather than only one manually blended output value.

Expected OpsDeck behavior:
Operational interruption impact uses product/process dependency data, and explainability includes affected process and product mix.

Should not happen:
OpsDeck should not use fallback blended value when active dependency data is available.

Engine layers involved:
Production Interruption Impact, Product & Process Dependency Modeling.

## Scenario 7: Missing Configuration Low Trust

Operational situation:
A continuity risk exists, but key operational configuration is missing.

Why it matters:
Risk existence and risk precision are different. Missing configuration weakens precision but should not hide risk.

Expected OpsDeck behavior:
Risk still generates, configuration completeness and operational trust are low or unknown, and missing assumptions are listed.

Should not happen:
OpsDeck should not suppress the risk or return fake precision.

Engine layers involved:
Signal Engine, Configuration Completeness & Operational Trust.

## Scenario 8: Substitution Reduces Impact

Operational situation:
A material/process dependency has meaningful substitution flexibility.

Why it matters:
Substitution can reduce the operational interruption exposure without changing the detected continuity risk.

Expected OpsDeck behavior:
Estimated interruption impact is lower than the no-substitution case, and explainability includes effective dependency after substitution weighting.

Should not happen:
OpsDeck should not change formulas or present substitution as an automatic action.

Engine layers involved:
Production Interruption Impact, Product & Process Dependency Modeling.

## Scenario 9: Weak Supplier Context

Operational situation:
A supplier has weak/repeated delay context for the same material/plant movement.

Why it matters:
Supplier reliability should influence inbound confidence mildly and contextually, without punishing the supplier globally.

Expected OpsDeck behavior:
Supplier reliability context is weak, trusted inbound protection is reduced mildly through the configured modifier, and operational actions may escalate supplier validation.

Should not happen:
OpsDeck should not automatically replace suppliers or create procurement automation.

Engine layers involved:
Supplier Reliability Context, Visibility Confidence, Inbound Delay vs Cover Intelligence, Action Recommendation.

## Test Location

The executable scenario pack lives in:

```text
apps/backend/tests/test_pilot_scenario_validation_pack.py
```

The tests use focused in-memory fixtures rather than changing production seed data.
