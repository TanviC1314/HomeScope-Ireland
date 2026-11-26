"""Page - Housing Supply-Demand Gap (Phase 2 Day 3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import demand_gap as dg  # noqa: E402

T.page_header("Housing Supply-Demand Gap",
              "Estimated annual household demand versus new dwelling completions, with low / central / high scenario bands "
              "based on observed migration. Positive gap = estimated shortfall.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)


@st.cache_data(show_spinner=False)
def _national_gap():
    return dg.national_gap(tables)


@st.cache_data(show_spinner=False)
def _county_gap():
    return dg.county_gap(tables)


@st.cache_data(show_spinner=False)
def _decomp():
    return dg.gap_decomposition(tables)


@st.cache_data(show_spinner=False)
def _kpis():
    return dg.gap_kpis(tables)


ng = _national_gap()
cg = _county_gap()
dec = _decomp()
kpis = _kpis()

T.note("<b>Methodology note.</b> Demand is estimated as (annual population change / average household size) + replacement "
       "demand (0.4% of housing stock). Scenario bands vary the net migration component: "
       "<b>high</b> = more people needing homes (less emigration or more immigration), "
       "<b>low</b> = fewer people needing homes. "
       "These are <b>analytical illustrations, not forecasts</b>. County values use CSO PEA08 annual estimates "
       "(rounded to the nearest hundred) and do not carry scenario bands.")

# ---------------------------------------------------------------------------- KPI strip
ly = kpis["latest_year"]
gap_c = kpis["latest_gap"]
cum = kpis["cumulative_gap_since_2017"]
avg_d = kpis["avg_annual_demand"]
avg_s = kpis["avg_annual_supply"]

k1, k2, k3, k4 = st.columns(4)
with k1:
    T.kpi_card(f"Gap {ly} (central)", f"{gap_c:+,}", delta="positive = shortfall", kind="estimate")
with k2:
    T.kpi_card("Cumulative gap 2017–", f"{cum:+,}", delta="full years, central scenario", kind="estimate")
with k3:
    T.kpi_card("Avg annual demand", f"{avg_d:,}" if avg_d else "–", delta="central scenario, full years", kind="estimate")
with k4:
    T.kpi_card("Avg annual completions", f"{avg_s:,}" if avg_s else "–", delta="full years", kind="published")

st.divider()

# ---------------------------------------------------------------------------- national gap chart
st.subheader("National supply-demand gap by year")

full_ng = ng[~ng["is_partial_year"]].copy()
partial_ng = ng[ng["is_partial_year"]].copy()

colors = T.CATEGORICAL
fig_gap = go.Figure()

# Scenario band (shaded area between high and low)
fig_gap.add_trace(go.Scatter(
    x=list(full_ng["year"]) + list(full_ng["year"])[::-1],
    y=list(full_ng["demand_high"]) + list(full_ng["demand_low"])[::-1],
    fill="toself", fillcolor=f"rgba({int(colors[0][1:3], 16)},{int(colors[0][3:5], 16)},{int(colors[0][5:7], 16)},0.12)",
    line=dict(color="rgba(0,0,0,0)"), name="Demand scenario band (low–high)", showlegend=True,
))
# Central demand line
fig_gap.add_trace(go.Scatter(
    x=full_ng["year"], y=full_ng["demand_central"], mode="lines+markers",
    line=dict(color=colors[0], width=2), marker=dict(size=5),
    name="Demand (central)", hovertemplate="Year %{x}<br>Demand: %{y:,}<extra></extra>",
))
# Completions line
fig_gap.add_trace(go.Scatter(
    x=full_ng["year"], y=full_ng["completions"], mode="lines+markers",
    line=dict(color=colors[1], width=2), marker=dict(size=5),
    name="Completions (actual)", hovertemplate="Year %{x}<br>Completions: %{y:,}<extra></extra>",
))
# Partial year point
if not partial_ng.empty:
    fig_gap.add_trace(go.Scatter(
        x=partial_ng["year"], y=partial_ng["completions"], mode="markers",
        marker=dict(color=colors[1], size=7, symbol="circle-open"),
        name="Completions (partial year)", hovertemplate="Year %{x} (partial)<br>Completions: %{y:,}<extra></extra>",
    ))

ch.style(fig_gap, title="National housing demand vs completions", height=380, ytitle="Dwellings",
         yfmt=",")
ch.show(fig_gap, key="dg_national")

# ---------------------------------------------------------------------------- gap bar chart
st.subheader("Annual gap (demand – completions)")

gap_colors = [T.STATUS["serious"] if g > 0 else T.STATUS["good"] for g in full_ng["gap_central"]]
fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(
    x=full_ng["year"], y=full_ng["gap_central"], marker_color=gap_colors,
    customdata=list(zip(full_ng["gap_low"], full_ng["gap_high"])),
    hovertemplate="Year %{x}<br>Gap (central): %{y:,}<br>Low: %{customdata[0]:,} | High: %{customdata[1]:,}<extra></extra>",
    name="Gap (central)",
))
fig_bar.add_hline(y=0, line_color=T.INK_2, line_dash="dot", line_width=1)
ch.style(fig_bar, title="Annual shortfall (positive) or surplus (negative) — central scenario", height=300, ytitle="Dwellings", legend=False)
ch.show(fig_bar, key="dg_gap_bar")

# ---------------------------------------------------------------------------- decomposition
with st.expander("Demand decomposition (national, central scenario)", expanded=False):
    st.caption("How annual demand splits into population growth, household-size change and replacement.")
    full_dec = dec[~dec["is_partial_year"]].copy()
    fig_dec = go.Figure()
    for col, label, color in [
        ("population_growth_demand", "Population growth", colors[0]),
        ("hh_size_change_demand", "Household-size change", colors[2]),
        ("replacement_demand", "Replacement", colors[3]),
    ]:
        fig_dec.add_trace(go.Bar(
            x=full_dec["year"], y=full_dec[col], name=label,
            marker_color=color,
            hovertemplate="Year %{x}<br>" + label + ": %{y:,}<extra></extra>",
        ))
    fig_dec.update_layout(barmode="stack")
    ch.style(fig_dec, title="Demand decomposition", height=300, ytitle="Dwellings", legend=True)
    ch.show(fig_dec, key="dg_decomp")

st.divider()

# ---------------------------------------------------------------------------- county gap
st.subheader("County supply-demand gap")

latest_county_year = int(cg["year"].max())
avail_years = sorted(cg["year"].unique(), reverse=True)
sel_year = st.selectbox("Year (county view)", avail_years, index=0, key="dg_county_year",
                        format_func=lambda y: f"{y}" + (" (partial)" if cg[(cg["year"] == y) & (cg["is_partial_year"])].any().any() else ""))

cg_yr = cg[cg["year"] == sel_year].sort_values("gap", ascending=False).copy()
cg_yr["gap_label"] = cg_yr["gap"].apply(lambda g: f"{int(g):+,}" if pd.notna(g) else "–")

col_colors = [T.STATUS["serious"] if (pd.notna(g) and g > 0) else T.STATUS["good"] for g in cg_yr["gap"]]

fig_county = go.Figure()
fig_county.add_trace(go.Bar(
    x=cg_yr["county"], y=cg_yr["gap"], marker_color=col_colors, name="Gap",
    text=cg_yr["gap_label"], textposition="outside",
    hovertemplate="%{x}<br>Gap: %{y:,}<br>Demand: %{customdata[0]:,}<br>Completions: %{customdata[1]}<extra></extra>",
    customdata=list(zip(cg_yr["total_demand"], cg_yr["completions"].fillna("–").astype(str))),
))
fig_county.add_hline(y=0, line_color=T.INK_2, line_dash="dot", line_width=1)
ch.style(fig_county, title=f"County supply-demand gap {sel_year} (central, PEA08 estimates)", height=420,
         ytitle="Dwellings (demand − completions)", legend=False)
fig_county.update_layout(xaxis_tickangle=-45)
ch.show(fig_county, key="dg_county_bar")

# ---------------------------------------------------------------------------- county table
with st.expander("County-level detail table", expanded=False):
    display_cg = cg_yr[["county", "population", "pop_change", "total_demand", "completions", "gap", "hh_size", "replacement_demand"]].copy()
    display_cg.columns = ["County", "Population", "Pop change", "Demand", "Completions", "Gap", "Avg hh size", "Replacement demand"]
    ch.show_df(display_cg)

# ---------------------------------------------------------------------------- methodology note
with st.expander("Assumptions and limitations", expanded=False):
    st.markdown("""
**Demand model**
- Annual household demand = (population change / average household size) + replacement demand
- Average household size is interpolated linearly between Census 2016 (2.75) and Census 2022 (2.74); county values use county Census figures
- Replacement rate = 0.4% of Census housing stock per year (a standard European estimate)
- National stock post-Census 2022 is extrapolated by adding cumulative completions

**Scenario bands (national only)**
- **Central:** observed net migration from CSO PEA15
- **High demand:** less emigration / more immigration (multiplier = 0.5 on negative migration, 1.5 on positive)
- **Low demand:** more emigration / less immigration (multiplier = 1.5 on negative migration, 0.5 on positive)
- Natural increase is held at the observed PEA15 figure in all scenarios

**Limitations**
- PEA08 county estimates are rounded to the nearest hundred persons; small pop changes carry large relative errors
- Completions are ESB-based proxies (new connections), not measured building completions
- The model counts dwellings, not whether they are affordable, in the right location, or of the right type
- 'Replacement demand' is an estimate, not a measured demolition rate
- The gap is per year, not cumulative: an annual surplus does not erase a previous shortfall
""")
