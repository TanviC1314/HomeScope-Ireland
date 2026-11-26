"""Tests for the Day 3 housing supply-demand gap indicator module."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.indicators import demand_gap as dg
from src.indicators.demand_gap import REPLACEMENT_RATE


# --------------------------------------------------------------------------- helpers
def _tables_minimal(pop_changes: dict, completions: dict, stock: int = 500_000,
                     households: int = 1_900_000, persons: int = 5_100_000,
                     nat_inc_k: float = 30.0, mig_k: float = 20.0) -> dict:
    """Build a minimal Tables dict for unit-testing demand_gap functions."""
    # population_national: two rows so we get one diff
    # nat_inc_k and mig_k are in thousands (e.g. 30.0 = 30,000 persons)
    nat = pd.DataFrame({
        "year": [2022, 2023],
        "population_thousand": [5100.0, 5100.0 + nat_inc_k + mig_k],
        "natural_increase_thousand": [nat_inc_k, nat_inc_k],
        "net_migration_thousand": [mig_k, mig_k],
        "births_thousand": [np.nan, np.nan],
        "deaths_thousand": [np.nan, np.nan],
        "emigrants_thousand": [np.nan, np.nan],
        "immigrants_thousand": [np.nan, np.nan],
        "population_change_thousand": [np.nan, nat_inc_k + mig_k],
    })
    # population_county_estimates: 2 counties, 2 years
    pop_rows = []
    for year, chg in pop_changes.items():
        half = chg // 2
        pop_rows += [
            {"county": "Dublin", "year": year, "population": 1_300_000 + half},
            {"county": "Cork", "year": year, "population": 500_000 + chg - half},
        ]
    if pop_rows and min(pop_changes) > 2017:
        # add a base year with no change so diff works
        base = min(pop_changes)
        pop_rows += [
            {"county": "Dublin", "year": base - 1, "population": 1_300_000},
            {"county": "Cork", "year": base - 1, "population": 500_000},
        ]
    pop_county = pd.DataFrame(pop_rows)
    # completions_quarterly
    comp_rows = []
    for year, total in completions.items():
        for q in range(1, 5):
            comp_rows.append({"la_name": "Dublin City Council", "county": "Dublin", "year": year,
                               "quarter": q, "dwelling_type": "Apartment", "completions": total // 4})
            comp_rows.append({"la_name": "Cork County Council", "county": "Cork", "year": year,
                               "quarter": q, "dwelling_type": "Single house", "completions": 0})
    completions_q = pd.DataFrame(comp_rows)
    # households_census: 2 census years
    hh = pd.DataFrame([
        {"county": "Dublin", "census_year": 2016, "households": 500_000, "persons_in_households": 1_375_000, "avg_household_size": 2.75},
        {"county": "Dublin", "census_year": 2022, "households": 510_000, "persons_in_households": 1_397_400, "avg_household_size": 2.74},
        {"county": "Cork", "census_year": 2016, "households": 185_000, "persons_in_households": 508_750, "avg_household_size": 2.75},
        {"county": "Cork", "census_year": 2022, "households": 190_000, "persons_in_households": 520_600, "avg_household_size": 2.74},
    ])
    # housing_stock_census
    stock_df = pd.DataFrame([
        {"area_name": "Dublin", "county": "Dublin", "census_year": 2022, "total_stock": 550_000,
         "occupied": 510_000, "temporarily_absent": np.nan, "vacant": 40_000, "holiday_home": np.nan, "vacancy_rate_pct": 7.3},
        {"area_name": "Cork", "county": "Cork", "census_year": 2022, "total_stock": 210_000,
         "occupied": 195_000, "temporarily_absent": np.nan, "vacant": 15_000, "holiday_home": np.nan, "vacancy_rate_pct": 7.1},
    ])
    # dim_county (minimal)
    dim = pd.DataFrame([
        {"county": "Dublin", "province": "Leinster", "nuts3_region": "Dublin", "homeless_region": "Dublin"},
        {"county": "Cork", "province": "Munster", "nuts3_region": "South-West", "homeless_region": "South-West"},
    ])
    return {
        "population_national": nat,
        "population_county_estimates": pop_county,
        "completions_quarterly": completions_q,
        "households_census": hh,
        "housing_stock_census": stock_df,
        "dim_county": dim,
    }


# --------------------------------------------------------------------------- unit tests
def test_national_gap_returns_expected_columns():
    t = _tables_minimal(pop_changes={2023: 50_000}, completions={2023: 30_000})
    ng = dg.national_gap(t)
    assert not ng.empty
    for col in ("year", "demand_central", "demand_low", "demand_high", "gap_central", "gap_low", "gap_high", "completions"):
        assert col in ng.columns, col


def test_national_gap_scenario_ordering():
    """High scenario (more migration) → higher demand → larger gap than central; low → smaller."""
    t = _tables_minimal(pop_changes={2023: 50_000}, completions={2023: 30_000},
                        nat_inc_k=30.0, mig_k=25.0)
    ng = dg.national_gap(t)
    row = ng[ng["year"] == 2023].iloc[0]
    assert row["demand_high"] >= row["demand_central"] >= row["demand_low"], (
        f"high={row['demand_high']} central={row['demand_central']} low={row['demand_low']}")
    assert row["gap_high"] >= row["gap_central"] >= row["gap_low"]


def test_national_gap_positive_when_demand_exceeds_supply():
    t = _tables_minimal(pop_changes={2023: 100_000}, completions={2023: 10_000},
                        nat_inc_k=50.0, mig_k=50.0)
    ng = dg.national_gap(t)
    row = ng[ng["year"] == 2023].iloc[0]
    assert row["gap_central"] > 0, "demand >> supply should give positive gap"


def test_national_gap_negative_when_supply_exceeds_demand():
    t = _tables_minimal(pop_changes={2023: 5_000}, completions={2023: 80_000},
                        nat_inc_k=1.0, mig_k=1.0)
    ng = dg.national_gap(t)
    row = ng[ng["year"] == 2023].iloc[0]
    assert row["gap_central"] < 0, "supply >> demand should give negative gap"


def test_replacement_demand_included_in_total():
    # Zero net migration and zero natural increase: demand = replacement only
    t = _tables_minimal(pop_changes={2023: 0}, completions={2023: 0},
                        nat_inc_k=0.001, mig_k=0.0)   # near-zero but non-zero so rows appear
    ng = dg.national_gap(t)
    assert not ng.empty, "should produce rows"
    row = ng[ng["year"] == 2023].iloc[0]
    stock_total = 760_000  # 550k Dublin + 210k Cork
    expected_repl = round(stock_total * REPLACEMENT_RATE)
    # replacement demand is explicit column
    assert abs(int(row["replacement_demand"]) - expected_repl) < 100


def test_county_gap_shape_and_types():
    t = _tables_minimal(pop_changes={2022: 10_000, 2023: 12_000},
                        completions={2022: 8_000, 2023: 9_000})
    cg = dg.county_gap(t)
    assert not cg.empty
    assert set(["county", "year", "population", "pop_change", "total_demand", "gap"]).issubset(cg.columns)
    assert (cg["year"] > 0).all()


def test_county_gap_positive_when_county_grows_fast():
    t = _tables_minimal(pop_changes={2023: 100_000}, completions={2023: 1_000})
    cg = dg.county_gap(t)
    assert (cg["gap"] > 0).any(), "fast-growing counties should show a shortfall"


def test_gap_decomposition_components_sum_to_total():
    t = _tables_minimal(pop_changes={2023: 60_000}, completions={2023: 25_000},
                        nat_inc_k=30.0, mig_k=20.0)
    dec = dg.gap_decomposition(t)
    assert not dec.empty
    row = dec[dec["year"] == 2023].iloc[0]
    total = int(row["population_growth_demand"]) + int(row["hh_size_change_demand"]) + int(row["replacement_demand"])
    assert abs(total - int(row["total_demand"])) <= 2, (
        f"components {total} should sum to total_demand {int(row['total_demand'])}")


def test_cumulative_gap_direction():
    t = _tables_minimal(pop_changes={2022: 60_000, 2023: 60_000},
                        completions={2022: 10_000, 2023: 10_000},
                        nat_inc_k=30.0, mig_k=20.0)
    cum = dg.cumulative_gap(t, from_year=2022)
    assert cum > 0, "persistent shortfall should give positive cumulative gap"


def test_gap_kpis_keys():
    t = _tables_minimal(pop_changes={2023: 50_000}, completions={2023: 30_000})
    kpis = dg.gap_kpis(t)
    for k in ("latest_year", "latest_gap", "cumulative_gap_since_2017", "avg_annual_demand", "avg_annual_supply"):
        assert k in kpis, k


# --------------------------------------------------------------------------- integration: real data
def test_national_gap_real_data(tables):
    ng = dg.national_gap(tables)
    assert not ng.empty, "national_gap should return rows for the real dataset"
    assert (ng["demand_central"] > 0).all(), "all demand estimates should be positive"
    assert (ng["demand_high"] >= ng["demand_central"]).all()
    assert (ng["demand_central"] >= ng["demand_low"]).all()
    full = ng[~ng["is_partial_year"]]
    assert len(full) >= 3, "should have at least 3 full years"


def test_county_gap_real_data_all_counties(tables):
    cg = dg.county_gap(tables)
    assert not cg.empty
    counties = set(tables["dim_county"]["county"])
    gap_counties = set(cg["county"])
    assert counties.issubset(gap_counties), f"missing counties: {counties - gap_counties}"


def test_gap_decomposition_real_data(tables):
    dec = dg.gap_decomposition(tables)
    assert not dec.empty
    assert (dec["replacement_demand"] > 0).all()
    assert (dec["total_demand"] > 0).all()


def test_gap_insight_included_in_insights(tables):
    from src.analysis.insights import generate_insights
    insights = generate_insights(tables)
    ids = [i.id for i in insights]
    assert "supply_demand_gap" in ids, "demand-gap insight should be generated from real data"
