# Product & Process Dependency Modeling V1

OpsDeck no longer has to treat operational interruption impact as only:

```text
material -> one blended output value
```

V1 adds a lightweight deterministic model:

```text
material -> process or line -> product mix -> operational exposure
```

This improves continuity impact explainability without becoming a production scheduler, accounting system, or manufacturing simulation.

## Why Blended Output Value Is Insufficient

One material can affect multiple processes. One process can support multiple products with different values and operational importance.

For example, coking coal may affect blast furnace operations, and blast furnace output may be weighted toward higher-value hot rolled coil compared with billets.

## Data Model

V1 uses existing `production_lines` as the backend process/line table.

New dependency tables:

### ProcessProductDependency

Represents process-to-product exposure:

- `tenant_id`
- `process_id`
- `product_name`
- `output_share_ratio`
- `product_value_per_mt`
- `operational_criticality_factor`
- `is_active`

### MaterialProcessDependency

Represents material-to-process dependency:

- `tenant_id`
- `material_id`
- `process_id`
- `dependency_ratio`
- `substitution_factor`, nullable
- `survivability_hours`, nullable
- `is_active`

## Weighting Logic

For each active material-process dependency:

```text
weighted_process_output_value =
  SUM(output_share_ratio * product_value_per_mt * operational_criticality_factor)
```

Then process impact contribution is calculated from:

```text
production_rate_mt_per_hour
* weighted_process_output_value
* process_interruption_hours
```

Where process interruption hours include:

- material dependency ratio
- configured line dependency ratio
- process-level substitution if configured
- process-level survivability if configured

The engine aggregates all active process contributions.

## Fallback Behavior

If no active dependency data exists, OpsDeck preserves the existing configured blended field:

```text
finished_goods_value_per_mt
```

No existing interruption impact configuration is broken.

## Admin Configuration

Tenant admins configure V1 at:

```text
Admin -> Operational Configuration -> Product & Process Dependency
```

The page has three compact sections:

- **Processes / Lines** configures active production processes using the existing `production_lines` table.
- **Product Mix** configures process output exposure through `ProcessProductDependency`.
- **Material Dependency** configures which materials affect which process through `MaterialProcessDependency`.

The UI keeps operational labels in front of backend ratios:

- `Output share %` is submitted as `output_share_ratio = percentage / 100`.
- Product criticality choices map to `operational_criticality_factor`.
- Material dependency choices map to `dependency_ratio`.
- Substitution and survivability can be left as fallback values, which submit `null` and let the interruption config continue to provide the baseline assumption.

If no product/process dependency is configured for a material, OpsDeck uses the existing weighted output value fallback. The page describes the result as an operational exposure estimate, not exact financial loss.

## Explainability

Impact reason chains now include:

- affected process names
- material dependency ratios
- effective dependency after line/substitution weighting
- product mix rows
- weighted product exposure values
- per-process production impact contribution

Example:

```text
Material affects Blast Furnace operations with dependency ratio 0.9000.
Blast Furnace output mix: HRC Coil 0.6000 share; Billets 0.4000 share.
```

## Limitations

V1 is not:

- a production scheduler
- exact accounting
- finite-capacity planning
- ERP writeback
- automatic production routing

It is deterministic continuity exposure estimation for operational risk explainability.
