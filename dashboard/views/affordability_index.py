"""Page - Housing Affordability Pressure Index (county ranking with adjustable weights and sensitivity analysis)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import affordability_index as ai  # noqa: E402
from src.indicators import calculations as calc  # noqa: E402

T.page_header("Affordability Index",
              "A transparent county ranking that combines rent burden, rent level, rent rises and property-price growth. "
              "Change the weights to see how much the ranking depends on them.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
counties = D.county_list()


@st.cache_data(show_spinner=False)
def _components() -> pd.DataFrame:
    return ai.build_components(D.get_tables()[0])


@st.cache_data(show_spinner="Running sensitivity analysis...")
def _sensitivity() -> dict:
    comp = _components()
    return {"scenarios": ai.scenario_ranks(comp), "loo": ai.leave_one_out_ranks(comp), "methods": ai.method_ranks(comp),
            "mc_local": ai.monte_carlo_ranks(comp, concentration=50), "mc_flat": ai.monte_carlo_ranks(comp),
            "summary": ai.stability_summary(D.get_tables()[0])}


comp = _components()
ly, lq = calc.latest_rent_period(tables)
T.note("<b>How to read this.</b> The index is a <b>relative</b> 0-100 score: 0 = the county with the lowest pressure on each component, "
       "100 = the highest. A high score means <i>less affordable than other counties</i>, not that housing is unaffordable by an absolute standard. "
       "It is not a forecast, and the weights are a documented judgement (adjustable below).")

# ------------------------------------------------------------------------------ method + weights
with st.expander("Formula, components and default weights", expanded=False):
    rows = [{"Component": c.label, "Default weight": f"{ai.DEFAULT_WEIGHTS[c.column]:.0%}", "Lens": c.lens, "Source": c.source} for c in ai.COMPONENTS]
    ch.show_df(pd.DataFrame(rows))
    st.markdown(
        "**Step 1** compute the four component values per county. **Step 2** standardise each across the 26 counties "
        "(min-max: 0 = lowest, 100 = highest). **Step 3** index = sum of (weight x standardised score), weights scaled to sum to 100%.  \n"
        "Prices: the CSO publishes no county property prices (only a regional index, 2015 = 100), so the price component is "
        "*regional house-price growth since Dec 2019*, shared by all counties in a region. "
        f"Rent period: Q{lq} {ly}; base for rent and price changes: Q4 2019.")

st.subheader("Weights")
w1, w2, w3, w4, w5 = st.columns([1, 1, 1, 1, 1.3])
labels = {"rent_burden_pct": "Rent burden (tenants)", "rent_vs_income_pct": "Rent vs income per person",
          "rent_rise_pct_income": "Rent rise vs income", "price_growth_pct": "Regional price growth"}
raw_w = {}
for col, widget in zip(labels, (w1, w2, w3, w4)):
    with widget:
        raw_w[col] = st.slider(labels[col], 0, 100, int(round(ai.DEFAULT_WEIGHTS[col] * 100)), 5, key=f"ai_w_{col}")
with w5:
    method = st.selectbox("Standardisation", ["minmax", "zscore", "rank"], index=0, key="ai_method",
                          format_func={"minmax": "Min-max (0-100)", "zscore": "Z-score", "rank": "Percentile rank"}.get)
if sum(raw_w.values()) == 0:
    T.note("All weights are zero - showing the default weights instead.", "warn")
    raw_w = dict(ai.DEFAULT_WEIGHTS)
weights = ai.validate_weights(raw_w)
st.caption("Weights are rescaled to sum to 100%: " + " | ".join(f"{labels[c]} {weights[c]:.0%}" for c in labels))

idx = ai.compute_index(comp, weights, method)
table = idx.merge(comp[["county", *ai.COLUMNS, "rent_latest", "rent_growth_pct", "price_region"]], on="county")
unit = "z-score units" if method == "zscore" else "0-100"

# ------------------------------------------------------------------------------ headline
selected = st.multiselect("Counties to highlight", counties, default=["Dublin", "Cork", "Galway", "Limerick", "Waterford"], max_selections=8, key="ai_sel")
k1, k2, k3 = st.columns(3)
top, bottom = table.iloc[0], table.iloc[-1]
with k1:
    T.kpi_card("Highest pressure", f"{top['county']}", f"index {top['index']:.1f} ({unit})", "Rank 1 of 26", "derived")
with k2:
    T.kpi_card("Lowest pressure", f"{bottom['county']}", f"index {bottom['index']:.1f} ({unit})", "Rank 26 of 26", "derived")
with k3:
    sel_rank = ", ".join(f"{c} #{int(table.loc[table['county'] == c, 'rank'].iloc[0])}" for c in selected[:4]) or "n/a"
    T.kpi_card("Selected counties", sel_rank, "1 = least affordable", "Current weights", "derived")

# ------------------------------------------------------------------------------ map + ranking
m1, m2 = st.columns([5, 4])
with m1:
    fig = ch.county_map(table, D.counties_geojson(), "index", f"Affordability pressure ({unit})", highlight=selected, fmt=",.1f")
    ch.show(fig, "ai_map")
    T.caption("Darker = higher pressure (less affordable relative to other counties). Boundaries: Tailte Eireann (OSi), CC BY 4.0.")
with m2:
    ch.show(ch.hbar_ranked(table, "county", "index", f"Affordability pressure index ({unit})", highlight=selected, height=560, value_fmt=",.1f"), "ai_rank")
    T.caption("Ranked from most to least pressured. Highlighted counties in blue.")

# ------------------------------------------------------------------------------ contributions
st.subheader("What drives each county's score")
ordered = table.sort_values("index", ascending=True)
fig = go.Figure()
for i, c in enumerate(ai.COMPONENTS):
    fig.add_trace(go.Bar(y=ordered["county"], x=ordered[f"contrib_{c.column}"], name=labels[c.column], orientation="h",
                         marker=dict(color=T.CATEGORICAL[i]), hovertemplate="%{y}<br>" + labels[c.column] + ": %{x:.1f}<extra></extra>"))
fig.update_layout(barmode="stack")
fig = ch.style(fig, "Contribution of each component to the index (weight x standardised score)", 640, legend=True, hover="closest")
fig.update_yaxes(showgrid=False, tickfont=dict(size=11))
ch.show(fig, "ai_contrib")
T.caption("Stacked contributions add up to the index. Counties in the same NUTS3 region share the price component (no county price series exists).")

# ------------------------------------------------------------------------------ ranked table
st.subheader("Ranked county table")
sens = _sensitivity()
mc = sens["mc_local"].set_index("county")
show = table[["rank", "county", "index", "tier", "rent_burden_pct", "rent_vs_income_pct", "rent_rise_pct_income", "price_growth_pct", "price_region", "rent_latest"]].copy()
show["Rank range, weights near baseline (5th-95th pct)"] = [
    f"{int(mc.loc[c, 'rank_p05'])}-{int(mc.loc[c, 'rank_p95'])}" for c in show["county"]]
show = show.round(1)
show.columns = ["Rank (1 = least affordable)", "County", "Index", "Tier", "Rent burden (% of tenant income, 2024)", "Annual rent % of income per person",
                "Rent rise since Q4 2019, % of income", "Regional house-price growth since Dec 2019 (%)", "Price region", f"Average rent Q{lq} {ly} (EUR/month)",
                "Rank range, weights near baseline (5th-95th pct)"]
ch.show_df(show)
st.download_button("Download ranked table (CSV)", show.to_csv(index=False).encode("utf-8"), "homescope_affordability_index.csv", "text/csv", key="ai_dl")
T.caption("The last column is the 5th-95th percentile of the county's rank over 5,000 random weight sets drawn around the default weights (see sensitivity). "
          "It is the rank range under baseline weights only; it does not depend on the sliders above.")

# ------------------------------------------------------------------------------ sensitivity
st.subheader("Sensitivity: how much do the rankings depend on the weights?")
s = sens["summary"]
T.note(f"<b>Headline.</b> With baseline weights the most pressured counties are {', '.join(s['top5_baseline'])}. "
       f"Across six named weighting scenarios the rank correlation with the baseline is between {s['min_spearman_scenarios']:.2f} and 1.00, "
       f"so the <i>order</i> changes substantially when weights shift towards price growth or rent rises. "
       f"{', '.join(s['top5_in_every_scenario']) or 'No county'} stay in the top 8 in every scenario. "
       f"Changing the standardisation method matters little (minimum rank correlation {s['min_spearman_methods']:.2f}). "
       f"Treat the ranking as indicative: neighbouring ranks are not meaningfully different.")

t1, t2 = st.tabs(["Rank range (random weights)", "Scenarios and drop-one-component"])
with t1:
    which = st.radio("Weights drawn", ["Around the baseline weights", "Any weights (flat)"], horizontal=True, key="ai_mc")
    d = (sens["mc_local"] if which.startswith("Around") else sens["mc_flat"]).sort_values("baseline_rank", ascending=False)
    fig = go.Figure(go.Scatter(
        x=d["median_rank"], y=d["county"], mode="markers", marker=dict(size=8, color=T.CATEGORICAL[0]),
        error_x=dict(type="data", symmetric=False, array=d["rank_p95"] - d["median_rank"], arrayminus=d["median_rank"] - d["rank_p05"],
                     color="#9bb7dd", thickness=3, width=0),
        customdata=d[["baseline_rank", "rank_p05", "rank_p95", "pct_draws_top_5"]],
        hovertemplate="<b>%{y}</b><br>median rank %{x:.0f}; range %{customdata[1]:.0f}-%{customdata[2]:.0f}<br>baseline rank %{customdata[0]:.0f}"
                      "<br>in top 5 in %{customdata[3]:.0f}% of draws<extra></extra>"))
    fig = ch.style(fig, "Rank range under 5,000 random weight sets (dot = median, bar = 5th-95th percentile; 1 = least affordable)", 640,
                   legend=False, hover="closest")
    fig.update_xaxes(range=[0.5, 26.5], dtick=1, showgrid=True, gridcolor=T.GRID, title="Rank")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11))
    ch.show(fig, "ai_mc_chart")
    T.caption("Wide bars = the county's position depends strongly on how components are weighted. Weights are drawn uniformly (flat) or "
              "clustered around the baseline (concentration 50); fixed seed, reproducible.")
with t2:
    scen = sens["scenarios"].copy()
    scen = scen.sort_values("Baseline")
    st.markdown("**Rank under named weighting scenarios** (1 = least affordable)")
    ch.show_df(scen.reset_index().rename(columns={"county": "County"}))
    agree = ai.rank_agreement(sens["scenarios"], "Baseline").rename("Spearman rank correlation with baseline").round(2).reset_index().rename(columns={"index": "Scenario"})
    ch.show_df(agree)
    st.markdown("**Rank when one component is dropped** (remaining weights rescaled)")
    loo = sens["loo"].copy()
    loo.columns = [f"Without {labels[c.replace('without ', '')]}" for c in loo.columns]
    ch.show_df(loo.loc[scen.index].reset_index().rename(columns={"county": "County"}))
    st.markdown("**Rank under different standardisation methods** (same weights)")
    ch.show_df(sens["methods"].loc[scen.index].reset_index().rename(columns={"county": "County", "minmax": "Min-max", "zscore": "Z-score", "rank": "Percentile rank"}))

# ------------------------------------------------------------------------------ limits
T.note("<b>Limitations.</b> (1) Relative ranking only; no absolute affordability threshold. (2) The CSO publishes no county property prices, so prices enter as "
       "regional house-price growth - counties in a region share a value, and growth says nothing about price levels. (3) Per-person income understates household "
       "income and overstates the rent share; the tenant-based burden (TRS38) is the best measured component and has the largest default weight. "
       "(4) Weights are a judgement, not estimated from data; the sensitivity section shows how much they matter. (5) No mortgage-affordability data "
       "(Central Bank) is included. See <i>docs/AFFORDABILITY_INDEX.md</i> for the full method.", "warn")
