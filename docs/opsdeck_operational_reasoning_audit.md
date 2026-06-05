# OpsDeck Operational Reasoning Audit

Date: 2026-06-04  
Perspective: Head of Raw Material Planning, Plant Operations Head, Logistics Head, Supply Chain Director, Steel Plant COO  
Scope: operational correctness only. This is not a software architecture or code quality review.

## Executive Verdict

OpsDeck has the skeleton of a real continuity intelligence system. It thinks in the right broad categories: stock cover, inbound reliability, ETA movement, visibility confidence, supplier reliability, reserve breach, and production interruption impact.

But it does not yet reason like an experienced steel plant operations team.

It reasons like a disciplined rules analyst. A real operations team reasons with context: port conditions, vessel lineup, rake availability, material grade constraints, supplier concentration, production schedule, planned shutdowns, blending options, stock quality, alternate source readiness, contract commitments, and the credibility of each signal source.

OpsDeck today would be useful as a second-screen warning layer. It should not yet be treated as the final operational judgment engine.

Trust verdict:

- Plant planner: would trust parts of it, especially stock cover and explainability, but would challenge several risk calls.
- Logistics head: would value ETA/visibility alerts, but would question port, rail, and mode-specific reasoning.
- COO: would not yet trust impact numbers without calibration, but would like the direction.

Single most important reasoning improvement: link inbound protection to whether the shipment can realistically arrive before the material reaches critical/reserve thresholds.

Single most important missing data input: production schedule and real consumption plan by plant/process/material.

## Phase 1 - Operator Thinking Model

### How A Steel Plant Thinks About Stock Risk

A steel plant does not ask only, "How many days of stock do I have?"

It asks:

- How much usable stock is physically available?
- How much stock is quality-held, wet, off-grade, blocked, or reserved?
- How much stock is in the wrong yard, wrong bunker, wrong silo, wrong plant, or not reclaimable?
- What is today's actual consumption rate?
- Is tomorrow's production plan higher or lower than average consumption?
- Is there a maintenance shutdown coming?
- Is there a blend constraint?
- Is this material replaceable?
- Is the next inbound material actually reachable before we hit reserve?
- What is the confidence that inbound material will clear port, rail, and gate-in?

OpsDeck partially matches this. It subtracts quality hold/blocked stock and computes cover. It does not yet deeply understand schedule, location, blend constraints, or mode-specific arrival reality.

### How A Steel Plant Thinks About Material Shortage

Shortage is not binary. Operators think in bands:

- Comfortable stock
- Watch stock
- Reserve stock
- Critical stock
- Line-at-risk stock
- Production loss stock

They also separate:

- accounting stock
- physically usable stock
- quality-approved stock
- operationally reachable stock
- protected reserve stock

OpsDeck understands usable stock and protected reserve at a basic level. It does not yet fully reason about physical reachability, grade substitution, stockyard constraints, or production campaign dependency.

### How A Steel Plant Thinks About Supplier Reliability

A real planner does not treat supplier reliability as one score.

They ask:

- Does this supplier deliver this material reliably to this plant?
- Is the current shipment under the same contract/source/mine/route?
- Has the supplier failed recently?
- Are delays supplier-caused or logistics-caused?
- Does supplier paperwork create customs/port delays?
- Is this supplier critical because alternatives are unavailable?
- What percentage of this material depends on this supplier?

OpsDeck partially models supplier reliability using recent shipment behavior. It does not yet model supplier concentration, alternate suppliers, contract commitment, route-specific supplier behavior, or reason for delay.

### How A Steel Plant Thinks About Vessel Delays

Vessel delay is judged against cover and port reality.

Operators ask:

- Is the vessel at anchorage, berth, or still sailing?
- Is berth available?
- Is discharge equipment available?
- Is port congested?
- Is the cargo cleared?
- Is rake/truck evacuation available?
- Is the ETA delay larger than available cover buffer?
- Are there other vessels behind/ahead?
- Is the delayed vessel carrying the critical grade or a substitutable grade?

OpsDeck sees ETA drift and stale visibility. It does not yet deeply reason about port congestion, berth queue, discharge, customs, evacuation, or grade criticality.

### How A Steel Plant Thinks About Port Congestion

Port congestion is often more important than ocean ETA.

Operators ask:

- Vessel arrived but not berthed?
- Berth occupied?
- Cargo discharged but stuck at port?
- Port stock physically exists but cannot move inland?
- Rake availability?
- Road permits?
- Weather stoppage?
- Demurrage pressure?

OpsDeck has port/profile language and port-related recommendations, but not true port operations reasoning.

### How A Steel Plant Thinks About Rail Delays

Rail is not just ETA drift.

Operators ask:

- Rake placed or only planned?
- Rake loaded?
- Rake departed?
- Yard congestion?
- Route disruption?
- Last-mile unloading slot?
- Is rake assigned to this plant or diverted?

OpsDeck has rail profile but no rake lifecycle model.

### How A Steel Plant Thinks About Road Delays

Road delays are highly noisy.

Operators ask:

- Truck dispatched?
- GPS active?
- Checkpost delay?
- Plant gate queue?
- Driver/vendor confirmation?
- Distance from plant?
- Delivery window?

OpsDeck uses strict inland visibility assumptions. That may create false panic if the customer updates road movements only once or twice daily.

### Reserve Stock, Safety Stock, Quality Hold

Reserve stock is not ordinary usable stock. It may be physically usable but operationally protected.

Quality hold stock is not usable until released.

Safety stock depends on:

- lead time
- supplier reliability
- transport mode
- material criticality
- consumption volatility
- plant shutdown plan

OpsDeck subtracts quality hold and can flag protected reserve. It does not yet calculate safety stock from lead time, volatility, mode, and supplier reliability.

### Multiple Inbound Shipments

Planners do not simply add all inbound.

They sequence inbound:

- Which shipment arrives first?
- Which one is credible?
- Which one clears port first?
- Which one has the right grade?
- Which one reaches plant before reserve breach?
- Are multiple shipments dependent on same port/route/supplier?

OpsDeck aggregates inbound confidence. That is directionally useful but operationally incomplete.

### Multiple Suppliers

Operators think in concentration and fallback:

- How much demand is tied to one supplier?
- Is alternate supplier technically approved?
- Is alternate material already contracted?
- What is lead time for alternate source?
- Can commercial/procurement actually activate it?

OpsDeck does not yet reason enough about supplier concentration or alternate source readiness.

### Material Substitution

Substitution is not a single percentage in real operations.

It depends on:

- grade/spec compatibility
- process tolerance
- blend recipes
- customer quality commitments
- current stock of substitute material
- approvals
- cost penalty
- effect on yield and productivity

OpsDeck has substitution factor in impact logic. That is a useful placeholder, not enough for plant-grade judgment.

### Production Interruption

COOs think in:

- which process stops first
- how many hours until process restriction
- which product campaigns are affected
- restart complexity
- quality loss
- energy cost
- downstream starvation
- customer dispatch impact
- safety and compliance constraints

OpsDeck estimates interruption impact from configured rates, survivability, substitution, restart, dependency, and cascading factor. This is useful for prioritization but not yet precise enough for crores-level decision-making.

## Phase 2 - Attack Every Engine

## 1. Inventory Continuity

Purpose: decide whether material stock can sustain production continuity.

Current logic:

- usable stock = on-hand minus blocked/reserved/quality hold
- days of cover = usable stock divided by daily consumption
- trusted cover can include inbound adjusted by visibility confidence
- protected reserve can trigger risk

Operational strengths:

- Separates usable stock from on-hand stock.
- Quality hold is treated as unavailable.
- Daily consumption is visible in the calculation.
- Protected reserve concept exists.
- Explainability is strong enough for planners to inspect.

Operational weaknesses:

- Consumption rate appears static, not tied to production plan.
- No volatility band around consumption.
- No planned shutdown or campaign schedule awareness.
- No stockyard/location/reclaimability awareness.
- Inbound can improve trusted cover without enough arrival-window reasoning.

What a planner would trust:

- "This much is on hand."
- "This much is quality-held."
- "At this daily consumption, cover is X days."

What a planner would question:

- "Why is inbound counted if it cannot reach before reserve breach?"
- "Is this consumption rate today's plan or historical average?"
- "Is this material actually usable in the current blend?"

False positive risks:

- Average consumption says low cover while planned shutdown reduces consumption.
- Quality hold stock may be releasable in hours but treated unavailable.
- Protected reserve breach may panic even when inbound is already at gate.

False negative risks:

- Inbound too far away inflates trusted cover.
- Consumption spike from production plan is ignored.
- Off-grade/yard-constrained stock is treated usable if not flagged.

Recommended improvements:

1. Add planned consumption by date, not only daily average.
2. Add inbound arrival horizon against reserve/critical thresholds.
3. Add stock status classes: unrestricted, quality hold, blocked, protected reserve, location constrained.
4. Add consumption volatility confidence.
5. Add "raw cover" and "protected cover" as separate operator-facing values.

## 2. Shipment Continuity

Purpose: determine whether inbound shipment movement threatens continuity.

Current logic:

- ETA slip creates watch/degraded status.
- overdue ETA creates degraded status.
- stale or critical tracking creates degraded status.
- missing milestone/context reduces confidence.

Operational strengths:

- ETA slip is visible.
- Stale tracking is not ignored.
- Missing milestone is treated as operational uncertainty.
- Works well for clean shipment data.

Operational weaknesses:

- Port, rail, and road modes need different operational logic.
- Missing purchase order context is penalized despite PO not being a mature modeled object.
- ETA alone is not enough; status/milestone credibility matters.
- Does not distinguish "delayed but still safe" from "delayed and cover-threatening" strongly enough by itself.

What a planner would trust:

- "ETA slipped by 2 days."
- "Tracking has not updated."
- "Delivery milestone is overdue."

What a planner would question:

- "Is the shipment at anchorage or only delayed on paper?"
- "Is discharge completed?"
- "Is the rake placed?"
- "Is the delay supplier-caused, port-caused, or inland-caused?"

False positive risks:

- Stable vessel with stale AIS update triggers panic.
- Manual road update not refreshed every 6 hours appears degraded.

False negative risks:

- Vessel arrived but port evacuation blocked is not fully captured.
- Rail/rake disruption not modeled if ETA still looks stable.

Recommended improvements:

1. Add mode-specific movement state machines.
2. Add port status: arrived, anchored, berthed, discharged, cleared, evacuated.
3. Add rail status: rake planned, placed, loaded, departed, arrived, unloaded.
4. Add road status: dispatched, GPS fresh, gate-in, unloaded.
5. Separate ETA delay from movement-condition risk.

## 3. Visibility Confidence

Purpose: decide how much inbound quantity should be trusted operationally.

Current logic:

- shipment profile determines base confidence and update cadence.
- old updates reduce confidence.
- ETA behavior reduces or improves confidence.
- abnormal states reduce confidence.
- trusted inbound = physical inbound x confidence.

Operational strengths:

- Strong concept: material is not gone just because visibility is weak.
- Separates physical inbound from trusted inbound.
- ETA stability and update freshness both matter.
- Good for explaining confidence to users.

Operational weaknesses:

- Cadence defaults may not match Indian plant realities.
- Confidence is too generic across routes, suppliers, ports, and materials.
- "Visibility freshness" can be confused with actual timestamp freshness.
- Does not know if shipment is stuck at a known bottleneck.

What a planner would trust:

- "Physical inbound remains 900 MT, but trusted protection is only 135 MT."
- "Poor visibility should reduce confidence, not erase the shipment."

What a planner would question:

- "Why is inland visibility expected every 6 hours?"
- "Why is stable ocean ETA punished heavily for stale update?"
- "Does the system know the port is congested?"

False positive risks:

- Poor tracking on a reliable long-haul vessel creates excessive concern.
- Manual uploads with daily cadence look stale.

False negative risks:

- Clean tracking from an unreliable supplier can overstate confidence.
- Stable ETA can hide known port/rail bottleneck.

Recommended improvements:

1. Configure cadence by tenant, mode, route, supplier, and source system.
2. Separate timestamp freshness from operational confidence.
3. Add source reliability: AIS, ERP, supplier email, manual file, GPS.
4. Add bottleneck-specific confidence penalties.

## 4. ETA Behaviour

Purpose: detect whether ETA is stable, drifting, repeatedly drifting, volatile, recovering, or degraded.

Current logic:

- compares current ETA to planned ETA.
- uses tolerance by profile: ocean tolerant, inland strict, near destination very strict.
- repeated drift and stale updates increase concern.

Operational strengths:

- Repeated ETA drift is treated worse than one-time drift.
- Near-destination strictness is operationally sensible.
- Recovering ETA concept is useful.

Operational weaknesses:

- ETA reliability depends on source. Carrier ETA, port ETA, supplier ETA, ERP ETA, and manual ETA are not equal.
- Planned ETA may be wrong from the start.
- Does not model cause of ETA drift.
- Does not weigh ETA drift by remaining cover enough at this layer.

What a planner would trust:

- "ETA repeatedly drifting" is a real risk signal.
- "Near plant but ETA still moving" deserves attention.

What a planner would question:

- "What is the ETA source?"
- "Was the planned ETA realistic?"
- "Is ETA drift normal for this route?"

False positive risks:

- Conservative supplier revises ETA frequently but still arrives before reserve breach.

False negative risks:

- ETA remains stable because source is stale or manually optimistic.

Recommended improvements:

1. Track ETA source and source reliability.
2. Compare ETA behavior against route-specific historical behavior.
3. Add cause classification: port, vessel, customs, rail, road, supplier, unknown.
4. Use arrival-before-threshold as central decision logic.

## 5. Supplier Reliability

Purpose: adjust operational confidence based on supplier performance.

Current logic:

- needs linked supplier ID.
- uses recent supplier shipment samples.
- combines on-time behavior and visibility confidence.
- weak supplier can reduce inbound trust.

Operational strengths:

- Supplier reliability is contextual, not just master-data text.
- Requires history before strong conclusions.
- Current shipment behavior can affect reliability.

Operational weaknesses:

- Missing supplier master means reliability becomes unknown.
- Supplier reliability is not separated by material grade, route, port, contract, or source mine strongly enough.
- Does not model supplier concentration.
- Does not understand approved alternate suppliers.
- No root-cause separation between supplier fault and logistics fault.

What a planner would trust:

- "This supplier has weak history for this plant/material."

What a planner would question:

- "Weak because supplier failed, or because port was congested?"
- "Do we have an alternate supplier?"
- "How much of our total requirement depends on this supplier?"

False positive risks:

- Supplier penalized for logistics delays outside its control.

False negative risks:

- New supplier with no history is treated neutral/unknown rather than risky in critical material context.
- Supplier concentration is ignored.

Recommended improvements:

1. Add supplier concentration risk.
2. Add supplier-material-plant-route reliability.
3. Add delay root-cause.
4. Add approved alternate supplier availability and lead time.
5. Require supplier master onboarding before pilot risk claims.

## 6. Delay Vs Cover Intelligence

Purpose: decide whether an inbound delay matters operationally given stock cover.

Current logic:

- considers cover pressure, ETA threat, trusted protection ratio, delay hours, and supplier reliability.
- creates risk when delay/visibility/cover combination applies.

Operational strengths:

- This is the most important engine directionally.
- It tries to answer the right question: "Does this delay threaten cover?"
- Explains that physical inbound still exists even when trusted protection is weak.

Operational weaknesses:

- Weak trusted protection alone can create medium concern.
- Multiple inbound sequencing is not mature.
- Does not know if healthy alternate inbound covers the delay.
- Fallback thresholds may create confident risk before configuration.

What a planner would trust:

- "Delayed inbound matters because cover is only X days."
- "Delay exceeds threshold window."

What a planner would question:

- "What about the other two shipments?"
- "Which shipment arrives before reserve breach?"
- "Does this material have a substitute?"

False positive risks:

- One delayed shipment triggers concern although other inbound fully protects cover.
- Weak visibility creates medium risk even with ample cover.

False negative risks:

- Aggregated inbound hides that first arrival is delayed past stockout.
- Critical grade is delayed but generic material stock appears enough.

Recommended improvements:

1. Sequence inbound arrivals by ETA and confidence.
2. Compare each inbound to critical/reserve stock dates.
3. Net off healthy inbound before escalating delayed inbound.
4. Show "this shipment matters / does not matter" explicitly.
5. Make missing thresholds uncalibrated, not confident.

## 7. Production Interruption Impact

Purpose: estimate how operational continuity risk affects production and financial exposure.

Current logic:

- uses production rate, finished goods value, survivable hours, dependency ratio, downtime cost, restart cost, substitution factor, cascading factor, and deterministic probability.

Operational strengths:

- Asks the right questions.
- Separates interruption impact from raw material value.
- Includes survivability, restart, substitution, and cascading.
- Useful for ranking risks.

Operational weaknesses:

- Impact numbers can look precise while assumptions are rough.
- Real production impact depends on campaign schedule and process bottleneck.
- Substitution is too simplified.
- Cascading factor is a configured multiplier, not a process simulation.
- Does not deeply model downstream customer dispatch impact.

What a COO would trust:

- Directional ranking: "this risk matters more than that one."

What a COO would question:

- "Why is probability 0.45?"
- "Which line actually stops?"
- "What customer orders are affected?"
- "Can we slow production instead of stopping?"

False positive risks:

- Overstated crore impact from conservative config.

False negative risks:

- Understated downstream effect if shared material feeds multiple critical products.

Recommended improvements:

1. Treat impact as range, not point estimate.
2. Connect to production schedule.
3. Add process-specific stoppage logic.
4. Add substitution stock availability.
5. Add customer/order criticality later, without becoming ERP.

## Phase 3 - Real Steel Plant Scenarios

## Scenario 1: Coking Coal, 4 Days Cover, Vessel Delayed 2 Days, Port Congestion

Would OpsDeck react correctly?

Partially.

Likely behavior:

- 4 days cover is near warning/critical depending thresholds.
- 2-day ETA slip would create shipment degradation or delay-vs-cover concern.
- Port profile may reduce confidence if stale/degraded.

What is correct:

- OpsDeck should not ignore this.
- It should show delay vs cover and trusted inbound degradation.

What is missing:

- True port congestion reasoning.
- Berth/discharge/evacuation status.
- Coking coal blend/grade criticality.
- Alternate vessel or stockpile at port.

Operator verdict: useful alert, not final decision.

## Scenario 2: Limestone, 12 Days Cover, Supplier Reliability Weak

Would OpsDeck react correctly?

Probably overreacts or under-contextualizes depending shipment state.

Likely behavior:

- 12 days cover is likely low/normal risk.
- weak supplier may reduce trusted inbound confidence if linked.
- if shipment is degraded, severity can increase.

What is correct:

- Weak supplier should be visible.

What is missing:

- Limestone is often easier to source locally than coking coal.
- 12 days cover may be comfortable depending lead time.
- Supplier weakness alone should not create panic unless concentration/lead time/alternate availability make it dangerous.

Operator verdict: should be watch, not alarm, unless supplier concentration is high and alternate supply is poor.

## Scenario 3: Iron Ore Fines, 3 Inbound Shipments, One Delayed, Two Healthy

Would OpsDeck react correctly?

Not reliably.

Likely behavior:

- delayed shipment creates shipment degradation.
- aggregate inbound may still improve cover.
- delay-vs-cover may not clearly explain whether the delayed shipment matters after two healthy shipments.

What is correct:

- It sees each shipment and continuity context.

What is missing:

- sequencing by ETA.
- net coverage after healthy inbound.
- grade/source compatibility.
- shared route/port dependency.

Operator verdict: planners would immediately ask, "Do the two healthy shipments cover us before the delayed one matters?"

## Scenario 4: Material Below Reserve, Inbound Healthy

Would OpsDeck react correctly?

Partially.

Likely behavior:

- protected reserve breach triggers risk.
- healthy inbound improves trusted cover.

What is correct:

- Reserve breach should not be ignored.

What is missing:

- If inbound is at gate/near plant, reserve breach may be acceptable for a few hours.
- If reserve is policy-protected, use of reserve may require approval even with healthy inbound.

Operator verdict: correct to flag, but severity must depend on inbound arrival certainty and reserve policy.

## Scenario 5: Poor Shipment Visibility, Stable ETA

Would OpsDeck react correctly?

Partially, with false panic risk.

Likely behavior:

- visibility confidence drops.
- trusted inbound quantity reduces.
- risk may increase if trusted protection weak.

What is correct:

- Poor visibility should reduce trust, not erase material.

What is missing:

- stable ETA from a trusted source should matter.
- source type should be judged.
- ocean/manual update cadence may be normal.

Operator verdict: good concept, but needs better source/cadence calibration.

## Scenario 6: Good Visibility, ETA Repeatedly Drifting

Would OpsDeck react correctly?

Mostly yes.

Likely behavior:

- repeated ETA drift becomes concern.
- confidence penalty applies.
- delay-vs-cover may escalate if cover is tight.

What is correct:

- Repeated ETA drift is operationally serious.

What is missing:

- cause of drift.
- route historical norms.
- whether drift still arrives before reserve breach.

Operator verdict: this is one of OpsDeck's stronger reasoning patterns.

## Scenario 7: Shared Material Feeding Multiple Products

Would OpsDeck react correctly?

Partially.

Likely behavior:

- process/product dependency config can estimate impact.
- cascading factor can amplify impact.

What is correct:

- It recognizes shared material can affect multiple processes/products if configured.

What is missing:

- actual production schedule.
- product campaign priority.
- ability to ration material between products.
- alternate blend/substitution stock.

Operator verdict: useful directional impact, not enough for production decision.

## Scenario 8: Supplier History Unavailable

Would OpsDeck react correctly?

Not fully.

Likely behavior:

- supplier reliability becomes unknown or neutral.

What is correct:

- It does not invent false supplier history.

What is missing:

- unknown supplier history should be risk-weighted differently for critical materials.
- supplier onboarding status should be explicit.
- concentration and alternate availability should compensate.

Operator verdict: acceptable for honesty, weak for decision-making.

## Phase 4 - Missing Reasoning

Important operational reasoning missing or immature:

1. Port congestion and berth queue.
2. Vessel arrived vs berthed vs discharged vs customs cleared vs evacuated.
3. Rail rake lifecycle and rake availability.
4. Road GPS/checkpost/gate-in logic.
5. Weather and monsoon disruption.
6. Route-level reliability.
7. Transport mode reliability by supplier/material/plant.
8. Supplier concentration risk.
9. Alternate supplier availability.
10. Approved supplier/material qualification.
11. Contractual supply commitments.
12. Purchase order and contract coverage.
13. Material grade/spec compatibility.
14. Blending constraints.
15. Substitution stock availability.
16. Consumption volatility.
17. Production schedule awareness.
18. Planned maintenance shutdowns.
19. Campaign/product mix awareness.
20. Shared material rationing.
21. Yard/silo/bunker location and reclaimability.
22. Port stock vs plant stock distinction.
23. In-transit ownership/title risk.
24. Quality release probability and time.
25. Historical shortage patterns.
26. Route-specific ETA drift norms.
27. Supplier delay root cause.
28. Multi-shipment sequencing.
29. Multi-supplier fallback path.
30. Human confirmation workflow.
31. Exception aging and owner accountability.
32. Confidence by data source, not only data age.
33. Criticality weighting by material/process.
34. Blast furnace/coke oven/sinter/pellet/steel melt process-specific survivability.
35. Slowdown vs shutdown decision model.

## Phase 5 - Calibration Roadmap

## P0 - Must Have Before First Pilot

1. Arrival-before-threshold logic: inbound counts as protective only if it can arrive before critical/reserve breach.
2. Multi-shipment sequencing: show which shipment protects cover and which one does not matter.
3. Production consumption plan input: daily average is not enough.
4. Supplier master/linking onboarding: supplier reliability cannot be optional for a supplier-risk product.
5. Threshold calibration workshop per material: coking coal, PCI coal, iron ore, limestone, ferro alloys, zinc, etc.
6. Separate stale timestamp from weak operational confidence.
7. Explicit uncalibrated state when thresholds/impact assumptions are missing.
8. Mode-specific minimum logic for ocean, port, rail, road.
9. Reserve breach logic that distinguishes policy breach from production stop.
10. Human override/comment for operational confirmation.

## P1 - Must Have Before First Paying Customer

1. Port lifecycle model.
2. Rail/rake lifecycle model.
3. Supplier concentration risk.
4. Alternate supplier availability.
5. Route reliability profiles.
6. Material criticality by process.
7. Consumption volatility bands.
8. Planned maintenance/shutdown awareness.
9. Quality hold release workflow.
10. Impact ranges instead of single precise impact number.
11. Historical validation/backtesting using past shortages and delays.
12. Data source reliability weighting.
13. Root cause classification for delay.
14. Strong operator-facing explanation: "why this matters now."

## P2 - Enterprise-Grade Enhancements

1. Weather and port congestion feeds.
2. Berth, customs, discharge, and evacuation integrations.
3. Rail GPS/rake tracking integration.
4. Truck GPS integration.
5. Contract and PO coverage context.
6. Advanced blend/substitution optimizer interface.
7. Customer order criticality.
8. Scenario simulation: "what if vessel slips another 48 hours?"
9. Multi-plant allocation and diversion logic.
10. Continuous calibration from outcomes.
11. Plant-specific operating playbooks.
12. Probabilistic interruption ranges.
13. Supplier scorecards by material/route/plant.
14. Approved vendor/material qualification rules.

## Phase 6 - Product Truth

### 1. Would A Plant Planner Trust OpsDeck Today?

Partially.

A planner would trust it as a visibility and prioritization aid. They would not blindly trust the severity decision until it proves that inbound timing, production consumption, reserve policy, and material substitutability are correctly handled.

### 2. Would A Logistics Head Trust OpsDeck Today?

Partially.

A logistics head would like ETA drift, stale visibility, and shipment degradation logic. They would challenge the lack of port, rail, rake, carrier, and route-specific reasoning.

### 3. Would A COO Trust OpsDeck Today?

Not yet for final decisions.

A COO would appreciate the impact framing but would treat impact values as directional. Wrong crore-level impact estimates are dangerous if the assumptions are not signed off.

### 4. What Would Make Them Reject It?

- False panic during normal logistics noise.
- Counting inbound that cannot arrive before stockout.
- Missing an actual shortage because aggregate cover looked safe.
- Supplier reliability shown as weak/strong without root cause.
- Impact numbers that look precise but cannot be defended.
- Too many alerts from missing PO/context/visibility rather than true continuity threat.
- No historical proof against their own past incidents.

### 5. What Would Make Them Adopt It?

- It correctly predicts past shortages and delayed-shipment escalations.
- It clearly distinguishes physical inbound from trusted protective inbound.
- It explains "why this matters now" in operational terms.
- It reduces meeting time between planning, logistics, and operations.
- It catches one real risk earlier than the existing Excel/WhatsApp process.
- It lets them tune assumptions by material and plant.
- It does not pretend to automate procurement or production decisions.

### 6. Single Most Important Reasoning Improvement Needed

Inbound protection must be time-phased.

OpsDeck must decide whether each inbound shipment can realistically protect the plant before material reaches warning, reserve, critical, and interruption points.

Without this, cover can be falsely safe or falsely alarming.

### 7. Single Most Important Data Input Missing

Forward production consumption plan by material/process/day.

Average daily consumption is not enough. Steel plants do not consume uniformly every day.

### 8. If OpsDeck Only Improved Reasoning For 6 Months

Improve in this order:

1. Time-phased cover with inbound sequencing.
2. Mode-specific logistics reasoning: ocean, port, rail, road.
3. Supplier concentration and alternate source readiness.
4. Production schedule and consumption volatility.
5. Historical validation and outcome calibration.
6. Impact ranges and process-specific interruption logic.

## Final Operational Verdict

OpsDeck is directionally right.

It has the right product instinct: continuity intelligence, not ERP; explain risk before production disruption; separate visibility weakness from physical material disappearance; connect stock, shipment, supplier, and impact.

But a real steel operations leader would not yet delegate judgment to it.

Today it is a promising control-room assistant.

To become trusted, it must move from rules to operational reasoning:

- Which inbound actually protects us?
- Which delay actually matters?
- Which supplier weakness is material?
- Which stock is truly usable?
- Which process will actually be hit?
- What should the planner do today?

Until it answers those questions with plant-calibrated evidence, it should be sold as an early warning and explanation layer, not as an authoritative continuity decision engine.

