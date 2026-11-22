"""Page 3 - Housing Affordability."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import calculations as calc  # noqa: E402

T.page_header("Housing Affordability",
              "Rents, property prices and incomes: how expensive is housing, how fast is it changing, and where is the burden heaviest?")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
counties = D.county_list()
rents = tables["rents_rtb"]

# ------------------------------------------------------------------------------ filters
f1, f2, f3 = st.columns([3, 2, 2])
with f1:
    selected = st.multiselect("Counties", counties, default=["Dublin", "Cork", "Galway", "Limerick", "Waterford"], max_selections=8, key="af_counties")
with f2:
    bedrooms = st.selectbox("Bedrooms", ["All bedrooms", "One bed", "Two bed", "Three bed", "Four plus bed"], key="af_bed")
with f3:
    ptype = st.selectbox("Property type", ["All property types", "Apartment", "Detached house", "Semi detached house", "Terrace house"], key="af_ptype")
cmap = ch.entity_colors(selected)
rs_all = calc.rent_series(tables, bedrooms, ptype)
if rs_all.empty:
    T.note("No RTB rent data are published for this bedroom / property-type combination.", "warn")
    st.stop()
yr_min, yr_max = int(rs_all["year"].min()), int(rs_all["year"].max())

# ------------------------------------------------------------------------------ rents
st.subheader("Rents")
a1, a2 = st.columns(2)
with a1:
    yr = st.slider("Year range", yr_min, yr_max, (max(yr_min, 2012), yr_max), key="af_years")
    d = rs_all[rs_all["county"].isin(selected) & rs_all["year"].between(*yr)]
    ch.show(ch.line(d, "period", "avg_monthly_rent", "county", f"Average monthly rent - {bedrooms.lower()}, {ptype.lower()}", color_map=cmap,
                    ytitle="EUR per month", hover_fmt=",.0f"), "af_rent_trend")
    T.caption("CSO RIQ02 (RTB). Standardised average rent for new tenancies; missing quarters mean no figure was published for that cut.")
with a2:
    base_year = st.select_slider("Compare latest rent with Q4 of", options=list(range(max(yr_min, 2008), yr_max)), value=2019, key="af_base")
    rc = calc.rent_change(tables, base=(base_year, 4), bedrooms=bedrooms, property_type=ptype)
    (ly, lq) = rc.attrs["latest"]
    fig = ch.hbar_ranked(rc, "county", "change_since_base_pct", f"Rent change, Q4 {base_year} to Q{lq} {ly}", highlight=selected, height=560,
                         value_fmt=",.0f", unit_suffix="%")
    ch.show(fig, "af_rent_change")
    T.caption("Percentage changes start from different base levels: counties with lower rents in the base year can show larger percentage rises.")

# ------------------------------------------------------------------------------ prices
st.subheader("Property prices")
p1, p2 = st.columns(2)
with p1:
    geos = sorted(tables["property_price_index"]["geography"].unique())
    default_geo = [g for g in ("National", "Dublin", "National excluding Dublin") if g in geos]
    sel_geo = st.multiselect("Price index areas", geos, default=default_geo, max_selections=6, key="af_geo")
    dtype = st.radio("Dwelling type", ["all residential properties", "houses", "apartments"], horizontal=True, key="af_dtype")
    pp = tables["property_price_index"]
    pp = pp[pp["geography"].isin(sel_geo) & (pp["dwelling_type"] == dtype)]
    if pp.empty:
        T.note("The CSO publishes this dwelling type only for some areas (e.g. regional series cover houses only).", "warn")
    else:
        gmap = ch.entity_colors(sel_geo, preferred=["National", "Dublin", "National excluding Dublin"])
        fig = ch.line(pp, "period", "rppi_index", "geography", f"Residential property price index - {dtype}", color_map=gmap, ytitle="Index (2015 = 100)")
        fig.add_hline(y=100, line=dict(color=T.MUTED, width=1, dash="dot"))
        ch.show(fig, "af_prices")
    T.caption("CSO HPM09. Index, not euro prices; county-level prices are not published by the CSO.")
with p2:
    s = calc.property_price_summary(tables, "National")
    d = calc.property_price_summary(tables, "Dublin")
    x = calc.property_price_summary(tables, "National excluding Dublin")
    rows = pd.DataFrame({
        "Area": ["National", "Dublin", "National excluding Dublin"],
        "Latest index": [s["latest_index"], d["latest_index"], x["latest_index"]],
        "12-month change (%)": [s["change_12m_pct"], d["change_12m_pct"], x["change_12m_pct"]],
        "vs 2015 average (%)": [s["index_vs_2015_pct"], d["index_vs_2015_pct"], x["index_vs_2015_pct"]],
        "vs pre-crisis peak (%)": [s["index_vs_prior_peak_pct"], d["index_vs_prior_peak_pct"], x["index_vs_prior_peak_pct"]]}).round(1)
    st.markdown(f"**Summary - {s['latest_period']:%B %Y}**")
    ch.show_df(rows)
    T.caption("Pre-crisis peak = highest index value before 2015 for that series.")

# ------------------------------------------------------------------------------ incomes + burden
st.subheader("Income and the rent burden")
i1, i2 = st.columns(2)
with i1:
    inc = tables["household_income_county"]
    iy = st.selectbox("Income year", sorted(inc["year"].unique(), reverse=True), index=0, key="af_inc_year")
    di = inc[inc["year"] == iy][["county", "disposable_income_per_person"]]
    ch.show(ch.hbar_ranked(di, "county", "disposable_income_per_person", f"Disposable income per person, {iy}", highlight=selected, height=560,
                           value_fmt=",.0f"), "af_income")
    T.caption("CSO RAA02 (Estimates of Household Income). Per-person measure; household incomes are higher.")
with i2:
    r2i = calc.rent_to_income_county(tables)
    ch.show(ch.hbar_ranked(r2i, "county", "median_rent_pct_income", "Median RTB tenant rent as % of disposable income (2024)", highlight=selected,
                           height=560, value_fmt=",.1f", unit_suffix="%"), "af_r2i")
    T.caption("CSO TRS38. Local-authority medians combined to counties using dwelling stock as weights. The measured rent-to-income share.")

j1, j2 = st.columns(2)
with j1:
    la = calc.rent_to_income_la(tables)
    n_show = st.slider("Local authorities to show (highest burden)", 5, 31, 12, key="af_la_n")
    top = la.head(n_show).assign(la=lambda x: x["la_name"].str.replace(" County Council", "").str.replace(" City Council", " City").str.replace(" and County", ""))
    fig = ch.bars(top.melt(id_vars="la", value_vars=["pct_tenants_40plus"], var_name="m", value_name="pct").assign(m="Tenants paying 40% or more of income on rent"),
                  "la", "pct", "Share of tenants paying 40% or more of disposable income on rent (2024)", ytitle="% of tenants", hover_fmt=",.1f",
                  single_color=T.CATEGORICAL[1])
    ch.show(fig, "af_la_40")
    T.caption("CSO TRS38. Local authorities ordered by median rent-to-income share (highest first).")
with j2:
    ri = calc.rent_vs_income_per_person(tables)
    ch.show(ch.scatter(ri, "disposable_income_per_person", "annual_rent", "county", "Annual rent vs disposable income per person (relative view)",
                       xtitle="Disposable income per person (EUR/year)", ytitle="Annualised average rent (EUR)", highlight=selected), "af_scatter")
    T.caption("Derived indicator for comparing counties only: per-person income understates household income, so the burden level is overstated.")

with st.expander("Table view - county affordability indicators"):
    sc = D.scorecard_table()[["county", "rent_latest", "rent_change_since_2019_pct", "rent_pct_income", "annual_rent_pct_of_income_per_person",
                              "disposable_income_per_person"]].round(1)
    sc.columns = ["County", "Rent (EUR/month, latest)", "Rent change since Q4 2019 (%)", "Rent % of disposable income (2024, measured)",
                  "Annual rent % of income per person (relative)", "Disposable income per person (EUR)"]
    ch.show_df(sc)
T.note("<b>Reading affordability.</b> Three different lenses are shown: rent levels and changes (RTB), prices as an index (CSO RPPI), and the measured "
       "share of income spent on rent (CSO/RTB). They answer different questions and should not be added together.")
