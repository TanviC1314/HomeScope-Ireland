# Housing Supply-Demand Gap (Phase 2 Day 3)

This document describes the methodology, data sources, assumptions and limitations of the
Day 3 supply-demand gap analysis in HomeScope Ireland.

## What it measures

The gap between:
- **Demand** – the estimated number of new dwellings needed each year
- **Supply** – actual new dwelling completions (CSO NDQ06, ESB-based proxy)

A positive gap means estimated demand exceeds supply (shortfall); a negative gap means supply
exceeds demand (surplus).

## Demand model

Annual household demand is decomposed into three components:

```
total_demand = household_growth_demand + replacement_demand

household_growth_demand = annual_population_change / average_household_size
replacement_demand       = housing_stock × REPLACEMENT_RATE (0.4 %)
```

**National:** population change from CSO PEA15 (observed natural increase + net migration).  
**County:** population change from CSO PEA08 (annual estimates, April-to-April).

## Scenario bands (national only)

Three scenarios vary the net migration component to represent plausible outcomes:

| Scenario | Description |
|---|---|
| **High demand** | More people needing homes: less emigration or more immigration |
| **Central** | Observed net migration from CSO PEA15 |
| **Low demand** | Fewer people needing homes: more emigration or less immigration |

The multiplier applied to observed net migration:

| Net migration | High demand | Central | Low demand |
|---|---|---|---|
| Positive (net inflow) | ×1.5 | ×1.0 | ×0.5 |
| Negative (net outflow) | ×0.5 | ×1.0 | ×1.5 |

This ensures **high demand ≥ central ≥ low demand** regardless of migration sign.
During pandemic years (net emigration), the ×0.5 scenario means *less* emigration = more people needing homes.

**Natural increase is held at the observed PEA15 figure in all scenarios.** The scenarios
are analytical illustrations of migration variation, not statistical confidence intervals.

## Assumptions

| Assumption | Value | Rationale |
|---|---|---|
| Replacement rate | 0.4 % of housing stock per year | In line with European housing model estimates |
| Average household size | Interpolated linearly between Census 2016 (2.75) and 2022 (2.74) | CSO F2001; county values use county Census figures |
| Housing stock (national) | Census 2022 baseline, extended post-2022 by cumulative completions | CSO F2020 + NDQ06 |
| Housing stock (county) | Census 2022 snapshot per county | CSO F2020 |

## Data sources

| Source | Table | Description |
|---|---|---|
| CSO NDQ06 | `completions_quarterly` | New dwelling completions by LA, quarter, type |
| CSO PEA15 | `population_national` | National population, natural increase, migration |
| CSO PEA08 | `population_county_estimates` | Annual county population estimates (April) |
| CSO F2001 | `households_census` | Private households and avg household size by county |
| CSO F2020 | `housing_stock_census` | Housing stock by county and Census year |

## Limitations

1. **Population-based demand does not capture location mismatch** – a shortfall in Dublin is
   not interchangeable with a surplus in rural counties.
2. **Completions are ESB-based** – a new electricity connection is a proxy; timing can lag
   actual habitation.
3. **PEA08 county estimates are rounded** to the nearest hundred persons; small pop changes
   carry large relative rounding errors.
4. **Replacement rate is a European-average estimate**, not measured from Irish demolition data.
5. **Average household size** is from Census snapshots; a faster decline post-2022 would
   increase effective demand.
6. **An annual surplus does not erase a previous shortfall** – the cumulative gap since 2017
   is shown as a headline KPI, but it understates the full problem if conditions before 2017
   also involved a shortfall.
7. **Housing type, quality, and affordability are not captured** – the model counts dwellings,
   not whether they are suitable or affordable.

## Files

| File | Purpose |
|---|---|
| `src/indicators/demand_gap.py` | All demand-gap functions (pure, unit-tested) |
| `src/indicators/registry.py` | Two new Indicator entries (`supply_demand_gap`, `supply_demand_gap_county`) |
| `src/analysis/insights.py` | `_demand_gap()` insight builder |
| `dashboard/views/demand_gap.py` | Supply-Demand Gap dashboard page |
| `data/raw/cso/PEA08.csv` | Raw CSO PEA08 download |
| `data/processed/population_county_estimates.csv` | Cleaned, 260 rows |
| `tests/test_demand_gap.py` | 14 unit + integration tests |
