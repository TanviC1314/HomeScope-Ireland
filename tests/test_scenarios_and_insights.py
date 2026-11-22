"""Policy scenario simulator (hypothetical arithmetic) and the automatic insight generator."""
from __future__ import annotations

import re

import pytest

from src.analysis import insights as ins
from src.analysis import scenarios as sc


@pytest.fixture()
def base():
    return sc.Baseline(area="Test", base_year=2025, completions=1000.0, stock_start=100_000.0, population=200_000.0,
                       long_term_vacant=2000.0, annual_household_growth=500.0)


# ----------------------------------------------------------------------------- scenario arithmetic
def test_no_change_scenario_has_no_effect(base):
    s = sc.summarise(base, sc.ScenarioInputs(horizon_years=5))
    assert s["cumulative_extra_supply"] == 0 and s["stock_growth_difference_pp"] == 0
    assert s["baseline_stock_growth_pct"] == pytest.approx(100 * 5000 / 100000)


@pytest.mark.parametrize("pct", [5, 10, 15])
def test_completions_uplift_is_exact(base, pct):
    s = sc.summarise(base, sc.ScenarioInputs(completions_uplift_pct=pct, horizon_years=5))
    assert s["cumulative_extra_completions"] == pytest.approx(1000 * pct / 100 * 5)
    assert s["stock_growth_difference_pp"] == pytest.approx(100 * (1000 * pct / 100 * 5) / 100000)
    assert s["scenario_completions_per_1000_final_year"] == pytest.approx(1000 * 1000 * (1 + pct / 100) / 200000)


def test_phase_in_is_linear(base):
    d = sc.simulate(base, sc.ScenarioInputs(completions_uplift_pct=10, horizon_years=4, phase_in_years=2))
    assert d["scenario_completions"].round(6).tolist() == [1050.0, 1100.0, 1100.0, 1100.0]


def test_renovation_is_capped_by_suitable_pool(base):
    s = sc.summarise(base, sc.ScenarioInputs(vacant_homes_target=1000, suitable_share_pct=10, horizon_years=5))
    assert s["suitable_vacant_pool"] == pytest.approx(200)          # 10% of 2,000 long-term vacant
    assert s["renovated_vacant_homes"] == pytest.approx(200)        # requested 1,000 but only 200 assumed suitable
    assert s["renovation_capped_by_suitable_pool"] is True
    ok = sc.summarise(base, sc.ScenarioInputs(vacant_homes_target=150, suitable_share_pct=10))
    assert ok["renovated_vacant_homes"] == 150 and ok["renovation_capped_by_suitable_pool"] is False


def test_zero_suitability_means_no_renovation(base):
    s = sc.summarise(base, sc.ScenarioInputs(vacant_homes_target=5000, suitable_share_pct=0))
    assert s["renovated_vacant_homes"] == 0


def test_affordable_delivery_is_share_of_completions(base):
    s = sc.summarise(base, sc.ScenarioInputs(completions_uplift_pct=10, horizon_years=5,
                                             affordable_share_baseline_pct=10, affordable_share_scenario_pct=20))
    scenario_aff = 1000 * 1.10 * 0.20 * 5
    baseline_aff = 1000 * 0.10 * 5
    assert s["cumulative_extra_affordable"] == pytest.approx(scenario_aff - baseline_aff)


def test_household_growth_coverage(base):
    s = sc.summarise(base, sc.ScenarioInputs(completions_uplift_pct=10, horizon_years=5))
    assert s["years_of_household_growth_covered"] == pytest.approx(500 / 500)      # 500 extra homes / 500 per year
    assert s["baseline_completions_to_household_growth"] == pytest.approx(2.0)


def test_negative_and_degenerate_inputs_do_not_break(base):
    d = sc.simulate(base, sc.ScenarioInputs(completions_uplift_pct=-10, horizon_years=0, vacant_homes_target=-5))
    assert len(d) == 1 and d["scenario_completions"].iloc[0] == pytest.approx(900)
    assert d.attrs["renovated_total"] == 0


def test_compare_returns_one_row_per_scenario(base):
    df = sc.compare(base, sc.standard_scenarios(5))
    assert len(df) == 4 and df["cumulative_extra_supply"].is_monotonic_increasing


def test_simulator_is_clearly_labelled_and_documents_assumptions():
    assert "HYPOTHETICAL" in sc.LABEL and "not a forecast" in sc.LABEL
    assert len(sc.ASSUMPTIONS) >= 6
    text = " ".join(sc.ASSUMPTIONS).lower()
    for phrase in ("constant", "suitab", "not simulated", "constraints"):
        assert phrase in text


def test_baseline_from_real_data_uses_actual_figures(tables):
    nat = sc.build_baseline(tables)
    assert nat.area == "Ireland" and nat.base_year == 2025
    assert nat.completions == tables["completions_quarterly"].query("year == 2025")["completions"].sum()
    county_total = sum(sc.build_baseline(tables, c).completions for c in tables["dim_county"]["county"])
    assert county_total == pytest.approx(nat.completions)
    assert sc.build_baseline(tables, "Limerick").long_term_vacant > 0


# ----------------------------------------------------------------------------- insights
def test_insights_are_complete_and_unique(tables):
    out = ins.generate_insights(tables)
    assert len(out) >= 12
    assert len({i.id for i in out}) == len(out)
    for i in out:
        for field in ("headline", "location", "period", "why_it_matters", "next_step", "sources"):
            assert getattr(i, field).strip(), (i.id, field)
        assert i.kind in ("published", "derived", "estimate")
        assert not re.search(r"\b(nan|none|inf|null)\b", i.headline.lower()), i.headline


def test_insight_numbers_trace_back_to_indicators(tables):
    from src.indicators import calc
    by_id = {i.id: i for i in ins.generate_insights(tables)}
    k = calc.national_kpis(tables)
    assert f"{k['completions_latest_full_year']:,}" in by_id["completions_trend"].headline
    assert f"{k['homeless_persons']:,}" in by_id["homelessness"].headline
    top_rent = calc.rent_change(tables).iloc[0]["county"]
    assert top_rent in by_id["rent_growth"].headline
    top_pressure = calc.housing_pressure_table(tables).iloc[0]["county"]
    assert top_pressure in by_id["pressure_flags"].headline


def test_vacancy_insights_never_claim_availability(tables):
    for i in ins.generate_insights(tables):
        if i.theme == "Vacancy":
            text = (i.headline + i.why_it_matters).lower()
            assert "not necessarily" in text or "do not" in text or "does not" in text or "not show" in text


def test_commencement_insight_warns_about_spikes(tables):
    i = {x.id: x for x in ins.generate_insights(tables)}["commencements"]
    assert "lumpy" in i.headline and "spike" in i.why_it_matters
