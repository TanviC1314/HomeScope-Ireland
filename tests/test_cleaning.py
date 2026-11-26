"""Cleaning functions: missing values, duplicates, ranges, name standardisation, reconciliation to source."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.data_cleaning import cleaners as C
from src.data_cleaning.quality import QualityReport, check_duplicates, check_missing, check_range, reconcile
from src.utils.paths import PROCESSED_DIR


# ----------------------------------------------------------------------------- generic quality helpers
def test_check_duplicates_keeps_first_and_reports():
    df = pd.DataFrame({"k": [1, 1, 2], "v": [10, 99, 20]})
    rep = QualityReport()
    out = check_duplicates(df, ["k"], "T", rep)
    assert out["v"].tolist() == [10, 20]
    assert rep.issues[0].status == "fixed" and rep.issues[0].affected == 1


def test_check_missing_never_imputes():
    df = pd.DataFrame({"v": [1.0, np.nan, 3.0]})
    rep = QualityReport()
    assert check_missing(df, ["v"], "T", rep) == 1
    assert df["v"].isna().sum() == 1  # unchanged
    assert rep.issues[0].action.startswith("left as missing")


def test_check_range_flags_and_optionally_drops():
    df = pd.DataFrame({"v": [-5, 10, 5000]})
    rep = QualityReport()
    assert len(check_range(df, "v", 0, 1000, "T", rep)) == 3          # flag only
    assert rep.warnings() and rep.warnings()[0].affected == 2
    assert check_range(df, "v", 0, 1000, "T", QualityReport(), drop=True)["v"].tolist() == [10]


def test_reconcile_tolerances():
    rep = QualityReport()
    assert reconcile(rep, "T", "ok", 100, 100.4, tolerance=0.5)
    assert not reconcile(rep, "T", "bad", 100, 120, tolerance=1)
    assert reconcile(rep, "T", "rel", 100000, 100005, rel_tolerance=1e-3)
    assert [i.status for i in rep.issues] == ["pass", "warning", "pass"]


# ----------------------------------------------------------------------------- dataset cleaners (synthetic raw frames)
def _ndq06(rows):
    return pd.DataFrame(rows, columns=["Quarter", "Type of House", "Local Authority", "VALUE"]).assign(
        **{"STATISTIC": "NDQ06"})


def _good_ndq06():
    rows = []
    for q in ("2024Q1", "2024Q2"):
        for la, v in (("Dublin City Council", (10, 5, 20)), ("Cork County Council", (4, 3, 1))):
            for t, x in zip(("Single house", "Scheme house", "Apartment"), v):
                rows.append((q, t, la, str(x)))
            rows.append((q, "All house types", la, str(sum(v))))
        for t, x in zip(("Single house", "Scheme house", "Apartment"), (14, 8, 21)):
            rows.append((q, t, "Ireland", str(x)))
        rows.append((q, "All house types", "Ireland", "43"))
    return rows


def test_clean_completions_basic_and_partial_year_note():
    rep = QualityReport()
    out = C.clean_completions(_ndq06(_good_ndq06()), rep)
    assert set(out["county"]) == {"Dublin", "Cork"}
    assert out["completions"].sum() == 2 * (35 + 8)
    assert not rep.warnings()                       # reconciles to the Ireland rows
    assert any("partial calendar year" in i.detail for i in rep.issues if i.check == "reporting period")
    assert "Ireland" not in out["la_name"].tolist()  # national rows removed after reconciliation


def test_clean_completions_detects_duplicates_and_reconciliation_break():
    rows = _good_ndq06()
    rows.append(rows[0])                             # exact duplicate record
    rows[1] = (rows[1][0], rows[1][1], rows[1][2], "999")  # corrupt a value so parts != published total
    rep = QualityReport()
    out = C.clean_completions(_ndq06(rows), rep)
    assert any(i.check == "duplicate keys" and i.status == "fixed" for i in rep.issues)
    assert rep.warnings(), "reconciliation failure must raise a warning"
    assert out.duplicated(["la_name", "year", "quarter", "dwelling_type"]).sum() == 0


def test_blank_planning_values_stay_missing_not_zero():
    raw = pd.DataFrame({
        "Statistic Label": ["Units for which Permission Granted"] * 3,
        "Year": ["2012", "2012", "2012"],
        "NUTS 3 Region": ["Border", "Border", "Ireland"],
        "Type of Dwelling": ["One off houses", "Apartments", "Apartments"],
        "VALUE": ["100", None, "5"]})
    out = C.clean_planning(raw, QualityReport())
    assert out.loc[out["dwelling_type"] == "Apartments", "units"].isna().all()   # blank stays NaN
    assert (out["units"].fillna(-1) >= -1).all()
    assert "Ireland" not in out["region"].tolist()


def test_rents_missing_rows_dropped_and_reported_not_zeroed():
    raw = pd.DataFrame({"Quarter": ["2024Q4"] * 3, "Number of Bedrooms": ["All bedrooms"] * 3,
                        "Property Type": ["All property types"] * 3, "Location": ["Dublin", "Kilkenny City", "Cavan"],
                        "VALUE": ["2000.5", "1200", None]})
    rep = QualityReport()
    out = C.clean_rents(raw, rep)
    assert len(out) == 2 and (out["avg_monthly_rent"] > 0).all()
    assert out.loc[out["location"] == "Kilkenny City", "county"].iloc[0] == "Kilkenny"
    assert out.loc[out["location"] == "Kilkenny City", "geography_type"].iloc[0] == "city"
    assert any("missing values" in i.check and i.affected == 1 for i in rep.issues)


def test_social_need_keeps_national_total_separately():
    raw = pd.DataFrame({
        "County": ["All Counties", "Carlow", "Dublin", "All Counties", "Carlow", "Dublin"],
        "Household Structure": ["All households with children"] * 6, "Number of Children": ["All households with children"] * 6,
        "Year": ["2017"] * 3 + ["2018"] * 3, "VALUE": ["30", "10", "20", "99", None, None]})
    rep = QualityReport()
    county, national = C.clean_social_need(raw, rep)
    assert county["year"].unique().tolist() == [2017]        # 2018 has no county breakdown
    assert national.set_index("year")["households_with_children_in_need"].to_dict() == {2017: 30.0, 2018: 99.0}


def test_homelessness_thousands_separators_are_parsed(tmp_path):
    header = "Region,Total Adults,Male Adults,Female Adults,Number of Families,Number of Dependants in Families\n"
    regions = ["Dublin", "Mid-East", "Midlands", "Mid-West", "North-East", "North-West", "South-East", "South-West", "West"]
    for month in ("january-2019", "february-2019"):
        body = "".join(f'{r},"{4258 if r == "Dublin" else 100}",1,1,10,20\n' for r in regions)
        (tmp_path / f"homelessness-report-{month}.csv").write_text(header + body, encoding="utf-8")
    rep = QualityReport()
    out = C.clean_homelessness(tmp_path, rep)
    assert out.loc[out["region"] == "Dublin", "adults_total"].tolist() == [4258, 4258]
    assert out["total_persons"].notna().all()
    assert not rep.warnings()


def test_homelessness_anomaly_check_flags_a_break(tmp_path):
    header = "Region,Total Adults,Number of Dependants in Families\n"
    regions = ["Dublin", "Mid-East", "Midlands", "Mid-West", "North-East", "North-West", "South-East", "South-West", "West"]
    for month, val in (("january-2020", 100), ("february-2020", 20)):    # 80% fall = implausible
        (tmp_path / f"homelessness-report-{month}.csv").write_text(header + "".join(f"{r},{val},0\n" for r in regions), encoding="utf-8")
    rep = QualityReport()
    C.clean_homelessness(tmp_path, rep)
    assert any("anomaly" in w.check for w in rep.warnings())


# ----------------------------------------------------------------------------- real processed data
def test_quality_report_has_no_warnings():
    report = json.loads((PROCESSED_DIR / "data_quality_report.json").read_text(encoding="utf-8"))
    assert len(report) > 50
    assert [r for r in report if r["status"] == "warning"] == []


def test_processed_tables_have_no_duplicate_keys_or_negative_counts(tables):
    keys = {
        "completions_quarterly": ["la_name", "year", "quarter", "dwelling_type"],
        "commencements_monthly": ["la_name", "period"], "planning_permissions": ["region", "year", "dwelling_type"],
        "population_census": ["county", "census_year"], "households_census": ["county", "census_year"],
        "housing_stock_census": ["area_name", "census_year"], "tenure_census": ["county", "census_year", "tenure"],
        "vacancy_estimates": ["la_name", "year", "quarter"], "vacancy_reasons_census": ["la_name", "reason"],
        "rents_rtb": ["location", "year", "quarter", "bedrooms", "property_type"],
        "property_price_index": ["geography", "dwelling_type", "period"], "homelessness_monthly": ["region", "report_month"],
    }
    for name, k in keys.items():
        assert not tables[name].duplicated(k).any(), name
    for name, col in (("completions_quarterly", "completions"), ("commencements_monthly", "units"), ("population_census", "population"),
                      ("vacancy_estimates", "vacant_dwellings"), ("homelessness_monthly", "total_persons")):
        assert (tables[name][col].dropna() >= 0).all(), name


def test_every_county_present_in_county_level_tables(tables):
    counties = set(tables["dim_county"]["county"])
    for name in ("completions_quarterly", "population_census", "population_county_estimates", "households_census", "housing_stock_census",
                 "tenure_census", "vacancy_estimates", "household_income_county", "social_housing_need"):
        assert set(tables[name]["county"]) == counties, name
    assert set(tables["rents_rtb"].query("geography_type == 'county'")["county"]) == counties


def test_reconciles_to_published_national_totals(tables, raw_csv):
    """Sum of cleaned local-authority completions equals the CSO 'Ireland' row for every quarter."""
    raw = raw_csv("NDQ06")
    nat = raw[(raw["Local Authority"] == "Ireland") & (raw["Type of House"] != "All house types")].copy()
    nat["v"] = pd.to_numeric(nat["VALUE"])
    expected = nat.groupby("Quarter")["v"].sum()
    c = tables["completions_quarterly"]
    got = c.assign(q=c["year"].astype(str) + "Q" + c["quarter"].astype(str)).groupby("q")["completions"].sum()
    pd.testing.assert_series_equal(got.sort_index(), expected.sort_index(), check_names=False, check_dtype=False)


def test_county_population_estimates_cleaning_converts_thousands_and_reconciles():
    rows = []
    for year in ("2022", "2023"):
        for county, v in (("Ireland", "30.0"), ("Co. Carlow", "10.0"), ("Co. Cavan", "20.0")):
            rows.append({"Age Group": "All ages", "Sex": "Both sexes", "Year": year, "County": county, "VALUE": v})
        rows.append({"Age Group": "0 - 4 years", "Sex": "Both sexes", "Year": year, "County": "Co. Carlow", "VALUE": "1.0"})
        rows.append({"Age Group": "All ages", "Sex": "Male", "Year": year, "County": "Co. Carlow", "VALUE": "5.0"})
    rep = QualityReport()
    out = C.clean_population_county_estimates(pd.DataFrame(rows), rep)
    assert len(out) == 4                                                   # age bands and single-sex rows excluded
    assert out.loc[(out["county"] == "Carlow") & (out["year"] == 2022), "population"].iloc[0] == 10_000
    assert not rep.warnings()


def test_county_population_estimates_match_national_series(tables):
    county = tables["population_county_estimates"].groupby("year")["population"].sum()
    national = tables["population_national"].set_index("year")["population_thousand"] * 1000
    for year, total in county.items():
        assert abs(total - national[year]) <= 1300, year                   # county rounding only


def test_census_population_matches_raw_state_total(tables, raw_csv):
    raw = raw_csv("F1003")
    state = raw[(raw["County"] == "State") & (raw["Census Year"] == "2022") & (raw["Statistic Label"] == "Population")]
    assert int(state["VALUE"].iloc[0]) == tables["population_census"].query("census_year == 2022")["population"].sum()
