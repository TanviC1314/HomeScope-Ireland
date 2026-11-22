"""Housing policy scenario simulator - HYPOTHETICAL arithmetic, not a forecast.

What it does
------------
Starting from the latest *actual* figures for an area (completions in the latest full year, the
current dwelling stock, long-term vacant stock, Census population and household growth), it applies
user-chosen hypothetical changes and shows the resulting differences in supply indicators.

What it deliberately does NOT do
--------------------------------
* It is not a forecast. Baseline completions are simply held at the latest full-year level.
* It does not model demand, prices, migration, construction capacity, viability, funding, planning
  delays, or any other real-world constraint.
* It does not assume all vacant homes can be renovated: only a user-chosen share of the long-term
  vacant stock is treated as suitable, and the number renovated is capped at that pool.
* Affordable housing is a user-assumed share of completions; no official affordable-delivery series is used.

All assumptions are returned with every result (see ``ASSUMPTIONS``).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.indicators import calculations as calc

Tables = Dict[str, pd.DataFrame]

LABEL = "HYPOTHETICAL SIMULATION - illustrative arithmetic, not a forecast"

ASSUMPTIONS = [
    "Baseline annual completions are held constant at the latest full calendar year (no trend, no cycle).",
    "Starting dwelling stock = ESB-based dwelling stock at Q4 2024 plus completions in later full years.",
    "A completions uplift is applied as a percentage above the baseline in every year (optionally phased in linearly).",
    "Renovated vacant homes are added to supply evenly across the horizon, capped at the share of long-term vacant stock "
    "the user judges suitable (default 10%). Suitability is an assumption, not a statistic.",
    "Affordable homes = assumed share of that year's completions (renovations are not counted as affordable). The baseline and "
    "scenario shares are user inputs, not official statistics.",
    "Population is held at its current level; demand, prices, migration and household formation are not simulated.",
    "'Years of household growth covered' compares extra homes with the average annual household growth between Census 2016 and 2022 (a proxy).",
    "No construction capacity, viability, finance, planning, infrastructure or labour constraints are modelled.",
]


@dataclass
class Baseline:
    area: str
    base_year: int                      # latest full year of completions
    completions: float                  # baseline annual completions
    stock_start: float                  # dwelling stock at the start of the horizon
    population: float
    long_term_vacant: float
    annual_household_growth: float      # Census 2016-22 average (proxy for household formation)


@dataclass
class ScenarioInputs:
    name: str = "Scenario"
    completions_uplift_pct: float = 0.0
    horizon_years: int = 5
    phase_in_years: int = 1
    vacant_homes_target: int = 0
    suitable_share_pct: float = 10.0
    affordable_share_baseline_pct: float = 10.0
    affordable_share_scenario_pct: float = 10.0


def build_baseline(t: Tables, county: Optional[str] = None) -> Baseline:
    """Baseline for the State (county=None) or one of the 26 counties, from actual published data."""
    ly = calc.latest_full_year(t)
    comp = calc.annual_completions(t, "county")
    vac = t["vacancy_estimates"]
    vy = int(vac["year"].max())
    stock_q4 = vac[(vac["year"] == vy) & (vac["quarter"] == 4)]
    lt = t["long_term_vacancy"]
    lt = lt[lt["year"] == int(lt["year"].max())]
    cg = calc.census_growth(t)
    if county:
        comp = comp[comp["county"] == county]
        stock_q4 = stock_q4[stock_q4["county"] == county]
        lt = lt[lt["county"] == county]
        cg = cg[cg["county"] == county]
        pop = float(t["population_census"].query("county == @county and census_year == 2022")["population"].iloc[0])
    else:
        pop = float(calc.national_population(t).iloc[-1]["population_thousand"]) * 1000
    base_comp = float(comp.loc[comp["year"] == ly, "completions"].sum())
    later = comp[(comp["year"] > vy) & (comp["year"] <= ly) & (~comp["is_partial_year"])]["completions"].sum()
    return Baseline(
        area=county or "Ireland", base_year=ly, completions=base_comp,
        stock_start=float(stock_q4["dwelling_stock"].sum() + later), population=pop,
        long_term_vacant=float(lt["vacant_dwellings"].sum()),
        annual_household_growth=float(cg["annual_household_growth"].sum()),
    )


def simulate(base: Baseline, s: ScenarioInputs) -> pd.DataFrame:
    """Year-by-year baseline vs scenario table."""
    n = max(int(s.horizon_years), 1)
    years = np.arange(1, n + 1)
    phase = max(int(s.phase_in_years), 1)
    uplift = (s.completions_uplift_pct / 100.0) * np.minimum(1.0, years / phase)
    pool = base.long_term_vacant * s.suitable_share_pct / 100.0
    renovated_total = float(min(max(s.vacant_homes_target, 0), pool))
    renovated = np.full(n, renovated_total / n)

    base_comp = np.full(n, base.completions)
    scen_comp = base.completions * (1 + uplift)
    df = pd.DataFrame({
        "year": base.base_year + years,
        "baseline_completions": base_comp,
        "scenario_completions": scen_comp,
        "extra_completions": scen_comp - base_comp,
        "renovated_vacant_homes": renovated,
    })
    df["scenario_additions"] = df["scenario_completions"] + df["renovated_vacant_homes"]
    df["baseline_stock"] = base.stock_start + df["baseline_completions"].cumsum()
    df["scenario_stock"] = base.stock_start + df["scenario_additions"].cumsum()
    df["baseline_stock_growth_pct"] = 100 * (df["baseline_stock"] / base.stock_start - 1)
    df["scenario_stock_growth_pct"] = 100 * (df["scenario_stock"] / base.stock_start - 1)
    df["baseline_completions_per_1000"] = 1000 * df["baseline_completions"] / base.population
    df["scenario_completions_per_1000"] = 1000 * df["scenario_completions"] / base.population
    df["baseline_affordable"] = df["baseline_completions"] * s.affordable_share_baseline_pct / 100
    df["scenario_affordable"] = df["scenario_completions"] * s.affordable_share_scenario_pct / 100
    df["extra_affordable"] = df["scenario_affordable"] - df["baseline_affordable"]
    df["cumulative_extra_supply"] = (df["scenario_additions"] - df["baseline_completions"]).cumsum()
    df.attrs.update(pool=pool, renovated_total=renovated_total, requested=s.vacant_homes_target,
                    capped=s.vacant_homes_target > pool)
    return df


def summarise(base: Baseline, s: ScenarioInputs) -> Dict[str, float]:
    df = simulate(base, s)
    last = df.iloc[-1]
    extra_supply = float(last["cumulative_extra_supply"])
    return {
        "scenario": s.name,
        "area": base.area,
        "horizon_years": int(s.horizon_years),
        "cumulative_extra_completions": float(df["extra_completions"].sum()),
        "renovated_vacant_homes": float(df.attrs["renovated_total"]),
        "vacant_homes_requested": float(s.vacant_homes_target),
        "renovation_capped_by_suitable_pool": bool(df.attrs["capped"]),
        "suitable_vacant_pool": float(df.attrs["pool"]),
        "cumulative_extra_supply": extra_supply,
        "baseline_stock_growth_pct": float(last["baseline_stock_growth_pct"]),
        "scenario_stock_growth_pct": float(last["scenario_stock_growth_pct"]),
        "stock_growth_difference_pp": float(last["scenario_stock_growth_pct"] - last["baseline_stock_growth_pct"]),
        "baseline_completions_per_1000": float(df["baseline_completions_per_1000"].iloc[-1]),
        "scenario_completions_per_1000_final_year": float(last["scenario_completions_per_1000"]),
        "cumulative_extra_affordable": float(df["extra_affordable"].sum()),
        "years_of_household_growth_covered": float(extra_supply / base.annual_household_growth) if base.annual_household_growth else float("nan"),
        "baseline_completions_to_household_growth": float(base.completions / base.annual_household_growth) if base.annual_household_growth else float("nan"),
    }


def compare(base: Baseline, scenarios: List[ScenarioInputs]) -> pd.DataFrame:
    return pd.DataFrame([summarise(base, s) for s in scenarios])


def standard_scenarios(horizon: int = 5) -> List[ScenarioInputs]:
    return [ScenarioInputs(name="Baseline (no change)", horizon_years=horizon)] + [
        ScenarioInputs(name=f"+{p}% completions", completions_uplift_pct=p, horizon_years=horizon) for p in (5, 10, 15)]
