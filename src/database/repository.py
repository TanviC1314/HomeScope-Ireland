"""Read access to the analytical tables.

``load_tables()`` returns the same dictionary of DataFrames whether the data come from PostgreSQL or
from the processed CSV files, so the indicators, insights, simulator and dashboard never care which
backend is active.  Backend selection (env ``HOMESCOPE_DATA_BACKEND``): ``auto`` (default) uses
PostgreSQL when it is reachable and falls back to the CSVs; ``postgres`` and ``csv`` force one.
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.database.connection import can_connect, get_engine
from src.utils.paths import PROCESSED_DIR

Tables = Dict[str, pd.DataFrame]

DATE_COLUMNS = {
    "commencements_monthly": ["period"], "property_price_index": ["period"], "homelessness_monthly": ["report_month"],
}

_LA = "JOIN dim_local_authority la ON la.la_id = f.la_id JOIN dim_county c ON c.county_id = la.county_id"

TABLE_SQL: Dict[str, str] = {
    "dim_county": """SELECT c.county_name AS county, c.province, rn.region_name AS nuts3_region, rh.region_name AS homeless_region
                     FROM dim_county c JOIN dim_region rn ON rn.region_id = c.nuts3_region_id
                     JOIN dim_region rh ON rh.region_id = c.homeless_region_id ORDER BY c.county_name""",
    "dim_local_authority": """SELECT la.la_name, c.county_name AS county, la.la_type FROM dim_local_authority la
                              JOIN dim_county c ON c.county_id = la.county_id ORDER BY la.la_name""",
    "dim_region": "SELECT region_name, region_type FROM dim_region ORDER BY region_type, region_name",
    "data_sources": "SELECT * FROM data_source ORDER BY source_key",
    "completions_quarterly": f"""SELECT la.la_name, c.county_name AS county, f.year, f.quarter, f.dwelling_type, f.completions
                                 FROM fact_completions f {_LA}""",
    "commencements_monthly": f"""SELECT la.la_name, c.county_name AS county, f.period, f.year, f.month, f.notices, f.units, f.one_off_units
                                 FROM fact_commencements f {_LA}""",
    "planning_permissions": """SELECT r.region_name AS region, p.year, p.dwelling_type, p.permissions, p.units, p.floor_area_000_sqm, p.avg_floor_area_sqm
                               FROM fact_planning_permissions p JOIN dim_region r ON r.region_id = p.region_id""",
    "planning_permissions_national": "SELECT year, dwelling_type, permissions, units FROM fact_planning_permissions_national",
    "population_census": """SELECT c.county_name AS county, p.census_year, p.population, p.change_since_previous, p.pct_change_since_previous
                            FROM fact_population_census p JOIN dim_county c ON c.county_id = p.county_id""",
    "population_national": "SELECT year, population_thousand, births_thousand, deaths_thousand, emigrants_thousand, immigrants_thousand, "
                           "natural_increase_thousand, net_migration_thousand, population_change_thousand FROM fact_population_national",
    "households_census": """SELECT c.county_name AS county, h.census_year, h.households, h.persons_in_households, h.avg_household_size
                            FROM fact_households_census h JOIN dim_county c ON c.county_id = h.county_id""",
    "housing_stock_census": """SELECT s.area_name, c.county_name AS county, s.census_year, s.total_stock, s.occupied, s.temporarily_absent,
                               s.vacant, s.holiday_home, s.vacancy_rate_pct
                               FROM fact_housing_stock_census s JOIN dim_county c ON c.county_id = s.county_id""",
    "tenure_census": """SELECT c.county_name AS county, t.census_year, t.tenure, t.households
                        FROM fact_tenure_census t JOIN dim_county c ON c.county_id = t.county_id""",
    "vacancy_estimates": f"""SELECT la.la_name, c.county_name AS county, f.year, f.quarter, f.vacant_dwellings, f.dwelling_stock, f.vacancy_rate_pct
                             FROM fact_vacancy_estimate f {_LA}""",
    "long_term_vacancy": f"""SELECT la.la_name, c.county_name AS county, f.year, f.quarter, f.vacant_dwellings, f.dwelling_stock, f.vacancy_rate_pct
                             FROM fact_long_term_vacancy f {_LA}""",
    "vacancy_reasons_census": f"""SELECT la.la_name, c.county_name AS county, f.reason, f.vacant_dwellings
                                  FROM fact_vacancy_reason_census f {_LA}""",
    "rents_rtb": """SELECT r.location, c.county_name AS county, r.geography_type, r.year, r.quarter, r.bedrooms, r.property_type, r.avg_monthly_rent
                    FROM fact_rent_rtb r JOIN dim_county c ON c.county_id = r.county_id""",
    "property_price_index": "SELECT geography, dwelling_type, period, rppi_index, pct_change_1m, pct_change_3m, pct_change_12m FROM fact_property_price_index",
    "household_income_county": """SELECT c.county_name AS county, i.year, i.disposable_income_per_person, i.total_income_per_person,
                                  i.disposable_household_income_m, i.total_household_income_m
                                  FROM fact_household_income_county i JOIN dim_county c ON c.county_id = i.county_id""",
    "household_income_national": "SELECT year, disposable_income_per_person, total_income_per_person, disposable_household_income_m, "
                                 "total_household_income_m FROM fact_household_income_national",
    "rent_to_income_la": f"""SELECT la.la_name, c.county_name AS county, f.year, f.median_rent_pct_income, f.pct_tenants_40plus,
                             f.pct_tenants_45plus, f.pct_tenants_50plus FROM fact_rent_to_income_la f {_LA}""",
    "social_housing_need": """SELECT c.county_name AS county, n.year, n.households_with_children_in_need
                              FROM fact_social_housing_need n JOIN dim_county c ON c.county_id = n.county_id""",
    "social_housing_need_national": "SELECT year, households_with_children_in_need FROM fact_social_housing_need_national",
    "homelessness_monthly": """SELECT r.region_name AS region, h.report_month, h.adults_total, h.adults_male, h.adults_female, h.adults_18_24,
                               h.adults_25_44, h.adults_45_64, h.adults_65_plus, h.private_emergency, h.supported_temporary,
                               h.temporary_emergency, h.other_accommodation, h.families, h.adults_in_families, h.single_parent_families,
                               h.dependants, h.total_persons FROM fact_homelessness h JOIN dim_region r ON r.region_id = h.region_id""",
}
TABLE_NAMES = list(TABLE_SQL)


def csv_tables() -> Tables:
    out: Tables = {}
    for name in TABLE_NAMES:
        path = PROCESSED_DIR / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run `python -m src.data_cleaning.pipeline` first")
        out[name] = pd.read_csv(path, parse_dates=DATE_COLUMNS.get(name, []))
    return out


def postgres_tables(engine: Optional[Engine] = None) -> Tables:
    engine = engine or get_engine()
    out: Tables = {}
    with engine.connect() as conn:
        for name, sql in TABLE_SQL.items():
            out[name] = pd.read_sql_query(text(sql), conn, coerce_float=True, parse_dates=DATE_COLUMNS.get(name))
    return out


def resolve_backend(requested: Optional[str] = None) -> str:
    requested = (requested or os.getenv("HOMESCOPE_DATA_BACKEND", "auto")).lower()
    if requested == "auto":
        return "postgres" if can_connect() else "csv"
    if requested not in ("csv", "postgres"):
        raise ValueError(f"unknown backend {requested!r}")
    return requested


def load_tables(backend: Optional[str] = None) -> Tuple[Tables, str]:
    """Return (tables, backend_used)."""
    backend = resolve_backend(backend)
    if backend == "postgres":
        try:
            tables = postgres_tables()
            if tables["completions_quarterly"].empty:
                raise RuntimeError("database is empty - run `python -m src.database.loader`")
            return tables, "postgres"
        except Exception:
            if (backend_requested := os.getenv("HOMESCOPE_DATA_BACKEND", "auto").lower()) == "postgres":
                raise
    return csv_tables(), "csv"
