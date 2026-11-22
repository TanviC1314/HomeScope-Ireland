"""Page 2 - County Comparison (interactive map, ranking, side-by-side indicators)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import calculations as calc  # noqa: E402
from src.indicators import scorecard as sc  # noqa: E402

T.page_header("County Comparison",
              "Compare counties on rents, affordability, housing supply, population growth and vacancy. "
              "Select counties to highlight them on the map and in every chart below.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
score = D.scorecard_table()
counties = D.county_list()
cmap_all = ch.entity_colors(["Dublin", "Cork", "Galway", "Limerick", "Waterford"])

# ------------------------------------------------------------------------------ controls
c1, c2 = st.columns([3, 2])
with c1:
    selected = st.multiselect("Counties to compare (up to 8)", counties, default=["Dublin", "Cork", "Galway", "Limerick", "Waterford"],
                              max_selections=8, key="cc_counties")
with c2:
    labels = {m.label: m.column for m in sc.SCORE_COLUMNS}
    ind_label = st.selectbox("Map and ranking indicator", list(labels), index=0, key="cc_indicator")
col = labels[ind_label]
meta = sc.BY_COLUMN[col]
cmap = ch.entity_colors(selected)

if not selected:
    T.note("Select at least one county to compare. The map and ranking show all 26 counties.", "warn")

# ------------------------------------------------------------------------------ map + ranking
m1, m2 = st.columns([5, 4])
with m1:
    fig = ch.county_map(score, D.counties_geojson(), col, f"{meta.label} ({meta.unit})", highlight=selected, fmt=f",.{meta.decimals}f")
    ch.show(fig, "cc_map")
    T.caption(f"Boundaries: Tailte Eireann (OSi) counties, generalised 20m (CC BY 4.0). Outlined = selected. Period: {meta.period}.")
with m2:
    fig = ch.hbar_ranked(score, "county", col, f"{meta.label} - all 26 counties", highlight=selected, height=560, value_fmt=f",.{meta.decimals}f")
    ch.show(fig, "cc_rank")
    T.caption(f"{meta.reading}. Source indicator: {meta.indicator_id} (see Data and Methodology).")

# ------------------------------------------------------------------------------ side-by-side table
st.subheader("Selected counties side by side")
if selected:
    rows = []
    for m in sc.SCORE_COLUMNS:
        row = {"Indicator": m.label, "Period": m.period}
        for cty in selected:
            row[cty] = sc.format_value(m.column, score.loc[score["county"] == cty, m.column].iloc[0])
        row["Median of 26 counties"] = sc.format_value(m.column, score[m.column].median())
        rows.append(row)
    ch.show_df(pd.DataFrame(rows))
    T.caption("Pressure flags count how many of six indicators (rent level, rent growth, rent-to-income, low completions, households outpacing stock, "
              "social housing need) place a county in the most-pressured quartile. No weights, no composite score.")

# ------------------------------------------------------------------------------ trend charts
if selected:
    st.subheader("Trends")
    t1, t2 = st.columns(2)
    with t1:
        rs = calc.rent_series(tables)
        years = (int(rs["year"].min()), int(rs["year"].max()))
        yr = st.slider("Rent trend: year range", years[0], years[1], (2015, years[1]), key="cc_rent_years")
        d = rs[rs["county"].isin(selected) & rs["year"].between(*yr)]
        fig = ch.line(d, "period", "avg_monthly_rent", "county", "Average monthly rent (RTB)", color_map=cmap, ytitle="EUR per month", hover_fmt=",.0f")
        ch.show(fig, "cc_rent_trend")
        T.caption("CSO RIQ02, all bedrooms and property types, new tenancies. Latest quarter: 2025Q4.")
    with t2:
        mode = st.radio("Completions measure", ["Dwellings completed", "Per 1,000 residents (Census 2022)"], horizontal=True, key="cc_comp_mode")
        ac = calc.annual_completions(tables, "county")
        ac = ac[~ac["is_partial_year"] & (ac["year"] >= 2012) & ac["county"].isin(selected)].copy()
        if mode.startswith("Per"):
            pop = tables["population_census"].query("census_year == 2022").set_index("county")["population"]
            ac["value"] = 1000 * ac["completions"] / ac["county"].map(pop)
            ytitle, fmt = "Per 1,000 residents", ",.1f"
        else:
            ac["value"], ytitle, fmt = ac["completions"], "Dwellings", ",.0f"
        fig = ch.line(ac, "year", "value", "county", "Completions per full calendar year", color_map=cmap, ytitle=ytitle, hover_fmt=fmt)
        ch.show(fig, "cc_comp_trend")
        T.caption("CSO NDQ06. Partial years are excluded. Per-1,000 uses a fixed 2022 population, so later years are approximate.")

    g1, g2 = st.columns(2)
    with g1:
        cg = calc.census_growth(tables)
        cg = cg[cg["county"].isin(selected)]
        long = cg.melt(id_vars="county", value_vars=["population_growth_pct", "household_growth_pct", "stock_growth_pct"],
                       var_name="measure", value_name="growth")
        long["measure"] = long["measure"].map({"population_growth_pct": "Population", "household_growth_pct": "Households", "stock_growth_pct": "Housing stock"})
        fig = ch.bars(long, "county", "growth", "Growth between Census 2016 and 2022 (%)", color="measure",
                      color_map={"Population": T.CATEGORICAL[0], "Households": T.CATEGORICAL[1], "Housing stock": T.CATEGORICAL[2]},
                      ytitle="% change", hover_fmt=",.1f", barmode="group")
        ch.show(fig, "cc_growth")
        T.caption("CSO F1003, F2001, F2020. Households growing faster than housing stock signals pressure.")
    with g2:
        v = calc.vacancy_by_county(tables)
        v = v[v["county"].isin(selected)].melt(id_vars="county", value_vars=["vacancy_rate_pct", "long_term_rate_pct"], var_name="m", value_name="rate")
        v["m"] = v["m"].map({"vacancy_rate_pct": "All estimated vacant", "long_term_rate_pct": "Vacant for 6 years"})
        fig = ch.bars(v, "county", "rate", "Estimated vacancy as % of dwelling stock (Q4 2024)", color="m",
                      color_map={"All estimated vacant": T.CATEGORICAL[3], "Vacant for 6 years": T.CATEGORICAL[4]}, ytitle="% of stock",
                      hover_fmt=",.1f", barmode="group")
        ch.show(fig, "cc_vacancy")
        T.caption("CSO VAC14, VAC23. Vacant does not mean habitable or available.")

with st.expander("Pressure flags - all counties (table view)"):
    show = D.pressure_table().rename(columns={"county": "County", "pressure_flags": "Flags (0-6)"})
    ch.show_df(show[["County", "Flags (0-6)", "rent_latest", "rent_change_since_2019_pct", "rent_pct_income", "completions_per_1000",
                     "household_minus_stock_growth_pp", "need_per_1000_households"]].round(1))
