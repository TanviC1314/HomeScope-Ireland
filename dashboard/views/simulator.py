"""Page 7 - Policy Scenario Simulator (HYPOTHETICAL)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.analysis import scenarios as sc  # noqa: E402

T.page_header("Policy Scenario Simulator",
              "Explore what could happen to housing supply indicators under hypothetical policy choices. This is a thinking tool, not a forecast.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
T.note(f"{sc.LABEL}. Results show simple arithmetic on the latest actual figures and your assumptions. They are not predictions and ignore most real-world constraints.", "hypo")

# ------------------------------------------------------------------------------ inputs
left, right = st.columns([2, 3])
with left:
    st.subheader("Your scenario")
    area = st.selectbox("Area", ["Ireland"] + D.county_list(), key="sim_area")
    base = sc.build_baseline(tables, None if area == "Ireland" else area)
    horizon = st.slider("Years simulated", 3, 10, 5, key="sim_horizon")
    preset = st.radio("Increase annual completions by", ["0%", "5%", "10%", "15%", "Custom"], horizontal=True, key="sim_preset")
    uplift = float(preset.strip("%")) if preset != "Custom" else st.slider("Custom increase (%)", -20, 40, 10, key="sim_custom")
    phase = st.slider("Years to phase in the increase", 1, 5, 1, key="sim_phase",
                      help="1 = the full increase applies from the first year; higher values ramp up linearly.")
    st.markdown("**Bring vacant homes back into use**")
    pool_note = f"{base.long_term_vacant:,.0f} dwellings in {area} have been vacant for six years running (VAC23, Q4 2024)."
    st.caption(pool_note)
    suitable = st.slider("Share of long-term vacant homes you assume are suitable (%)", 0, 50, 10, key="sim_suitable",
                         help="An assumption, not a statistic: it caps how many homes the simulator allows to be renovated.")
    pool = base.long_term_vacant * suitable / 100
    target = st.slider("Vacant homes to renovate over the period", 0, int(max(base.long_term_vacant, 100)), 0, step=max(1, int(base.long_term_vacant // 100) or 1), key="sim_target")
    st.markdown("**Affordable housing delivery**")
    aff_base = st.slider("Assumed affordable share of completions today (%)", 0, 50, 10, key="sim_aff_b", help="Illustrative input: no official series is used.")
    aff_scen = st.slider("Affordable share of completions in the scenario (%)", 0, 50, 10, key="sim_aff_s",
                         help="Defaults to the same share as today, so the starting scenario shows no change. Raise it to explore higher affordable delivery.")

custom = sc.ScenarioInputs(name="Your scenario", completions_uplift_pct=uplift, horizon_years=horizon, phase_in_years=phase,
                           vacant_homes_target=target, suitable_share_pct=suitable, affordable_share_baseline_pct=aff_base, affordable_share_scenario_pct=aff_scen)
res = sc.summarise(base, custom)
df = sc.simulate(base, custom)

with right:
    st.subheader(f"Results for {area} (hypothetical)")
    m = st.columns(3)
    m[0].metric("Extra homes (completions)", f"{res['cumulative_extra_completions']:,.0f}")
    m[1].metric("Vacant homes renovated", f"{res['renovated_vacant_homes']:,.0f}")
    m[2].metric("Total extra supply", f"{res['cumulative_extra_supply']:,.0f}")
    m = st.columns(3)
    m[0].metric("Stock growth over period", f"{res['scenario_stock_growth_pct']:.2f}%", f"{res['stock_growth_difference_pp']:+.2f} pp vs baseline")
    m[1].metric("Completions per 1,000 (final yr)", f"{res['scenario_completions_per_1000_final_year']:.2f}",
                f"{res['scenario_completions_per_1000_final_year'] - res['baseline_completions_per_1000']:+.2f} vs baseline")
    m[2].metric("Extra affordable homes", f"{res['cumulative_extra_affordable']:,.0f}")
    if res["renovation_capped_by_suitable_pool"]:
        T.note(f"You asked to renovate {res['vacant_homes_requested']:,.0f} homes but only {res['suitable_vacant_pool']:,.0f} are assumed suitable "
               f"({suitable}% of the long-term vacant stock), so the simulator capped renovations at that number.", "warn")
    if res["years_of_household_growth_covered"] == res["years_of_household_growth_covered"]:
        st.caption(f"Proxy: the extra supply equals about {res['years_of_household_growth_covered']:.1f} years of average household growth ({base.annual_household_growth:,.0f} a year "
                   f"between Census 2016 and 2022). Baseline completions are {res['baseline_completions_to_household_growth']:.1f}x that figure.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["year"], y=df["baseline_stock_growth_pct"], name="Baseline (completions held at latest year)", mode="lines+markers",
                             line=dict(color=T.CATEGORICAL[0], width=2), marker=dict(size=8, line=dict(color=T.SURFACE, width=2))))
    fig.add_trace(go.Scatter(x=df["year"], y=df["scenario_stock_growth_pct"], name="Your scenario (hypothetical)", mode="lines+markers",
                             line=dict(color=T.CATEGORICAL[1], width=2, dash="dash"), marker=dict(size=8, line=dict(color=T.SURFACE, width=2))))
    ch.style(fig, f"Cumulative growth in dwelling stock since {base.base_year}, {area} (hypothetical)", 330, ytitle="% growth in stock", yfmt=".1f")
    fig.update_xaxes(dtick=1)
    ch.show(fig, "sim_chart")

# ------------------------------------------------------------------------------ comparison
st.subheader("Compare supply scenarios")
scen = sc.standard_scenarios(horizon) + [custom]
comp = sc.compare(base, scen)
table = comp[["scenario", "cumulative_extra_supply", "stock_growth_difference_pp", "scenario_completions_per_1000_final_year",
              "cumulative_extra_affordable", "years_of_household_growth_covered"]].copy()
table.columns = ["Scenario", "Extra homes over period", "Stock growth vs baseline (pp)", "Completions per 1,000 (final year)", "Extra affordable homes",
                 "Years of household growth covered (proxy)"]
ch.show_df(table.round(2))

c1, c2 = st.columns(2)
with c1:
    fig = ch.bars(comp.assign(x=comp["scenario"]), "x", "cumulative_extra_supply", "Extra homes over the period vs baseline (hypothetical)", ytitle="Dwellings",
                  single_color=T.CATEGORICAL[2])
    ch.show(fig, "sim_compare_bar")
with c2:
    annual = pd.concat([sc.simulate(base, s).assign(scenario=s.name)[["year", "scenario", "scenario_completions"]] for s in scen[:4]])
    cm = {s.name: T.CATEGORICAL[i] for i, s in enumerate(scen[:4])}
    ch.show(ch.line(annual, "year", "scenario_completions", "scenario", "Annual completions under each scenario (hypothetical)", color_map=cm, ytitle="Dwellings",
                    hover_fmt=",.0f"), "sim_compare_line")

with st.expander("Assumptions and limitations (please read)", expanded=False):
    st.markdown(f"**Baseline for {area}** - from actual data: {base.completions:,.0f} completions in {base.base_year}; starting dwelling stock {base.stock_start:,.0f}; "
                f"population {base.population:,.0f}; long-term vacant dwellings {base.long_term_vacant:,.0f}.")
    for a in sc.ASSUMPTIONS:
        st.markdown(f"- {a}")
    st.markdown("- **This simulator is not an official model and its outputs must not be quoted as forecasts.**")
