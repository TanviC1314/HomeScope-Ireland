"""County scorecard: every county-level indicator in one tidy table, with display metadata.

Used by the County Comparison page (map, ranking, comparison table).  Each column documents its
unit, how it should be read, and the registry indicator it comes from.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd

from src.indicators import calculations as calc

Tables = Dict[str, pd.DataFrame]


@dataclass(frozen=True)
class ScoreColumn:
    column: str
    label: str
    unit: str          # e.g. "EUR / month", "%", "per 1,000"
    decimals: int
    reading: str       # how to read it
    period: str        # reference period
    indicator_id: str  # registry id


SCORE_COLUMNS = [
    ScoreColumn("rent_latest", "Average monthly rent", "EUR / month", 0, "Higher = more expensive", "Latest quarter (RTB)", "rent_level_change"),
    ScoreColumn("rent_change_since_2019_pct", "Rent change since Q4 2019", "%", 1, "Higher = faster rise", "Q4 2019 to latest", "rent_level_change"),
    ScoreColumn("rent_pct_income", "Median rent as % of disposable income", "%", 1, "Higher = larger burden", "2024", "rent_to_income_measured"),
    ScoreColumn("annual_rent_pct_of_income_per_person", "Annual rent vs income per person (relative)", "%", 0, "Compare counties only; overstates burden", "Latest rent / 2024 income", "rent_vs_income_per_person"),
    ScoreColumn("disposable_income_per_person", "Disposable income per person", "EUR / year", 0, "Higher = more income", "2024", "rent_vs_income_per_person"),
    ScoreColumn("completions_per_1000", "Completions per 1,000 residents (annual avg)", "per 1,000", 1, "Lower = less building relative to population", "Last 3 full years", "completions_per_1000"),
    ScoreColumn("population_growth_pct", "Population growth 2016-2022", "%", 1, "Higher = faster growth", "Census 2016-2022", "population_growth"),
    ScoreColumn("household_growth_pct", "Household growth 2016-2022", "%", 1, "Higher = more new households", "Census 2016-2022", "household_growth"),
    ScoreColumn("stock_growth_pct", "Housing stock growth 2016-2022", "%", 1, "Higher = more dwellings added", "Census 2016-2022", "stock_growth"),
    ScoreColumn("household_minus_stock_growth_pp", "Household minus stock growth", "pp", 1, "Positive = households grew faster than stock", "Census 2016-2022", "household_minus_stock_growth"),
    ScoreColumn("vacancy_rate_pct", "Vacancy rate (estimated)", "%", 1, "Vacant does not mean available or habitable", "Q4 2024", "vacancy_rate_esb"),
    ScoreColumn("long_term_rate_pct", "Long-term vacancy (6 years) as % of stock", "%", 1, "Persistent vacancy", "Q4 2024", "long_term_vacancy"),
    ScoreColumn("need_per_1000_households", "Families in need of social housing per 1,000 households", "per 1,000", 1, "Families with children only", "Latest year", "social_need_per_1000"),
    ScoreColumn("social_rented_pct", "Social rented share of households", "%", 1, "Existing social stock", "Census 2022", "social_rented_share"),
    ScoreColumn("private_rented_pct", "Private rented share of households", "%", 1, "Size of the private rental sector", "Census 2022", "social_rented_share"),
    ScoreColumn("pressure_flags", "Housing-pressure flags (0-6)", "count", 0, "Number of indicators in the most-pressured quartile", "Mixed", "pressure_flags"),
]
BY_COLUMN = {c.column: c for c in SCORE_COLUMNS}


def county_scorecard(t: Tables) -> pd.DataFrame:
    """One row per county with every scorecard indicator."""
    hp = calc.housing_pressure_table(t)[["county", "rent_latest", "rent_change_since_2019_pct", "rent_pct_income", "completions_per_1000",
                                         "household_minus_stock_growth_pp", "need_per_1000_households", "pressure_flags"]]
    cg = calc.census_growth(t)[["county", "population_growth_pct", "household_growth_pct", "stock_growth_pct"]]
    vac = calc.vacancy_by_county(t)[["county", "vacancy_rate_pct", "long_term_rate_pct"]]
    ten = calc.tenure_shares(t)[["county", "social_rented_pct", "private_rented_pct"]]
    inc = calc.rent_vs_income_per_person(t)[["county", "disposable_income_per_person", "annual_rent_pct_of_income_per_person"]]
    out = hp.merge(cg, on="county").merge(vac, on="county").merge(ten, on="county").merge(inc, on="county")
    return out.merge(t["dim_county"][["county", "province", "nuts3_region"]], on="county")


def format_value(column: str, value: float) -> str:
    meta = BY_COLUMN[column]
    if pd.isna(value):
        return "n/a"
    txt = f"{value:,.{meta.decimals}f}"
    return {"%": f"{txt}%", "EUR / month": f"EUR {txt}", "EUR / year": f"EUR {txt}", "pp": f"{txt} pp"}.get(meta.unit, txt)
