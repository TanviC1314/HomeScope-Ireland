"""PostgreSQL: connection, schema constraints, load integrity, SQL query execution and SQL-vs-pandas parity.

These tests run against an isolated, temporary schema (see the ``pg`` fixture) and are skipped automatically
when PostgreSQL is not reachable.
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.database import loader, repository
from src.database.run_queries import load_queries, parse_queries, run_query
from src.indicators import calc
from src.utils.paths import PROCESSED_DIR


def test_connection_and_schema_objects(pg):
    with pg.connect() as c:
        assert c.execute(text("SELECT 1")).scalar() == 1
        tables = {r[0] for r in c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"))}
    assert {"dim_county", "dim_local_authority", "dim_region", "fact_completions", "fact_rent_rtb", "data_source"} <= tables
    assert {"v_completions_county_year", "v_county_census_2022"} <= tables


def test_row_counts_match_processed_files(pg):
    with pg.connect() as c:
        for name, table, _, _ in loader.LOAD_PLAN:
            n = c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            assert n == len(pd.read_csv(PROCESSED_DIR / f"{name}.csv")), table


def test_dimensions_seeded(pg):
    with pg.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM dim_county")).scalar() == 26
        assert c.execute(text("SELECT COUNT(*) FROM dim_local_authority")).scalar() == 31
        assert c.execute(text("SELECT COUNT(*) FROM dim_region")).scalar() == 17


def test_no_orphan_foreign_keys(pg):
    checks = [("fact_completions", "la_id", "dim_local_authority", "la_id"), ("fact_rent_rtb", "county_id", "dim_county", "county_id"),
              ("fact_homelessness", "region_id", "dim_region", "region_id"), ("fact_planning_permissions", "region_id", "dim_region", "region_id"),
              ("fact_vacancy_estimate", "la_id", "dim_local_authority", "la_id")]
    with pg.connect() as c:
        for t, col, pt, pcol in checks:
            orphans = c.execute(text(f"SELECT COUNT(*) FROM {t} x LEFT JOIN {pt} p ON p.{pcol} = x.{col} WHERE p.{pcol} IS NULL")).scalar()
            assert orphans == 0, t


def test_constraints_reject_bad_data(pg):
    with pytest.raises(IntegrityError):
        with pg.begin() as c:
            c.execute(text("INSERT INTO fact_completions VALUES (999999, 2025, 1, 'Single house', 5)"))       # unknown FK
    with pytest.raises(IntegrityError):
        with pg.begin() as c:
            c.execute(text("INSERT INTO fact_completions SELECT la_id, 2025, 9, 'Single house', 5 FROM dim_local_authority LIMIT 1"))  # quarter 9
    with pytest.raises(IntegrityError):
        with pg.begin() as c:   # primary key violation: same (la, year, quarter, type) twice
            c.execute(text("INSERT INTO fact_completions SELECT la_id, year, quarter, dwelling_type, 1 FROM fact_completions LIMIT 1"))


def test_loader_is_idempotent(pg):
    before = repository.postgres_tables(pg)["completions_quarterly"]
    loader.load_all(pg)                      # second full refresh must not duplicate rows
    after = repository.postgres_tables(pg)["completions_quarterly"]
    assert len(before) == len(after)


def test_postgres_and_csv_backends_return_identical_data(pg, tables):
    pgt = repository.postgres_tables(pg)
    assert set(pgt) == set(tables)
    for name in ("completions_quarterly", "population_census", "households_census", "vacancy_estimates", "rent_to_income_la",
                 "homelessness_monthly", "social_housing_need", "tenure_census", "planning_permissions_national"):
        a, b = pgt[name], tables[name]
        cols = list(b.columns)
        key = [c for c in cols if b[c].dtype == object or str(b[c].dtype).startswith(("str", "string"))] or cols[:1]
        a = a[cols].sort_values(cols).reset_index(drop=True)
        b = b[cols].sort_values(cols).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b, check_dtype=False, check_exact=False, rtol=1e-9)


# ----------------------------------------------------------------------------- SQL analytics
def test_queries_file_parses_into_documented_queries():
    qs = load_queries()
    assert 15 <= len(qs) <= 25
    assert len({q.name for q in qs}) == len(qs)
    for q in qs:
        assert q.question and q.techniques and q.sql.upper().lstrip().startswith(("SELECT", "WITH")), q.name
    techniques = " ".join(q.techniques.lower() for q in qs)
    for required in ("join", "cte", "window", "case", "subquery", "group by"):
        assert required in techniques or required.replace("cte", "ctes") in techniques, required


def test_parse_queries_handles_metadata():
    qs = parse_queries("-- name: A_test\n-- question: Q?\n-- techniques: JOIN\n-- caveat: be careful\nSELECT 1 AS x;\n")
    assert qs[0].name == "A_test" and qs[0].caveat == "be careful" and qs[0].sql == "SELECT 1 AS x;"


@pytest.fixture(scope="module")
def sql_results(pg):
    return {q.name: run_query(pg, q) for q in load_queries()}


def test_every_query_executes_and_returns_rows(sql_results):
    for name, df in sql_results.items():
        assert len(df) > 0, name


def test_sql_completions_match_pandas(sql_results, tables):
    sql = sql_results["Q01_completions_by_county_year"].set_index(["county_name", "year"])["completions"]
    py = calc.annual_completions(tables, "county")
    py = py[~py["is_partial_year"] & (py["year"] >= 2015)].set_index(["county", "year"])["completions"]
    assert len(sql) == len(py)
    assert (sql.sort_index().to_numpy() == py.sort_index().to_numpy()).all()


def test_sql_population_growth_matches_pandas(sql_results, tables):
    sql = sql_results["Q04_population_growth_by_county_2016_2022"].set_index("county_name")["pct_change"].astype(float)
    py = calc.census_growth(tables).set_index("county")["population_growth_pct"]
    assert (sql.sort_index() - py.sort_index()).abs().max() < 0.006


def test_sql_vacancy_by_region_matches_pandas(sql_results, tables):
    sql = sql_results["Q10_vacancy_rate_by_nuts3_region"].set_index("region_name")
    v = calc.vacancy_by_county(tables).merge(tables["dim_county"][["county", "nuts3_region"]], on="county")
    g = v.groupby("nuts3_region")[["vacant_dwellings", "dwelling_stock"]].sum()
    assert (sql["vacant_dwellings"].astype(float).sort_index() == g["vacant_dwellings"].sort_index()).all()
    assert (100 * g["vacant_dwellings"] / g["dwelling_stock"] - sql["vacancy_rate_pct"].astype(float)).abs().max() < 0.006


def test_sql_homelessness_per_10000_matches_pandas(sql_results, tables):
    sql = sql_results["Q16_homelessness_per_10000_by_region_latest"].set_index("region_name")["persons_per_10000_residents"].astype(float)
    py = calc.homelessness_by_region(tables).set_index("region")["persons_per_10000"]
    assert (sql.sort_index() - py.sort_index()).abs().max() < 0.06


def test_sql_rent_growth_matches_pandas(sql_results, tables):
    sql = sql_results["Q07_rent_growth_since_2019"].set_index("county_name")["pct_change"].astype(float)
    py = calc.rent_change(tables).set_index("county")["change_since_base_pct"]
    assert (sql.sort_index() - py.sort_index()).abs().max() < 0.06


def test_sql_planning_ratio_matches_pandas(sql_results, tables):
    sql = sql_results["Q11_planning_permissions_vs_completions_by_region"]
    sql = sql[sql["year"] == 2025].set_index("region_name")["completions_to_permitted_same_year"].astype(float)
    py = calc.planning_vs_completions(tables, lag=0, year_from=2025)
    py = py.set_index("region")["completions_to_permitted"]
    assert (sql.sort_index() - py.sort_index()).abs().max() < 0.006
