"""Affordability Pressure Index: formulas on hand-built data, properties, and reconciliation with the processed tables."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.indicators import INDICATORS
from src.indicators import affordability_index as ai
from src.indicators import calculations as calc


# ----------------------------------------------------------------------------- hand-built components
@pytest.fixture()
def comp3():
    """Three counties with raw component values chosen so every standardised score is easy to compute."""
    return pd.DataFrame({
        "county": ["A", "B", "C"], "province": ["p"] * 3, "nuts3_region": ["R"] * 3,
        "rent_burden_pct": [10.0, 20.0, 30.0],
        "rent_vs_income_pct": [40.0, 60.0, 80.0],
        "rent_rise_pct_income": [30.0, 20.0, 10.0],
        "price_growth_pct": [50.0, 50.0, 50.0],           # constant column -> no information
    })


@pytest.fixture()
def comp8():
    rng = np.random.default_rng(7)
    return pd.DataFrame({"county": list("ABCDEFGH"), "province": "p", "nuts3_region": "R",
                         **{c: rng.uniform(1, 100, 8) for c in ai.COLUMNS}})


# ----------------------------------------------------------------------------- weights
def test_default_weights_sum_to_one_and_cover_all_components():
    assert set(ai.DEFAULT_WEIGHTS) == set(ai.COLUMNS)
    assert sum(ai.DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    for scenario in ai.WEIGHT_SCENARIOS.values():
        assert sum(scenario.values()) == pytest.approx(1.0)


def test_validate_weights_normalises_and_rejects_bad_input():
    w = ai.validate_weights({"rent_burden_pct": 2, "rent_vs_income_pct": 2})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["rent_burden_pct"] == pytest.approx(0.5) and w["price_growth_pct"] == 0.0
    with pytest.raises(ValueError, match="Unknown"):
        ai.validate_weights({"nonsense": 1})
    with pytest.raises(ValueError, match="non-negative"):
        ai.validate_weights({"rent_burden_pct": -1, "rent_vs_income_pct": 2})
    with pytest.raises(ValueError, match="positive"):
        ai.validate_weights({c: 0 for c in ai.COLUMNS})


# ----------------------------------------------------------------------------- standardisation
def test_minmax_scores_are_0_to_100_and_constant_columns_are_neutral(comp3):
    z = ai.standardise(comp3, "minmax")
    assert z["rent_burden_pct"].tolist() == [0.0, 50.0, 100.0]
    assert z["rent_rise_pct_income"].tolist() == [100.0, 50.0, 0.0]
    assert z["price_growth_pct"].tolist() == [0.0, 0.0, 0.0]


def test_zscore_has_zero_mean_and_unit_sd(comp8):
    z = ai.standardise(comp8, "zscore")
    assert np.allclose(z.mean(), 0, atol=1e-9) and np.allclose(z.std(ddof=0), 1, atol=1e-9)


def test_rank_standardisation_spans_0_to_100_and_ignores_outliers(comp8):
    comp8.loc[0, "rent_burden_pct"] = 1e6
    z = ai.standardise(comp8, "rank")
    assert z["rent_burden_pct"].min() == 0 and z["rent_burden_pct"].max() == 100
    assert z.loc[0, "rent_burden_pct"] == 100


def test_unknown_standardisation_method_rejected(comp3):
    with pytest.raises(ValueError):
        ai.standardise(comp3, "magic")


# ----------------------------------------------------------------------------- index
def test_index_matches_hand_calculation(comp3):
    w = {"rent_burden_pct": 0.5, "rent_vs_income_pct": 0.25, "rent_rise_pct_income": 0.25, "price_growth_pct": 0.0}
    idx = ai.compute_index(comp3, w).set_index("county")
    # A: 0*.5 + 0*.25 + 100*.25 = 25 ; B: 50*.5 + 50*.25 + 50*.25 = 50 ; C: 100*.5 + 100*.25 + 0 = 75
    assert idx.loc["A", "index"] == pytest.approx(25)
    assert idx.loc["B", "index"] == pytest.approx(50)
    assert idx.loc["C", "index"] == pytest.approx(75)
    assert idx["rank"].to_dict() == {"C": 1, "B": 2, "A": 3}                      # 1 = least affordable


def test_contributions_add_up_to_index(comp8):
    idx = ai.compute_index(comp8)
    total = sum(idx[f"contrib_{c}"] for c in ai.COLUMNS)
    assert np.allclose(total, idx["index"])


def test_weights_are_scale_invariant(comp8):
    a = ai.compute_index(comp8, {"rent_burden_pct": 1, "rent_vs_income_pct": 1, "rent_rise_pct_income": 1, "price_growth_pct": 1})
    b = ai.compute_index(comp8, {"rent_burden_pct": 7, "rent_vs_income_pct": 7, "rent_rise_pct_income": 7, "price_growth_pct": 7})
    assert np.allclose(a.set_index("county")["index"], b.set_index("county")["index"])


def test_index_is_monotonic_in_each_component(comp8):
    base = ai.compute_index(comp8).set_index("county")["index"]
    for c in ai.COLUMNS:
        worse = comp8.copy()
        worse.loc[worse["county"] == "C", c] = worse[c].max() + 10        # new extreme value for one county
        new = ai.compute_index(worse).set_index("county")["index"]
        assert new["C"] >= base["C"] - 1e-9, c


def test_tiers_split_into_quartiles(comp8):
    idx = ai.compute_index(comp8)
    assert idx["tier"].value_counts().to_dict() == {t: 2 for t in ai.TIERS}
    assert set(idx.loc[idx["rank"] <= 2, "tier"]) == {"Highest pressure"}


# ----------------------------------------------------------------------------- price input
def _price_table(regions, base="2019-12-01", latest="2020-12-01", values=None):
    rows = []
    for g in regions:
        for period, v in zip((base, latest), values or (100.0, 110.0)):
            rows.append({"geography": g, "dwelling_type": "houses", "period": pd.Timestamp(period), "rppi_index": v})
    return pd.DataFrame(rows)


def test_regional_price_growth_maps_region_aliases():
    t = {"property_price_index": _price_table(["Midland", "Dublin"], values=(100.0, 125.0)),
         "dim_county": pd.DataFrame({"county": ["Offaly", "Dublin"], "nuts3_region": ["Midlands", "Dublin"]})}
    out = ai.regional_price_growth(t).set_index("county")
    assert out.loc["Offaly", "price_region"] == "Midland"          # CSO spells it 'Midland', the dimension table 'Midlands'
    assert out.loc["Offaly", "price_growth_pct"] == pytest.approx(25.0)
    assert out.loc["Dublin", "price_growth_pct"] == pytest.approx(25.0)


def test_regional_price_growth_uses_latest_month_and_fails_loudly_on_gaps():
    t = {"property_price_index": _price_table(["Border"], values=(100.0, 90.0)),
         "dim_county": pd.DataFrame({"county": ["Cavan"], "nuts3_region": ["Border"]})}
    assert ai.regional_price_growth(t)["price_growth_pct"].iloc[0] == pytest.approx(-10.0)
    t["dim_county"] = pd.DataFrame({"county": ["Kerry"], "nuts3_region": ["South-West"]})
    with pytest.raises(ValueError, match="South-West"):
        ai.regional_price_growth(t)


# ----------------------------------------------------------------------------- sensitivity
def test_scenarios_leave_one_out_and_methods_have_expected_shape(comp8):
    scen = ai.scenario_ranks(comp8)
    assert list(scen.columns) == list(ai.WEIGHT_SCENARIOS)
    assert scen["Baseline"].to_dict() == ai.compute_index(comp8).set_index("county")["rank"].to_dict()
    loo = ai.leave_one_out_ranks(comp8)
    assert loo.shape == (8, len(ai.COLUMNS))
    assert list(ai.method_ranks(comp8).columns) == ["minmax", "zscore", "rank"]
    assert ai.rank_agreement(scen, "Baseline").between(-1, 1).all()


def test_leave_one_out_equals_index_with_that_weight_set_to_zero(comp8):
    w = dict(ai.DEFAULT_WEIGHTS)
    w["price_growth_pct"] = 0.0
    expected = ai.compute_index(comp8, w).set_index("county")["rank"]
    got = ai.leave_one_out_ranks(comp8)["without price_growth_pct"]
    assert got.to_dict() == expected.to_dict()


def test_monte_carlo_is_reproducible_and_internally_consistent(comp8):
    a = ai.monte_carlo_ranks(comp8, n=500, seed=1)
    b = ai.monte_carlo_ranks(comp8, n=500, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert (a["rank_p05"] <= a["median_rank"]).all() and (a["median_rank"] <= a["rank_p95"]).all()
    assert a["rank_p05"].min() >= 1 and a["rank_p95"].max() <= 8
    assert a["pct_draws_top_5"].sum() == pytest.approx(500.0 * 5 / 5)          # each draw has exactly 5 counties in its top 5 -> 100% x 5
    assert not a.equals(ai.monte_carlo_ranks(comp8, n=500, seed=2))


def test_monte_carlo_collapses_to_baseline_when_weights_are_pinned(comp8):
    pinned = ai.monte_carlo_ranks(comp8, n=200, concentration=1e7)
    assert (pinned["rank_p05"] == pinned["baseline_rank"]).all()
    assert (pinned["rank_p95"] == pinned["baseline_rank"]).all()
    flat = ai.monte_carlo_ranks(comp8, n=2000)
    assert flat["rank_range_width"].sum() > pinned["rank_range_width"].sum()


# ----------------------------------------------------------------------------- real processed data
def test_components_reconcile_with_source_tables(tables):
    comp = ai.build_components(tables).set_index("county")
    assert len(comp) == 26 and not comp[ai.COLUMNS].isna().any().any()
    # re-derive Dublin's rent-rise component directly from the processed rent and income tables
    r = tables["rents_rtb"]
    r = r[(r["county"] == "Dublin") & (r["geography_type"] == "county") & (r["bedrooms"] == "All bedrooms") & (r["property_type"] == "All property types")]
    ly, lq = int(r["year"].max()), int(r.loc[r["year"] == r["year"].max(), "quarter"].max())
    latest = r[(r["year"] == ly) & (r["quarter"] == lq)]["avg_monthly_rent"].iloc[0]
    base = r[(r["year"] == 2019) & (r["quarter"] == 4)]["avg_monthly_rent"].iloc[0]
    inc = tables["household_income_county"]
    inc = inc[(inc["county"] == "Dublin") & (inc["year"] == inc["year"].max())]["disposable_income_per_person"].iloc[0]
    assert comp.loc["Dublin", "rent_rise_pct_income"] == pytest.approx(100 * 12 * (latest - base) / inc)
    assert comp.loc["Dublin", "rent_vs_income_pct"] == pytest.approx(100 * 12 * latest / inc)
    # price component = change in the CSO regional house index for Dublin between Dec 2019 and the latest month
    p = tables["property_price_index"]
    s = p[(p["geography"] == "Dublin") & (p["dwelling_type"] == "houses")].set_index("period")["rppi_index"]
    assert comp.loc["Dublin", "price_growth_pct"] == pytest.approx(100 * (s.iloc[-1] / s[pd.Timestamp("2019-12-01")] - 1))
    # burden component equals the stock-weighted TRS38 county value used elsewhere in the dashboard
    burden = calc.rent_to_income_county(tables).set_index("county")["median_rent_pct_income"]
    assert comp["rent_burden_pct"].to_dict() == pytest.approx(burden.reindex(comp.index).to_dict())


def test_every_county_gets_a_price_region_with_data(tables):
    out = ai.regional_price_growth(tables)
    assert len(out) == 26 and out["price_growth_pct"].notna().all()
    assert set(out["price_region"]) <= set(tables["property_price_index"]["geography"])


def test_ranked_table_is_complete_and_consistent(tables):
    r = ai.ranked_table(tables)
    assert len(r) == 26 and sorted(r["rank"]) == list(range(1, 27))
    assert r["index"].is_monotonic_decreasing
    assert r["index"].between(0, 100).all()
    assert r["tier"].isin(ai.TIERS).all()
    assert set(["rent_latest", "rent_growth_pct", "price_region"]) <= set(r.columns)
    assert "Dublin" in r["county"].head(10).tolist()          # sanity: the Dublin region is among the most pressured on rent-vs-income


def test_published_rent_burden_ordering_is_respected_when_only_burden_is_weighted(tables):
    comp = ai.build_components(tables)
    only = ai.compute_index(comp, {"rent_burden_pct": 1.0}).set_index("county")["rank"]
    burden_rank = comp.set_index("county")["rent_burden_pct"].rank(ascending=False, method="min").astype(int)
    assert only.to_dict() == burden_rank.to_dict()


def test_stability_summary_reports_sensible_values(tables):
    s = ai.stability_summary(tables)
    assert -1 <= s["min_spearman_scenarios"] <= 1
    assert s["min_spearman_methods"] > 0.8                       # method choice matters much less than weights
    assert len(s["top5_baseline"]) == 5
    assert s["median_rank_interval_width_local"] < s["median_rank_interval_width_flat"]


# ----------------------------------------------------------------------------- registry
def test_index_is_documented_in_the_indicator_registry():
    for key in ("affordability_pressure_index", "affordability_index_sensitivity"):
        ind = INDICATORS[key]
        assert ind.kind in ("derived", "estimate")
        assert "weight" in (ind.calculation + ind.assumptions).lower()
        assert ind.limitations
