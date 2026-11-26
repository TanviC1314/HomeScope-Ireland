"""Dashboard tests: every page renders, headline numbers equal the indicator calculations, and filters work.

Uses Streamlit's headless AppTest runner against the processed CSV backend (deterministic, no database needed).
"""
from __future__ import annotations

import re

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.indicators import calc  # noqa: E402
from src.utils.paths import ROOT  # noqa: E402

VIEWS = ["national_overview", "county_comparison", "affordability", "affordability_index", "supply", "demand_gap", "vacancy_needs", "insights", "simulator", "methodology"]


@pytest.fixture(autouse=True)
def csv_backend(monkeypatch):
    monkeypatch.setenv("HOMESCOPE_DATA_BACKEND", "csv")


def run(view: str, timeout: int = 180) -> AppTest:
    return AppTest.from_file(str(ROOT / "dashboard" / "views" / f"{view}.py"), default_timeout=timeout).run()


def text(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


@pytest.mark.parametrize("view", VIEWS)
def test_every_page_renders_without_errors(tables, view):
    at = run(view)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error
    assert "HomeScope Ireland" in text(at)


def test_app_entrypoint_defines_all_pages_and_branding():
    src = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    for view in VIEWS:
        assert f"views/{view}.py" in src
    assert "Housing Crisis Intelligence Platform" in src


# ----------------------------------------------------------------------------- KPIs vs calculations
def test_overview_kpis_match_indicator_calculations(tables):
    at = run("national_overview")
    cards = re.sub(r"<[^>]+>", " ", " ".join(m.value for m in at.markdown if "hs-card" in m.value))
    k = calc.national_kpis(tables)
    assert f"{k['completions_latest_full_year']:,}" in cards
    assert f"{k['homeless_persons']:,}" in cards
    assert f"{k['vacant_dwellings']:,}" in cards
    assert f"{k['rent_proxy']:,.0f}" in cards
    assert f"{k['price_index']:.1f}" in cards


def test_overview_year_filter_and_partial_toggle_are_wired(tables):
    at = run("national_overview")
    assert at.slider(key="nat_years").value == (2012, 2026)
    at.slider(key="nat_years").set_value((2018, 2024)).run()
    assert not at.exception
    assert at.slider(key="nat_years").value == (2018, 2024)
    at.checkbox(key="nat_partial").set_value(False).run()
    assert not at.exception


# ----------------------------------------------------------------------------- filters
def test_county_comparison_filters_change_output(tables):
    at = run("county_comparison")
    assert at.multiselect(key="cc_counties").value == ["Dublin", "Cork", "Galway", "Limerick", "Waterford"]
    before = [df.value for df in at.dataframe]
    at.multiselect(key="cc_counties").set_value(["Kerry", "Mayo"]).run()
    assert not at.exception
    side_by_side = at.dataframe[0].value
    assert {"Kerry", "Mayo"} <= set(side_by_side.columns) and "Dublin" not in side_by_side.columns
    at.selectbox(key="cc_indicator").select("Vacancy rate (estimated)").run()
    assert not at.exception
    assert before[0].shape != side_by_side.shape or list(before[0].columns) != list(side_by_side.columns)


def test_county_comparison_values_match_scorecard(tables):
    at = run("county_comparison")
    table = at.dataframe[0].value.set_index("Indicator")
    rc = calc.rent_change(tables).set_index("county")
    assert table.loc["Average monthly rent", "Dublin"] == f"EUR {rc.loc['Dublin', 'rent_latest']:,.0f}"
    cg = calc.census_growth(tables).set_index("county")
    assert table.loc["Population growth 2016-2022", "Galway"] == f"{cg.loc['Galway', 'population_growth_pct']:.1f}%"


def test_affordability_filters(tables):
    at = run("affordability")
    at.selectbox(key="af_bed").select("Two bed").run()
    assert not at.exception
    at.selectbox(key="af_ptype").select("Apartment").run()
    assert not at.exception
    at.multiselect(key="af_counties").set_value(["Cork"]).run()
    assert not at.exception


def test_supply_filters_and_lag(tables):
    at = run("supply")
    at.slider(key="su_lag").set_value(2).run()
    assert not at.exception and at.slider(key="su_lag").value == 2
    at.multiselect(key="su_types").set_value(["Apartment"]).run()
    assert not at.exception
    at.slider(key="su_years").set_value((2016, 2024)).run()
    assert not at.exception


def test_vacancy_page_always_warns_vacant_is_not_available(tables):
    at = run("vacancy_needs")
    assert "Vacant does not mean available" in text(at)
    at.selectbox(key="vn_year").select(2022).run()
    assert not at.exception


def test_insights_filters_reduce_results(tables):
    at = run("insights")
    total = int(re.search(r"\*\*(\d+) of (\d+) insights", text(at)).group(2))
    assert total >= 12
    at.multiselect(key="in_theme").set_value(["Vacancy"]).run()
    shown = int(re.search(r"\*\*(\d+) of", text(at)).group(1))
    assert 0 < shown < total
    at.multiselect(key="in_theme").set_value([]).run()
    at.selectbox(key="in_county").select("Dublin").run()
    assert not at.exception
    shown_dublin = int(re.search(r"\*\*(\d+) of", text(at)).group(1))
    assert 0 < shown_dublin < total
    for label in ("Where / when", "Why it matters", "Possible intervention"):
        assert label in text(at)


# ----------------------------------------------------------------------------- simulator
def test_simulator_is_labelled_hypothetical_and_responds(tables):
    at = run("simulator")
    assert "HYPOTHETICAL SIMULATION" in text(at)
    base = [m.value for m in at.metric]
    assert base[2] == "0"                                  # no change by default -> no extra supply
    at.radio(key="sim_preset").set_value("10%").run()
    assert not at.exception
    after = {m.label: m.value for m in at.metric}
    assert after["Total extra supply"] != "0"
    assert at.exception == []
    k = calc.national_kpis(tables)["completions_latest_full_year"]
    expected = round(k * 0.10 * 5)
    assert after["Extra homes (completions)"] == f"{expected:,}"


def test_simulator_caps_renovation_and_warns(tables):
    at = run("simulator")
    at.slider(key="sim_suitable").set_value(1).run()
    at.slider(key="sim_target").set_value(20000).run()
    assert not at.exception
    assert "capped renovations" in text(at)


def test_simulator_county_baseline(tables):
    at = run("simulator")
    at.selectbox(key="sim_area").select("Limerick").run()
    assert not at.exception
    assert "Results for Limerick" in text(at) or any("Limerick" in s.value for s in at.subheader)


def test_methodology_lists_sources_indicators_and_limitations(tables):
    at = run("methodology")
    assert not at.exception
    assert len(at.tabs) == 4
    body = text(at)
    assert "Vacant is not available" in body and "not a forecast" in body.lower() or "hypothetical" in body.lower()


# ----------------------------------------------------------------------------- affordability index page
def test_affordability_index_page_shows_ranking_and_matches_calculation(tables):
    from src.indicators import affordability_index as ai

    at = run("affordability_index")
    assert not at.exception, [e.value for e in at.exception]
    expected = ai.ranked_table(tables)
    body = text(at)
    assert expected.iloc[0]["county"] in body                      # highest-pressure county named in the headline cards
    assert "relative" in body.lower() and "not a forecast" in body.lower()
    assert len(at.slider) == 4                                      # one weight slider per component
    assert "Sensitivity" in " ".join(h.value for h in at.subheader)


def test_affordability_index_weights_change_the_ranking(tables):
    from src.indicators import affordability_index as ai

    at = run("affordability_index")
    # put all weight on regional price growth: the highest-pressure county must change to the top price-growth county
    for sl in at.slider:
        sl.set_value(100 if "price" in sl.label.lower() else 0)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    comp = ai.build_components(tables)
    top_price = comp.loc[comp["price_growth_pct"] == comp["price_growth_pct"].max(), "county"]   # regional ties: all counties of that region
    assert any(c in text(at) for c in top_price)


def test_affordability_index_all_zero_weights_fall_back_to_defaults(tables):
    at = run("affordability_index")
    for sl in at.slider:
        sl.set_value(0)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("All weights are zero" in m.value for m in at.markdown)


# ----------------------------------------------------------------------------- demand-gap page
def test_demand_gap_page_shows_kpis_and_scenario_note(tables):
    from src.indicators import demand_gap as dg

    at = run("demand_gap")
    assert not at.exception, [e.value for e in at.exception]
    body = text(at)
    kpis = dg.gap_kpis(tables)
    # Latest-year gap is shown in the KPI strip
    assert f"{kpis['latest_gap']:+,}" in body or str(abs(kpis["latest_gap"])) in body
    # Methodology note is on the page
    assert "not forecasts" in body.lower() or "not a forecast" in body.lower()
    assert "central" in body.lower() and "scenario" in body.lower()


def test_demand_gap_county_selectbox_works(tables):
    at = run("demand_gap")
    sel = at.selectbox(key="dg_county_year")
    avail = [opt for opt in sel.options]
    assert len(avail) >= 2
    sel.select(avail[-1]).run()
    assert not at.exception, [e.value for e in at.exception]
