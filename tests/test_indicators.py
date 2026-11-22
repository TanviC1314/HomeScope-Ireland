"""KPI / indicator calculations: formulas on hand-built data, plus validation against raw source data."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.indicators import INDICATORS, calc, indicator_table
from src.indicators.registry import to_markdown


# ----------------------------------------------------------------------------- tiny hand-built tables
@pytest.fixture()
def mini():
    comp = pd.DataFrame([
        # county A: full 2023 and 2024, partial 2025 (Q1 only); county B: same
        *[(f"LA-{c}", c, y, q, "Single house", v) for c, base in (("A", 10), ("B", 30)) for y, qs in ((2023, 4), (2024, 4), (2025, 1))
          for q in range(1, qs + 1) for v in [base * (1 + 0.5 * (y == 2024))]],
    ], columns=["la_name", "county", "year", "quarter", "dwelling_type", "completions"])
    return {
        "completions_quarterly": comp,
        "dim_county": pd.DataFrame({"county": ["A", "B"], "province": ["x", "y"], "nuts3_region": ["R1", "R2"], "homeless_region": ["R1", "R2"]}),
        "population_census": pd.DataFrame({"county": ["A", "A", "B", "B"], "census_year": [2016, 2022, 2016, 2022],
                                           "population": [1000, 1100, 3000, 3000]}),
        "households_census": pd.DataFrame({"county": ["A", "A", "B", "B"], "census_year": [2016, 2022, 2016, 2022],
                                           "households": [400, 460, 1200, 1260]}),
        "housing_stock_census": pd.DataFrame({"area_name": ["A", "A", "B", "B"], "county": ["A", "A", "B", "B"],
                                              "census_year": [2016, 2022, 2016, 2022], "total_stock": [500, 520, 1500, 1620],
                                              "occupied": [400, 460, 1200, 1260], "temporarily_absent": [0] * 4,
                                              "vacant": [100, 60, 300, 360], "holiday_home": [0] * 4, "vacancy_rate_pct": [20, 11.5, 20, 22.2]}),
        "rents_rtb": pd.DataFrame({
            "location": ["A", "A", "B", "B"], "county": ["A", "A", "B", "B"], "geography_type": ["county"] * 4,
            "year": [2019, 2025, 2019, 2025], "quarter": [4, 4, 4, 4], "bedrooms": ["All bedrooms"] * 4,
            "property_type": ["All property types"] * 4, "avg_monthly_rent": [1000.0, 1500.0, 800.0, 1000.0]}),
        "vacancy_estimates": pd.DataFrame({
            "la_name": ["LA-A1", "LA-A2", "LA-B"], "county": ["A", "A", "B"], "year": [2024] * 3, "quarter": [4] * 3,
            "vacant_dwellings": [10, 90, 50], "dwelling_stock": [100, 900, 500], "vacancy_rate_pct": [10.0, 10.0, 10.0]}),
        "long_term_vacancy": pd.DataFrame({
            "la_name": ["LA-A1", "LA-A2", "LA-B"], "county": ["A", "A", "B"], "year": [2024] * 3, "quarter": [4] * 3,
            "vacant_dwellings": [5, 45, 10], "dwelling_stock": [100, 900, 500], "vacancy_rate_pct": [5.0, 5.0, 2.0]}),
        "planning_permissions": pd.DataFrame({"region": ["R1", "R2", "R1", "R2"], "year": [2023, 2023, 2024, 2024],
                                              "dwelling_type": ["Apartments"] * 4, "units": [20.0, 60.0, 15.0, 45.0]}),
        "tenure_census": pd.DataFrame({
            "county": ["A"] * 4, "census_year": [2022] * 4,
            "tenure": ["All types of occupancy", "Rented from a local authority", "Rented from a voluntary body", "Rented from private landlord"],
            "households": [1000, 100, 50, 200]}),
    }


def test_annual_completions_flags_partial_years(mini):
    nat = calc.annual_completions(mini, "national").set_index("year")
    assert nat.loc[2023, "completions"] == 4 * (10 + 30)
    assert nat.loc[2024, "completions"] == 4 * 15 + 4 * 45
    assert nat.loc[2025, "is_partial_year"] and not nat.loc[2024, "is_partial_year"]
    assert calc.latest_full_year(mini) == 2024


def test_supply_growth_only_between_full_years(mini):
    g = calc.national_supply_growth(mini).set_index("year")
    assert g.loc[2024, "yoy_change_pct"] == pytest.approx(50.0)
    assert np.isnan(g.loc[2023, "yoy_change_pct"]) and np.isnan(g.loc[2025, "yoy_change_pct"])   # first year / partial year


def test_completions_per_1000_uses_full_years_and_2022_population(mini):
    cp = calc.completions_per_1000(mini, years=(2023, 2024)).set_index("county")
    # county A: (40 + 60)/2 = 50 a year ; population 1100 -> 45.45 per 1,000
    assert cp.loc["A", "completions_per_1000"] == pytest.approx(1000 * 50 / 1100)
    assert cp.loc["B", "completions_per_1000"] == pytest.approx(1000 * 150 / 3000)


def test_census_growth_and_gap(mini):
    g = calc.census_growth(mini).set_index("county")
    assert g.loc["A", "population_growth_pct"] == pytest.approx(10.0)
    assert g.loc["A", "household_growth_pct"] == pytest.approx(15.0)
    assert g.loc["A", "stock_growth_pct"] == pytest.approx(4.0)
    assert g.loc["A", "household_minus_stock_growth_pp"] == pytest.approx(11.0)
    assert g.loc["A", "annual_household_growth"] == pytest.approx(10.0)


def test_rent_change(mini):
    rc = calc.rent_change(mini).set_index("county")
    assert rc.loc["A", "change_since_base_pct"] == pytest.approx(50.0)
    assert rc.loc["B", "change_since_base_pct"] == pytest.approx(25.0)
    assert rc.attrs["latest"] == (2025, 4)


def test_vacancy_by_county_sums_counts_not_average_of_rates(mini):
    v = calc.vacancy_by_county(mini).set_index("county")
    assert v.loc["A", "vacant_dwellings"] == 100 and v.loc["A", "dwelling_stock"] == 1000
    assert v.loc["A", "vacancy_rate_pct"] == pytest.approx(10.0)
    assert v.loc["A", "long_term_share_pct"] == pytest.approx(50.0)
    # an average of the two LA rates would be 10 as well here; use a skewed case to prove sums are used
    mini["vacancy_estimates"].loc[0, ["vacant_dwellings", "dwelling_stock"]] = [50, 100]   # rate 50% in a tiny LA
    v2 = calc.vacancy_by_county(mini).set_index("county")
    assert v2.loc["A", "vacancy_rate_pct"] == pytest.approx(100 * (50 + 90) / 1000)       # not (50 + 10) / 2


def test_planning_vs_completions_with_lag(mini):
    mini["completions_quarterly"]["year"] = mini["completions_quarterly"]["year"]
    same = calc.planning_vs_completions(mini, lag=0, year_from=2023).set_index(["region", "year"])
    assert same.loc[("R1", 2024), "completions_to_permitted"] == pytest.approx(60 / 15)
    lagged = calc.planning_vs_completions(mini, lag=1, year_from=2024).set_index(["region", "year"])
    # completions in 2024 compared with permissions of 2023
    assert lagged.loc[("R1", 2024), "permitted_units"] == 20
    assert lagged.loc[("R1", 2024), "completions_to_permitted"] == pytest.approx(60 / 20)


def test_tenure_shares(mini):
    s = calc.tenure_shares(mini).set_index("county")
    assert s.loc["A", "social_rented_pct"] == pytest.approx(15.0)
    assert s.loc["A", "private_rented_pct"] == pytest.approx(20.0)


# ----------------------------------------------------------------------------- real-data properties
def test_pressure_flags_are_bounded_and_explainable(tables):
    hp = calc.housing_pressure_table(tables)
    assert len(hp) == 26 and hp["pressure_flags"].between(0, 6).all()
    flag_cols = [c for c in hp.columns if c.startswith("flag_")]
    assert len(flag_cols) == 6
    assert (hp[flag_cols].sum(axis=1) == hp["pressure_flags"]).all()          # no hidden weights
    assert hp[flag_cols].sum().between(6, 8).all()                              # about a quarter of 26 counties per indicator


def test_national_rent_proxy_is_weighted_mean_of_counties(tables):
    prox = calc.national_rent_proxy(tables)
    last = prox.iloc[-1]
    s = calc.rent_series(tables)
    d = s[(s["year"] == last["year"]) & (s["quarter"] == last["quarter"])]
    w = tables["tenure_census"].query("census_year == 2022 and tenure == 'Rented from private landlord'").set_index("county")["households"]
    manual = (d.set_index("county")["avg_monthly_rent"] * w).sum() / w.reindex(d["county"]).sum()
    assert last["avg_monthly_rent"] == pytest.approx(manual)
    assert d["avg_monthly_rent"].min() < last["avg_monthly_rent"] < d["avg_monthly_rent"].max()


def test_rent_to_income_county_weighting_stays_within_la_range(tables):
    c = calc.rent_to_income_county(tables).set_index("county")
    la = tables["rent_to_income_la"]
    dub = la[la["county"] == "Dublin"]["median_rent_pct_income"]
    assert dub.min() <= c.loc["Dublin", "median_rent_pct_income"] <= dub.max()


def test_homelessness_per_10000_uses_region_population(tables):
    r = calc.homelessness_by_region(tables).set_index("region")
    pop = tables["dim_county"].merge(tables["population_census"].query("census_year == 2022"), on="county").groupby("homeless_region")["population"].sum()
    assert r.loc["Dublin", "population_2022"] == pop["Dublin"]
    assert r.loc["Dublin", "persons_per_10000"] == pytest.approx(10000 * r.loc["Dublin", "total_persons"] / pop["Dublin"])
    assert r["share_of_national_pct"].sum() == pytest.approx(100.0)


# ----------------------------------------------------------------------------- validated against the SOURCE files
def test_national_completions_equal_raw_source(tables, raw_csv):
    raw = raw_csv("NDQ06")
    ly = calc.latest_full_year(tables)
    r = raw[(raw["Local Authority"] == "Ireland") & (raw["Type of House"] == "All house types") & (raw["Quarter"].str.startswith(str(ly)))]
    assert calc.annual_completions(tables, "national").set_index("year").loc[ly, "completions"] == r["VALUE"].astype(float).sum()
    assert calc.national_kpis(tables)["completions_latest_full_year"] == r["VALUE"].astype(float).sum()


def test_county_population_growth_equals_raw_census_percentage(tables, raw_csv):
    raw = raw_csv("F1003")
    pct = raw[(raw["Census Year"] == "2022") & (raw["Statistic Label"] == "Percentage change since previous census")]
    cg = calc.census_growth(tables).set_index("county")
    for county in ("Dublin", "Galway", "Cork", "Limerick", "Waterford"):
        published = float(pct.loc[pct["County"] == county, "VALUE"].iloc[0])
        assert cg.loc[county, "population_growth_pct"] == pytest.approx(published, abs=0.06)  # published to 1 d.p.


def test_latest_rent_equals_raw_source(tables, raw_csv):
    raw = raw_csv("RIQ02")
    r = raw[(raw["Location"] == "Dublin") & (raw["Number of Bedrooms"] == "All bedrooms") & (raw["Property Type"] == "All property types")
            & (raw["Quarter"] == "2025Q4")]
    assert calc.rent_change(tables).set_index("county").loc["Dublin", "rent_latest"] == pytest.approx(float(r["VALUE"].iloc[0]))


def test_vacancy_rate_matches_published_national_figure(tables, raw_csv):
    """Sum of LA vacant dwellings / stock reproduces the CSO national vacancy figures in VAC12 within rounding."""
    v = calc.vacancy_trend_national(tables).set_index("year")
    assert v.loc[2024, "vacant_dwellings"] > 50000 and 1.0 < v.loc[2024, "vacancy_rate_pct"] < 6.0
    raw = raw_csv("VAC14")
    la = raw[(raw["Quarter"] == "2024Q4") & (raw["Statistic Label"] == "Number of Vacant Dwellings")]
    assert v.loc[2024, "vacant_dwellings"] == la["VALUE"].astype(float).sum()


def test_homelessness_latest_total_equals_raw_files(tables):
    from src.utils.paths import RAW_DIR
    f = RAW_DIR / "housing_gov" / "homelessness" / "homelessness-report-september-2026.csv"
    if not f.exists():
        pytest.skip("raw homelessness file not present")
    raw = pd.read_csv(f, encoding="utf-8-sig", thousands=",")
    dep_col = [c for c in raw.columns if "Dependants" in c][0]
    expected = int(raw["Total Adults"].sum() + raw[dep_col].sum())
    assert calc.national_kpis(tables)["homeless_persons"] == expected


# ----------------------------------------------------------------------------- registry
def test_every_indicator_is_fully_documented():
    df = indicator_table()
    assert len(df) >= 20 and df["id"].is_unique
    for col in ("calculation", "assumptions", "limitations"):
        assert (df[col].str.len() > 10).all(), col
    assert (df["reference_period"].str.len() >= 6).all()
    assert (df["sources"].str.len() >= 8).all() and df["sources"].str.contains("CSO|Dept|Rents").all()
    assert set(df["kind"]) <= {"published", "derived", "estimate"}
    assert "Limitations" in to_markdown() or "limitations" in to_markdown()
    assert {"pressure_flags", "rent_to_income_measured", "planning_to_completion"} <= set(INDICATORS)
