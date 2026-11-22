"""Create the PostgreSQL schema and load the processed tables.

    python -m src.database.loader            # create schema if needed, seed dimensions, refresh all fact tables
    python -m src.database.loader --reset    # drop every HomeScope table first (clean rebuild)

The loader performs a *full refresh* of the fact tables, so it can be re-run safely after the
pipeline has produced new processed files.
"""
from __future__ import annotations

import argparse
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.database.connection import get_engine
from src.utils.logging_config import get_logger
from src.utils.paths import DATABASE_DIR, PROCESSED_DIR

log = get_logger("loader")

ALL_TABLES = [
    "fact_homelessness", "fact_social_housing_need_national", "fact_social_housing_need", "fact_rent_to_income_la",
    "fact_household_income_national", "fact_household_income_county", "fact_property_price_index", "fact_rent_rtb",
    "fact_vacancy_reason_census", "fact_long_term_vacancy", "fact_vacancy_estimate", "fact_tenure_census",
    "fact_housing_stock_census", "fact_households_census", "fact_population_national", "fact_population_census",
    "fact_planning_permissions_national", "fact_planning_permissions", "fact_commencements", "fact_completions",
    "dim_local_authority", "dim_county", "dim_region", "data_source",
]
VIEWS = ["v_completions_county_year", "v_county_census_2022"]


def _nullsafe(df: pd.DataFrame) -> pd.DataFrame:
    """Convert pandas NA/NaN to None so psycopg2 inserts SQL NULLs."""
    return df.astype(object).where(df.notna(), None)


def apply_sql_file(conn: Connection, path) -> None:
    conn.exec_driver_sql(path.read_text(encoding="utf-8"))


def reset_schema(conn: Connection) -> None:
    for v in VIEWS:
        conn.execute(text(f"DROP VIEW IF EXISTS {v} CASCADE"))
    for t in ALL_TABLES:
        conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
    log.info("dropped existing HomeScope tables")


def _ids(conn: Connection) -> Dict[str, Dict]:
    county = dict(conn.execute(text("SELECT county_name, county_id FROM dim_county")).all())
    la = dict(conn.execute(text("SELECT la_name, la_id FROM dim_local_authority")).all())
    region = {(t, n): i for i, n, t in conn.execute(text("SELECT region_id, region_name, region_type FROM dim_region")).all()}
    return {"county": county, "la": la, "region": region}


Builder = Callable[[pd.DataFrame, Dict[str, Dict]], pd.DataFrame]


def _with_la(cols: List[str]) -> Builder:
    def build(df, ids):
        out = df.assign(la_id=df["la_name"].map(ids["la"]))
        if out["la_id"].isna().any():
            raise ValueError(f"unmapped local authorities: {out.loc[out['la_id'].isna(), 'la_name'].unique()[:5]}")
        return out[["la_id"] + cols]
    return build


def _with_county(cols: List[str], extra_first: Optional[List[str]] = None) -> Builder:
    def build(df, ids):
        out = df.assign(county_id=df["county"].map(ids["county"]))
        if out["county_id"].isna().any():
            raise ValueError(f"unmapped counties: {out.loc[out['county_id'].isna(), 'county'].unique()[:5]}")
        return out[(extra_first or []) + ["county_id"] + cols]
    return build


def _with_region(rtype: str, cols: List[str]) -> Builder:
    def build(df, ids):
        out = df.assign(region_id=df["region"].map(lambda r: ids["region"].get((rtype, r))))
        if out["region_id"].isna().any():
            raise ValueError(f"unmapped {rtype} regions: {out.loc[out['region_id'].isna(), 'region'].unique()[:5]}")
        return out[["region_id"] + cols]
    return build


def _direct(df, ids):
    return df


def _data_source(df, ids):
    out = df.rename(columns={}).copy()
    for c in ("publication_updated", "retrieved_utc"):
        out[c] = out[c].replace("", None)
    out["publication_updated"] = pd.to_datetime(out["publication_updated"], errors="coerce").dt.date
    out["retrieved_utc"] = pd.to_datetime(out["retrieved_utc"], errors="coerce", utc=True)
    return out[["source_key", "title", "provider", "theme", "landing_url", "download_url", "licence", "granularity",
                "publication_updated", "reference_period", "retrieved_utc", "raw_rows", "status", "use_in_project", "notes"]]


# processed CSV name -> (DB table, builder, date columns to parse)
LOAD_PLAN: List[Tuple[str, str, Builder, List[str]]] = [
    ("data_sources", "data_source", _data_source, []),
    ("completions_quarterly", "fact_completions", _with_la(["year", "quarter", "dwelling_type", "completions"]), []),
    ("commencements_monthly", "fact_commencements", _with_la(["period", "year", "month", "notices", "units", "one_off_units"]), ["period"]),
    ("planning_permissions", "fact_planning_permissions",
     _with_region("NUTS3", ["year", "dwelling_type", "permissions", "units", "floor_area_000_sqm", "avg_floor_area_sqm"]), []),
    ("planning_permissions_national", "fact_planning_permissions_national", _direct, []),
    ("population_census", "fact_population_census", _with_county(["census_year", "population", "change_since_previous", "pct_change_since_previous"]), []),
    ("population_national", "fact_population_national", _direct, []),
    ("households_census", "fact_households_census", _with_county(["census_year", "households", "persons_in_households", "avg_household_size"]), []),
    ("housing_stock_census", "fact_housing_stock_census",
     _with_county(["census_year", "total_stock", "occupied", "temporarily_absent", "vacant", "holiday_home", "vacancy_rate_pct"], ["area_name"]), []),
    ("tenure_census", "fact_tenure_census", _with_county(["census_year", "tenure", "households"]), []),
    ("vacancy_estimates", "fact_vacancy_estimate", _with_la(["year", "quarter", "vacant_dwellings", "dwelling_stock", "vacancy_rate_pct"]), []),
    ("long_term_vacancy", "fact_long_term_vacancy", _with_la(["year", "quarter", "vacant_dwellings", "dwelling_stock", "vacancy_rate_pct"]), []),
    ("vacancy_reasons_census", "fact_vacancy_reason_census", _with_la(["reason", "vacant_dwellings"]), []),
    ("rents_rtb", "fact_rent_rtb",
     _with_county(["geography_type", "year", "quarter", "bedrooms", "property_type", "avg_monthly_rent"], ["location"]), []),
    ("property_price_index", "fact_property_price_index", _direct, ["period"]),
    ("household_income_county", "fact_household_income_county",
     _with_county(["year", "disposable_income_per_person", "total_income_per_person", "disposable_household_income_m", "total_household_income_m"]), []),
    ("household_income_national", "fact_household_income_national", _direct, []),
    ("rent_to_income_la", "fact_rent_to_income_la",
     _with_la(["year", "median_rent_pct_income", "pct_tenants_40plus", "pct_tenants_45plus", "pct_tenants_50plus"]), []),
    ("social_housing_need", "fact_social_housing_need", _with_county(["year", "households_with_children_in_need"]), []),
    ("social_housing_need_national", "fact_social_housing_need_national", _direct, []),
    ("homelessness_monthly", "fact_homelessness",
     _with_region("HOMELESS", ["report_month", "adults_total", "adults_male", "adults_female", "adults_18_24", "adults_25_44",
                               "adults_45_64", "adults_65_plus", "private_emergency", "supported_temporary", "temporary_emergency",
                               "other_accommodation", "families", "adults_in_families", "single_parent_families", "dependants",
                               "total_persons"]), ["report_month"]),
]


def load_all(engine: Optional[Engine] = None, reset: bool = False) -> Dict[str, int]:
    engine = engine or get_engine()
    counts: Dict[str, int] = {}
    with engine.begin() as conn:
        if reset:
            reset_schema(conn)
        apply_sql_file(conn, DATABASE_DIR / "schema.sql")
        apply_sql_file(conn, DATABASE_DIR / "seed_data.sql")
        facts = [p[1] for p in LOAD_PLAN]
        conn.execute(text("TRUNCATE TABLE " + ", ".join(facts)))  # full refresh of facts + provenance
        ids = _ids(conn)
        for name, table, build, dates in LOAD_PLAN:
            df = pd.read_csv(PROCESSED_DIR / f"{name}.csv", parse_dates=dates, keep_default_na=True)
            out = _nullsafe(build(df, ids))
            out.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=2000)
            counts[table] = len(out)
            log.info("%-36s %7d rows", table, len(out))
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Load processed HomeScope data into PostgreSQL")
    ap.add_argument("--reset", action="store_true", help="drop all HomeScope tables before loading")
    load_all(reset=ap.parse_args().reset)


if __name__ == "__main__":
    main()
