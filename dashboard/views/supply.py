"""Page 4 - Housing Supply."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import calculations as calc  # noqa: E402

T.page_header("Housing Supply",
              "Completed dwellings, construction commencements and planning permissions - and how supply compares with population and household growth.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
counties = D.county_list()
comp_q = tables["completions_quarterly"]
last_year = int(comp_q["year"].max())

# ------------------------------------------------------------------------------ filters
f1, f2, f3 = st.columns([3, 3, 3])
with f1:
    yr = st.slider("Year range", 2011, last_year, (2012, last_year), key="su_years")
with f2:
    types = st.multiselect("Dwelling types", ["Single house", "Scheme house", "Apartment"], default=["Single house", "Scheme house", "Apartment"], key="su_types")
with f3:
    selected = st.multiselect("Counties (county charts)", counties, default=["Dublin", "Cork", "Galway", "Limerick", "Waterford"], max_selections=8, key="su_counties")
cmap = ch.entity_colors(selected)

# ------------------------------------------------------------------------------ completions
st.subheader("Completed dwellings")
a1, a2 = st.columns(2)
with a1:
    d = comp_q[comp_q["dwelling_type"].isin(types) & comp_q["year"].between(*yr)]
    g = d.groupby(["year", "dwelling_type"], as_index=False)["completions"].sum()
    q = comp_q.groupby("year")["quarter"].nunique()
    g["label"] = g["year"].map(lambda y: f"{y} (Q1-Q{q[y]})" if q[y] < 4 else str(y))
    tmap = {"Single house": T.CATEGORICAL[0], "Scheme house": T.CATEGORICAL[1], "Apartment": T.CATEGORICAL[2]}
    fig = ch.bars(g, "label", "completions", "New dwelling completions by type", color="dwelling_type", color_map=tmap, barmode="stack", ytitle="Dwellings")
    ch.show(fig, "su_types_chart")
    T.caption("CSO NDQ06. The latest year is partial and labelled with the quarters reported.")
with a2:
    ac = calc.annual_completions(tables, "county")
    ac = ac[~ac["is_partial_year"] & ac["year"].between(*yr) & ac["county"].isin(selected)]
    ch.show(ch.line(ac, "year", "completions", "county", "Completions by county (full years)", color_map=cmap, ytitle="Dwellings", hover_fmt=",.0f"), "su_county")
    T.caption("Counties are sums of their local authorities (Dublin = 4, Cork = 2, Galway = 2).")

# ------------------------------------------------------------------------------ commencements
st.subheader("Construction commencements")
b1, b2 = st.columns(2)
cm = tables["commencements_monthly"]
with b1:
    mon = cm.groupby("period", as_index=False)["units"].sum()
    mon = mon[mon["period"].dt.year.between(*yr)]
    fig = go.Figure(go.Bar(x=mon["period"], y=mon["units"], marker=dict(color=T.CATEGORICAL[1], cornerradius=2), name="Units commenced",
                           hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>"))
    ch.style(fig, "Residential units in commencement notices, by month", 360, legend=False, ytitle="Units", hover="closest")
    peak = mon.loc[mon["units"].idxmax()]
    fig.add_annotation(x=peak["period"], y=peak["units"], text=f"{peak['period']:%b %Y}: {peak['units']:,.0f}", showarrow=True, arrowhead=0,
                       font=dict(size=10, color=T.INK_2), ax=40, ay=0)
    ch.show(fig, "su_commence_monthly")
    T.caption("CSO HSM13. Monthly commencements are very lumpy; single months can dominate a year.")
with b2:
    ann = calc.commencements_annual(tables, "county")
    ann = ann[ann["county"].isin(selected) & ann["year"].between(*yr) & ~ann["is_partial_year"]]
    ch.show(ch.line(ann, "year", "units", "county", "Commencements by county (full years)", color_map=cmap, ytitle="Units", hover_fmt=",.0f"), "su_commence_county")
    T.caption("Commencement notices precede completions by many months; not every commenced unit completes.")

# ------------------------------------------------------------------------------ planning
st.subheader("Planning permissions and completions")
p1, p2 = st.columns([1, 1])
with p1:
    lag = st.slider("Compare completions with permissions granted this many years earlier", 0, 3, 0, key="su_lag")
    pv = calc.planning_vs_completions(tables, lag=lag, year_from=2018)
    yrs = sorted(pv["year"].unique())
    sel_year = st.selectbox("Completions year", yrs, index=len(yrs) - 1, key="su_plan_year")
    d = pv[pv["year"] == sel_year].melt(id_vars="region", value_vars=["completions", "permitted_units"], var_name="m", value_name="units")
    d["m"] = d["m"].map({"completions": f"Completions {sel_year}", "permitted_units": f"Units permitted {sel_year - lag}"})
    fig = ch.bars(d, "region", "units", f"Completions vs permitted units by NUTS3 region ({sel_year})", color="m",
                  color_map={f"Completions {sel_year}": T.CATEGORICAL[0], f"Units permitted {sel_year - lag}": T.CATEGORICAL[2]}, ytitle="Dwelling units",
                  barmode="group")
    ch.show(fig, "su_plan_region")
with p2:
    w0 = int(pv["year"].min())
    win = st.slider("Cumulative window (completions years)", w0, int(pv["year"].max()), (max(w0, 2021), int(pv["year"].max())), key="su_plan_win")
    cw = calc.planning_vs_completions_window(tables, win[0], win[1], lag=lag).sort_values("completions_to_permitted")
    cw["pct"] = 100 * cw["completions_to_permitted"]
    fig = ch.hbar_ranked(cw, "region", "pct", f"Completions as % of permitted units, {win[0]}-{win[1]} (lag {lag}y)", height=360, value_fmt=",.0f", unit_suffix="%")
    ch.show(fig, "su_plan_ratio")
T.caption("CSO BHA13 (regional values from 2018) and NDQ06. A simple comparison ratio, not a conversion rate: permissions can lapse, be re-applied for, "
          "or relate to homes completed outside this period. It does not show why permitted homes are not yet built.")

# ------------------------------------------------------------------------------ supply vs growth
st.subheader("Supply compared with population and household growth")
s1, s2 = st.columns(2)
with s1:
    cv = calc.completions_vs_household_growth(tables)
    fig = ch.hbar_ranked(cv, "county", "completions_per_added_household", "Completions 2016-2021 per household added (Census 2016-22)",
                         highlight=selected, height=620, value_fmt=",.2f")
    fig.add_vline(x=1, line=dict(color=T.MUTED, width=1, dash="dot"))
    ch.show(fig, "su_cv_hh")
    T.caption("Derived: completions in calendar years 2016-2021 / households added between Census 2016 and 2022. Below 1 = fewer new dwellings than new "
              "households (the gap is met from existing stock, e.g. falling vacancy). A rough comparison, not a measured shortfall.")
with s2:
    cg = calc.census_growth(tables)
    cg = cg[cg["county"].isin(selected)] if selected else cg
    long = cg.melt(id_vars="county", value_vars=["population_growth_pct", "household_growth_pct", "stock_growth_pct"], var_name="m", value_name="v")
    long["m"] = long["m"].map({"population_growth_pct": "Population", "household_growth_pct": "Households", "stock_growth_pct": "Housing stock"})
    fig = ch.bars(long, "county", "v", "Population, household and housing-stock growth, Census 2016-2022 (%)", color="m", height=620,
                  color_map={"Population": T.CATEGORICAL[0], "Households": T.CATEGORICAL[1], "Housing stock": T.CATEGORICAL[2]}, ytitle="% change", hover_fmt=",.1f")
    ch.show(fig, "su_growth")
    T.caption("CSO F1003, F2001, F2020. Households grew faster than housing stock in every county between 2016 and 2022.")

nat = calc.national_population(tables)
hh_nat = tables["households_census"].groupby("census_year")["households"].sum()
T.note(f"<b>National context.</b> Census households rose from {hh_nat[2016]:,.0f} (2016) to {hh_nat[2022]:,.0f} (2022), about "
       f"{(hh_nat[2022] - hh_nat[2016]) / 6:,.0f} per year. Population in April {int(nat['year'].max())} was estimated at "
       f"{nat.iloc[-1]['population_thousand'] * 1000:,.0f}.")

with st.expander("Table view - completions by county and year"):
    t = calc.annual_completions(tables, "county").pivot(index="county", columns="year", values="completions")
    t.columns = t.columns.astype(str)
    ch.show_df(t.reset_index())
