"""Housing supply-demand gap analysis (Phase 2 Day 3).

Three levels of analysis:
  national_gap()      - annual completions vs estimated new household demand,
                        with low / central / high scenario bands
  county_gap()        - same calculation at county level using PEA08 estimates
  gap_decomposition() - break national demand into population growth,
                        household-size change and replacement components

Scenario bands vary the net migration assumption relative to the observed PEA15 figure:
  low      - 50 % of observed net migration (more emigration / less immigration)
  central  - 100 % of observed net migration (observed PEA15 figure)
  high     - 150 % of observed net migration (more immigration / less emigration)

Demand calculation:
  household_growth_demand = population_change / avg_household_size
  replacement_demand       = housing_stock * REPLACEMENT_RATE
  total_demand             = household_growth_demand + replacement_demand

Gap = total_demand - completions  (positive = shortfall, negative = surplus)

This is an analytical estimate, not a statistical forecast.  Scenario bands
represent plausible migration outcomes, not confidence intervals.
See docs/DEMAND_GAP.md for full assumptions and limitations.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from src.indicators import calculations as calc

Tables = Dict[str, pd.DataFrame]

# Annual housing replacement rate: dwellings demolished, made uninhabitable or
# requiring replacement (~0.4 % of stock, in line with European estimates).
REPLACEMENT_RATE = 0.004

# Scenario bounds: "high demand" means more people needing housing.
# When net migration is positive, high = 1.5× and low = 0.5×.
# When net migration is negative (emigration dominates), high = 0.5× of observed
# (less emigration = more people) and low = 1.5× (more emigration = fewer people).
# This keeps demand_high >= demand_central >= demand_low regardless of migration sign.
_SCEN_MULT = {"low": (1.50, 0.50), "central": (1.00, 1.00), "high": (0.50, 1.50)}
# tuple: (mult_when_negative, mult_when_positive)

# Census average household sizes (persons per household)
HH_SIZE_2016 = 2.75
HH_SIZE_2022 = 2.74


def _avg_hh_size(t: Tables, year: int) -> float:
    """Return national average household size for a given year, interpolated between Census."""
    h = t["households_census"].groupby("census_year")[["households", "persons_in_households"]].sum().reset_index()
    h["avg"] = h["persons_in_households"] / h["households"]
    years = sorted(h["census_year"].tolist())
    if year <= years[0]:
        return float(h.loc[h["census_year"] == years[0], "avg"].iloc[0])
    if year >= years[-1]:
        return float(h.loc[h["census_year"] == years[-1], "avg"].iloc[0])
    lo = max(y for y in years if y <= year)
    hi = min(y for y in years if y > year)
    s_lo = float(h.loc[h["census_year"] == lo, "avg"].iloc[0])
    s_hi = float(h.loc[h["census_year"] == hi, "avg"].iloc[0])
    frac = (year - lo) / (hi - lo)
    return s_lo + frac * (s_hi - s_lo)


def _national_stock(t: Tables, year: int) -> float:
    """Housing stock for a given year (Census snapshot or extrapolated)."""
    stock = t["housing_stock_census"].groupby("census_year")["total_stock"].sum()
    years = sorted(stock.index.tolist())
    if year <= years[0]:
        return float(stock.loc[years[0]])
    if year >= years[-1]:
        # extend post-Census with cumulative completions
        base_year = years[-1]
        base_stock = float(stock.loc[base_year])
        comps = calc.annual_completions(t, "national")
        comps = comps[comps["year"] > base_year]
        extra = float(comps["completions"].sum()) if len(comps) else 0.0
        return base_stock + extra
    # interpolate between census years
    lo = max(y for y in years if y <= year)
    hi = min(y for y in years if y > year)
    frac = (year - lo) / (hi - lo)
    return float(stock.loc[lo]) + frac * (float(stock.loc[hi]) - float(stock.loc[lo]))


def national_gap(t: Tables) -> pd.DataFrame:
    """National supply-demand gap by year with low / central / high scenario bands.

    Returns columns: year, completions, is_partial_year,
      demand_central, demand_low, demand_high,
      gap_central, gap_low, gap_high,
      natural_increase, net_migration_obs,
      hh_size, stock, replacement_demand
    """
    nat = t["population_national"].sort_values("year").copy()
    # Keep only years where both completions and population data exist
    comps = calc.annual_completions(t, "national").sort_values("year")
    # We need year-on-year population change; PEA15 has this directly
    # nat.population_thousand is April of that year; change = pop[t] - pop[t-1]
    nat["pop"] = nat["population_thousand"] * 1000
    nat["pop_change"] = nat["pop"].diff()

    # Only process years covered by the completions series (from earliest completions year)
    comp_min_year = int(comps["year"].min()) if len(comps) else 2011
    rows = []
    for _, prow in nat.iterrows():
        year = int(prow["year"])
        if np.isnan(prow["pop_change"]) or year < comp_min_year:
            continue
        crow = comps[comps["year"] == year]
        completions = int(crow["completions"].iloc[0]) if len(crow) else np.nan
        is_partial = bool(crow["is_partial_year"].iloc[0]) if len(crow) else True

        nat_inc = float(prow.get("natural_increase_thousand", np.nan)) * 1000 if not pd.isna(prow.get("natural_increase_thousand")) else np.nan
        mig_obs = float(prow.get("net_migration_thousand", np.nan)) * 1000 if not pd.isna(prow.get("net_migration_thousand")) else np.nan

        hh_size = _avg_hh_size(t, year)
        stock = _national_stock(t, year)
        repl = round(stock * REPLACEMENT_RATE)

        for scenario, (mult_neg, mult_pos) in _SCEN_MULT.items():
            if np.isnan(mig_obs) or np.isnan(nat_inc):
                pop_chg = float(prow["pop_change"])
            else:
                mult = mult_neg if mig_obs < 0 else mult_pos
                pop_chg = nat_inc + mig_obs * mult

            hh_demand = pop_chg / hh_size if hh_size > 0 else 0
            total_demand = round(hh_demand + repl)
            gap = round(total_demand - completions) if not np.isnan(completions) else np.nan
            rows.append({"year": year, "scenario": scenario, "completions": completions,
                         "is_partial_year": is_partial, "hh_size": round(hh_size, 3),
                         "stock": int(stock), "replacement_demand": repl,
                         "natural_increase": round(nat_inc) if not np.isnan(nat_inc) else np.nan,
                         "net_migration_obs": round(mig_obs) if not np.isnan(mig_obs) else np.nan,
                         "pop_change_scenario": round(pop_chg),
                         "household_growth_demand": round(hh_demand),
                         "total_demand": total_demand, "gap": gap})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Pivot to wide format for easy charting
    wide = df[df["scenario"] == "central"][
        ["year", "completions", "is_partial_year", "hh_size", "stock",
         "replacement_demand", "natural_increase", "net_migration_obs"]
    ].copy()
    for sc in ("central", "low", "high"):
        sub = df[df["scenario"] == sc][["year", "total_demand", "gap", "household_growth_demand", "pop_change_scenario"]]
        wide = wide.merge(sub.rename(columns={
            "total_demand": f"demand_{sc}", "gap": f"gap_{sc}",
            "household_growth_demand": f"hh_growth_demand_{sc}",
            "pop_change_scenario": f"pop_change_{sc}",
        }), on="year", how="left")
    return wide.reset_index(drop=True)


def county_gap(t: Tables) -> pd.DataFrame:
    """County-level supply-demand gap using PEA08 population estimates.

    Returns columns: county, year, population, pop_change, hh_size,
      replacement_demand, total_demand, completions, is_partial_year, gap
    """
    pop = t["population_county_estimates"].sort_values(["county", "year"])
    pop = pop.assign(pop_change=pop.groupby("county")["population"].diff())

    # County average household size: interpolate between Census years
    hh = t["households_census"].copy()
    hh["hh_size"] = hh["persons_in_households"] / hh["households"]
    hh = hh[["county", "census_year", "hh_size"]].dropna()
    # For each (county, year) in pop, interpolate hh_size
    hh_pivot = hh.pivot(index="county", columns="census_year", values="hh_size")
    census_yrs = sorted(hh_pivot.columns.tolist())

    def _county_hh_size(county: str, year: int) -> float:
        if county not in hh_pivot.index:
            return _avg_hh_size(t, year)
        vals = {y: hh_pivot.at[county, y] for y in census_yrs if not np.isnan(hh_pivot.at[county, y])}
        yrs = sorted(vals)
        if not yrs:
            return _avg_hh_size(t, year)
        if year <= yrs[0]:
            return vals[yrs[0]]
        if year >= yrs[-1]:
            return vals[yrs[-1]]
        lo = max(y for y in yrs if y <= year)
        hi = min(y for y in yrs if y > year)
        frac = (year - lo) / (hi - lo)
        return vals[lo] + frac * (vals[hi] - vals[lo])

    # Census housing stock per county (from housing_stock_census)
    stock_c = t["housing_stock_census"].groupby(["county", "census_year"])["total_stock"].sum().reset_index()
    stock_latest = (stock_c.sort_values("census_year").groupby("county").last()["total_stock"].to_dict())

    comps = calc.annual_completions(t, "county")

    rows = []
    for _, row in pop.iterrows():
        if pd.isna(row["pop_change"]):
            continue
        county, year = row["county"], int(row["year"])
        hh_size = _county_hh_size(county, year)
        stock = stock_latest.get(county, np.nan)
        repl = round(stock * REPLACEMENT_RATE) if not np.isnan(stock) else np.nan
        hh_demand = round(row["pop_change"] / hh_size) if hh_size > 0 else 0
        total_demand = round(hh_demand + (repl or 0))
        crow = comps[(comps["county"] == county) & (comps["year"] == year)]
        completions = int(crow["completions"].iloc[0]) if len(crow) else np.nan
        is_partial = bool(crow["is_partial_year"].iloc[0]) if len(crow) else True
        gap = round(total_demand - completions) if not np.isnan(completions) else np.nan
        rows.append({"county": county, "year": year, "population": int(row["population"]),
                     "pop_change": int(row["pop_change"]), "hh_size": round(hh_size, 3),
                     "replacement_demand": int(repl) if not np.isnan(repl) else np.nan,
                     "total_demand": total_demand, "completions": completions,
                     "is_partial_year": is_partial, "gap": gap})
    return pd.DataFrame(rows).sort_values(["county", "year"]).reset_index(drop=True)


def gap_decomposition(t: Tables) -> pd.DataFrame:
    """Decompose national demand into three components for each year.

    Returns: year, population_growth_demand, hh_size_change_demand, replacement_demand, total_demand
    """
    ng = national_gap(t)
    if ng.empty:
        return ng
    out = ng[["year", "is_partial_year", "replacement_demand",
              "hh_growth_demand_central", "pop_change_central",
              "demand_central", "gap_central"]].copy()
    # hh_size_change component: counterfactual – what if hh_size were constant at HH_SIZE_2016?
    ng2 = ng.copy()
    ng2["pop_demand_const_hh"] = ng2["pop_change_central"] / HH_SIZE_2016
    out["population_growth_demand"] = ng2["pop_demand_const_hh"].round().astype("Int64")
    out["hh_size_change_demand"] = (ng["hh_growth_demand_central"] - ng2["pop_demand_const_hh"]).round().astype("Int64")
    out["replacement_demand"] = ng["replacement_demand"].astype("Int64")
    out["total_demand"] = ng["demand_central"].astype("Int64")
    out["completions"] = ng["completions"].astype("Int64")
    out["gap"] = ng["gap_central"].astype("Int64")
    return out[["year", "is_partial_year", "population_growth_demand",
                "hh_size_change_demand", "replacement_demand",
                "total_demand", "completions", "gap"]].reset_index(drop=True)


def cumulative_gap(t: Tables, from_year: int = 2017) -> int:
    """Cumulative shortfall (completions < demand_central) since from_year (full years only)."""
    ng = national_gap(t)
    sel = ng[(ng["year"] >= from_year) & (~ng["is_partial_year"])]
    return int(sel["gap_central"].sum())


def gap_kpis(t: Tables) -> dict:
    """Return a dict of key gap metrics for the KPI strip."""
    ng = national_gap(t)
    full = ng[~ng["is_partial_year"]]
    latest = full.sort_values("year").iloc[-1] if len(full) else ng.sort_values("year").iloc[-1]
    latest_year = int(latest["year"])
    latest_gap = int(latest["gap_central"]) if not pd.isna(latest["gap_central"]) else None
    cum_gap = cumulative_gap(t)
    avg_demand = round(float(full["demand_central"].mean())) if len(full) else None
    avg_supply = round(float(full["completions"].mean())) if len(full) else None
    return {
        "latest_year": latest_year,
        "latest_gap": latest_gap,
        "cumulative_gap_since_2017": cum_gap,
        "avg_annual_demand": avg_demand,
        "avg_annual_supply": avg_supply,
    }
