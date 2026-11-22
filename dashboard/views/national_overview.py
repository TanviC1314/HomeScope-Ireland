"""Page 1 - National Housing Overview."""
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

T.page_header("National Housing Overview",
              "Where Irish housing supply, population, rents, prices, vacancy and homelessness stand - and how they have moved over time. "
              "Official CSO, RTB and Department of Housing statistics only.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
k = D.kpis()

# ------------------------------------------------------------------------------ KPI cards
row1, row2 = st.columns(3), st.columns(3)
with row1[0]:
    T.kpi_card("Housing completions", f"{k['completions_latest_full_year']:,}", f"{k['completions_yoy_pct']:+.1f}% vs {k['latest_full_year'] - 1}",
               f"{k['latest_full_year']} (full year)", "published")
with row1[1]:
    T.kpi_card("Population", f"{k['population_thousand'] / 1000:.2f} million", f"{k['population_growth_pct']:+.1f}% in the year",
               f"April {k['population_year']} (CSO estimate)", "published")
with row1[2]:
    T.kpi_card("Average monthly rent", f"EUR {k['rent_proxy']:,.0f}", f"{k['rent_yoy_pct']:+.1f}% vs a year earlier",
               f"{k['rent_period']} - weighted county average", "estimate")
with row2[0]:
    T.kpi_card("Property price index", f"{k['price_index']:.1f}", f"{k['price_yoy_pct']:+.1f}% in 12 months",
               f"{k['price_period']:%B %Y} (2015 = 100)", "published")
with row2[1]:
    T.kpi_card("Estimated vacancy rate", f"{k['vacancy_rate_pct']:.1f}%", f"{k['vacant_dwellings']:,} vacant dwellings",
               f"Q4 {k['vacancy_year']} - not all habitable or available", "published")
with row2[2]:
    T.kpi_card("In emergency accommodation", f"{k['homeless_persons']:,}", f"{k['homeless_yoy_pct']:+.1f}% vs a year earlier",
               f"{k['homeless_month']:%B %Y} (Dept. of Housing)", "published")
st.write("")

# ------------------------------------------------------------------------------ filters
nat_comp = calc.annual_completions(tables, "national")
all_years = list(range(2011, int(nat_comp["year"].max()) + 1))
f1, f2, f3 = st.columns([3, 2, 3])
with f1:
    yr = st.slider("Year range (trend charts)", min_value=all_years[0], max_value=all_years[-1], value=(2012, all_years[-1]), key="nat_years")
with f2:
    partial = st.checkbox("Include the latest partial year", value=True, key="nat_partial",
                          help="The latest calendar year is incomplete; it is shown lighter and is never used for year-on-year comparisons.")
with f3:
    T.caption("Charts show actual published statistics unless labelled otherwise (derived or estimate). "
              "Partial years are drawn in a lighter tone.")

# ------------------------------------------------------------------------------ row 1: supply + population
r1a, r1b = st.columns(2)
with r1a:
    comp = nat_comp[nat_comp["year"].between(*yr)].copy()
    if not partial:
        comp = comp[~comp["is_partial_year"]]
    fig = ch.bars(comp, "year", "completions", "New dwelling completions per year", ytitle="Dwellings", opacity_col="is_partial_year")
    fig.update_xaxes(dtick=1)
    ch.show(fig, "nat_completions")
    T.caption("CSO NDQ06 (ESB Networks connections based). Lighter bar = partial year.")
with r1b:
    pop = calc.national_population(tables)
    pop = pop[pop["year"].between(max(yr[0], 2000), yr[1] + 1)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pop["year"], y=pop["natural_increase_thousand"], name="Natural increase", marker=dict(color=T.CATEGORICAL[0], cornerradius=3,
                                                                                                          line=dict(color=T.SURFACE, width=2))))
    fig.add_trace(go.Bar(x=pop["year"], y=pop["net_migration_thousand"], name="Net migration", marker=dict(color=T.CATEGORICAL[1], cornerradius=3,
                                                                                                      line=dict(color=T.SURFACE, width=2))))
    fig.update_layout(barmode="relative")
    ch.style(fig, "Annual population change (thousands, April to April)", 360, ytitle="Thousand persons")
    ch.show(fig, "nat_population")
    T.caption("CSO PEA15. Natural increase = births minus deaths. Latest years are provisional estimates.")

# ------------------------------------------------------------------------------ row 2: rent + prices
r2a, r2b = st.columns(2)
with r2a:
    prox = calc.national_rent_proxy(tables).assign(series="Ireland (weighted county average, estimate)")
    dub = calc.rent_series(tables).query("county == 'Dublin'").assign(series="Dublin")[["year", "quarter", "period", "avg_monthly_rent", "series"]]
    rent = pd.concat([prox[["year", "quarter", "period", "avg_monthly_rent", "series"]], dub])
    rent = rent[rent["year"].between(max(yr[0], 2008), yr[1])]
    fig = ch.line(rent, "period", "avg_monthly_rent", "series", "Average monthly rent (RTB, new tenancies)", ytitle="EUR per month", hover_fmt=",.0f",
                  color_map={"Dublin": T.CATEGORICAL[0], "Ireland (weighted county average, estimate)": T.CATEGORICAL[1]})
    ch.show(fig, "nat_rent")
    T.caption("CSO RIQ02. The national line is a HomeScope estimate: county averages weighted by private-rented households (Census 2022).")
with r2b:
    parts = []
    for geo, label in (("National", "National"), ("Dublin", "Dublin"), ("National excluding Dublin", "Outside Dublin")):
        s = calc.property_price_series(tables, geo)[["period", "rppi_index"]].assign(series=label)
        parts.append(s)
    pp = pd.concat(parts)
    pp = pp[(pp["period"].dt.year >= max(yr[0], 2005)) & (pp["period"].dt.year <= yr[1] + (1 if partial else 0))]
    fig = ch.line(pp, "period", "rppi_index", "series", "Residential property price index (2015 = 100)", ytitle="Index", hover_fmt=",.1f",
                  color_map={"Dublin": T.CATEGORICAL[0], "National": T.CATEGORICAL[1], "Outside Dublin": T.CATEGORICAL[2]})   # Dublin = blue everywhere
    fig.add_hline(y=100, line=dict(color=T.MUTED, width=1, dash="dot"))
    ch.show(fig, "nat_prices")
    T.caption("CSO HPM09. An index, not a euro price.")

# ------------------------------------------------------------------------------ row 3: vacancy + supply pipeline
r3a, r3b = st.columns(2)
with r3a:
    vt = calc.vacancy_trend_national(tables)
    census = tables["housing_stock_census"].query("census_year == 2022")
    fig = ch.bars(vt.assign(year=vt["year"].astype(str) + " (Q4)"), "year", "vacant_dwellings", "Estimated vacant dwellings", ytitle="Dwellings",
                  single_color=T.CATEGORICAL[3])
    ch.show(fig, "nat_vacancy")
    row = vt.iloc[-1]
    T.caption(f"CSO VAC14. Rate {vt.iloc[0]['vacancy_rate_pct']:.2f}% in {int(vt.iloc[0]['year'])} -> {row['vacancy_rate_pct']:.2f}% in {int(row['year'])}. "
              f"Census 2022 counted {int(census['vacant'].sum()):,} vacant dwellings (different method). Vacant does not mean habitable or available.")
with r3b:
    comp_all = nat_comp.assign(series="Completions")[["year", "completions", "series", "is_partial_year"]].rename(columns={"completions": "units"})
    cm = calc.commencements_annual(tables, "national").assign(series="Commencements")[["year", "units", "series", "is_partial_year"]]
    pl = (tables["planning_permissions_national"].groupby("year", as_index=False)["units"].sum().assign(series="Permitted (planning)", is_partial_year=False))
    sup = pd.concat([comp_all, cm, pl])
    sup = sup[sup["year"].between(*yr)]
    sup = sup if partial else sup[~sup["is_partial_year"]]
    fig = ch.line(sup, "year", "units", "series", "Supply pipeline: permissions, commencements and completions", ytitle="Dwelling units", hover_fmt=",.0f",
                  color_map={"Completions": T.CATEGORICAL[0], "Commencements": T.CATEGORICAL[1], "Permitted (planning)": T.CATEGORICAL[2]})
    ch.show(fig, "nat_pipeline")
    T.caption("CSO BHA13, HSM13, NDQ06. Commencements are lumpy (e.g. a single month in April 2024 recorded 18,700 units); partial years included only if ticked.")

with st.expander("Table view of the headline series"):
    t_comp = nat_comp[["year", "completions", "quarters_reported"]]
    ch.show_df(t_comp.sort_values("year", ascending=False))
st.markdown("---")
T.note("<b>How to read this page.</b> KPI badges show whether a number is a <i>published statistic</i>, a <i>derived indicator</i> or an <i>estimate</i>. "
       "Definitions, sources and limitations for every indicator are on the <b>Data and Methodology</b> page.")
