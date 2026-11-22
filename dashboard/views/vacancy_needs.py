"""Page 5 - Vacancy and Housing Needs (vacancy, reuse potential, social housing, homelessness)."""
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

T.page_header("Vacancy and Housing Needs",
              "Where dwellings are vacant, why, and where housing need is greatest - social housing demand and homelessness.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
counties = D.county_list()

T.note("<b>Vacant does not mean available.</b> A vacant dwelling may be uninhabitable, awaiting probate or sale, a second home in transition, or too costly to "
       "restore. These pages show where vacancy is concentrated and why it is recorded; they do <b>not</b> show how many homes could be brought into use "
       "or how quickly.", "warn")
selected = st.multiselect("Counties to highlight", counties, default=["Dublin", "Cork", "Galway", "Limerick", "Waterford"], max_selections=8, key="vn_counties")

tab_vac, tab_reuse, tab_social, tab_home = st.tabs(["Vacancy", "Reuse screening", "Social housing", "Homelessness"])

# =============================================================================== vacancy
with tab_vac:
    v_years = sorted(tables["vacancy_estimates"]["year"].unique())
    c1, c2 = st.columns([1, 3])
    with c1:
        vy = st.selectbox("Year (Q4)", v_years, index=len(v_years) - 1, key="vn_year")
    vc = calc.vacancy_by_county(tables, vy)
    a1, a2 = st.columns(2)
    with a1:
        ch.show(ch.hbar_ranked(vc, "county", "vacancy_rate_pct", f"Estimated vacancy rate by county, Q4 {vy}", highlight=selected, height=620, value_fmt=",.1f",
                               unit_suffix="%"), "vn_vac_rank")
        T.caption("CSO VAC14: dwellings with low or no electricity use as a share of the ESB-connection dwelling stock. County = sum of its local authorities.")
    with a2:
        ch.show(ch.county_map(vc, D.counties_geojson(), "vacancy_rate_pct", "Vacancy rate (%)", highlight=selected, fmt=",.1f", height=620), "vn_vac_map")
        T.caption("Outlined counties are those selected above. Darker = higher estimated vacancy.")
    b1, b2 = st.columns(2)
    with b1:
        la = calc.vacancy_by_la(tables, vy)
        shown = la.assign(la=lambda x: x["la_name"].str.replace(" County Council", "").str.replace(" City Council", " City").str.replace(" and County Council", "")
                          .str.replace(" City & County Council", "")).head(12)
        ch.show(ch.bars(shown, "la", "vacancy_rate_pct", f"Highest vacancy rates by local authority, Q4 {vy}", ytitle="% of dwelling stock", hover_fmt=",.1f",
                        single_color=T.CATEGORICAL[3]), "vn_vac_la")
    with b2:
        reg = vc.merge(tables["dim_county"][["county", "nuts3_region"]], on="county").groupby("nuts3_region").agg(
            vacant=("vacant_dwellings", "sum"), stock=("dwelling_stock", "sum"), long_term=("long_term_vacant", "sum")).reset_index()
        reg["rate"] = 100 * reg["vacant"] / reg["stock"]
        reg["lt_share"] = 100 * reg["long_term"] / reg["vacant"]
        ch.show(ch.hbar_ranked(reg, "nuts3_region", "rate", f"Vacancy rate by region, Q4 {vy}", height=360, value_fmt=",.1f", unit_suffix="%"), "vn_vac_reg")
    tr = calc.vacancy_trend_national(tables)
    st.markdown("**National trend**")
    ch.show_df(tr.rename(columns={"year": "Q4 of", "vacant_dwellings": "Vacant dwellings", "dwelling_stock": "Dwelling stock", "vacancy_rate_pct": "Rate (%)"}).round(2))

# =============================================================================== reuse
with tab_reuse:
    st.markdown("**Reasons for vacancy (Census 2022) and potential reuse pathways**")
    r1, r2 = st.columns([1, 3])
    with r1:
        scope = st.selectbox("Area", ["Ireland"] + counties, key="vn_reason_scope")
    reasons = calc.vacancy_reasons(tables, None if scope == "Ireland" else scope)
    a1, a2 = st.columns(2)
    with a1:
        fig = ch.hbar_ranked(reasons, "reason", "vacant_dwellings", f"Census 2022 vacant dwellings by reason - {scope}", height=420, value_fmt=",.0f")
        ch.show(fig, "vn_reasons")
    with a2:
        grp = reasons.groupby("reason_group", as_index=False)["vacant_dwellings"].sum()
        grp["share"] = 100 * grp["vacant_dwellings"] / grp["vacant_dwellings"].sum()
        gcol = {"Needs work / probate": T.CATEGORICAL[1], "In market transition": T.CATEGORICAL[0], "Family or care circumstances": T.CATEGORICAL[2],
                "Other / not stated": "#b8c4d6"}
        fig = ch.bars(grp, "reason_group", "share", "Reuse-pathway grouping (share of vacant dwellings)", color="reason_group", color_map=gcol,
                      ytitle="% of vacant dwellings", hover_fmt=",.1f", barmode="group")
        fig.update_layout(showlegend=False)
        ch.show(fig, "vn_reason_groups")
    T.caption("CSO F2014 (Census night, April 2022). The grouping is a HomeScope screening device: 'Needs work / probate' = Renovation + Deceased; "
              "'In market transition' = For sale, Rental, New build; 'Family or care' = With relatives, Nursing home/hospital. "
              "No group proves a home is habitable, available or economic to restore.")

    st.markdown("**Where is vacancy not where the pressure is?**")
    sc = D.scorecard_table()
    ch.show(ch.scatter(sc, "vacancy_rate_pct", "rent_change_since_2019_pct", "county", "Vacancy rate vs rent growth since Q4 2019, by county",
                       xtitle="Estimated vacancy rate, Q4 2024 (%)", ytitle="Rent change since Q4 2019 (%)", highlight=selected, height=460), "vn_scatter")
    T.caption("Each dot is a county. Compare the position of high-vacancy counties with the counties under most rent pressure (see County Comparison).")

    reuse = vc[["county", "vacant_dwellings", "long_term_vacant", "long_term_share_pct"]].merge(
        tables["vacancy_reasons_census"].assign(g=lambda d: d["reason"].map(calc.REASON_GROUPS)).query("g == 'Needs work / probate'")
        .groupby("county", as_index=False)["vacant_dwellings"].sum().rename(columns={"vacant_dwellings": "census_needs_work_or_probate"}), on="county")
    reuse.columns = ["County", "Vacant dwellings (est., latest Q4)", "Vacant for six years", "Long-term share of vacant (%)", "Census 2022: vacant for renovation/probate"]
    st.markdown("**Screening table** (counts are published statistics; they are not estimates of homes that can be reused)")
    ch.show_df(reuse.round(1).sort_values("Vacant for six years", ascending=False))

# =============================================================================== social
with tab_social:
    s1, s2 = st.columns(2)
    with s1:
        nat = tables["social_housing_need_national"].sort_values("year")
        fig = ch.line(nat, "year", "households_with_children_in_need", None, "Households with children identified as in need of social housing (State)", ytitle="Households",
                      hover_fmt=",.0f", legend=False)
        fig.update_traces(mode="lines+markers", marker=dict(size=7))
        ch.show(fig, "vn_need_trend")
        T.caption("CSO SCA10. Counts cover households with children only and depend on eligibility rules and list management - a fall does not necessarily mean lower need.")
    with s2:
        sn = calc.social_need(tables)
        ch.show(ch.hbar_ranked(sn, "county", "need_per_1000_households", f"Families with children in need of social housing per 1,000 households, {sn.attrs['year']}",
                               highlight=selected, height=620, value_fmt=",.1f"), "vn_need_county")
        T.caption("CSO SCA10 / F2001 (Census 2022 households).")
    ts = calc.tenure_shares(tables)
    show = ts[ts["county"].isin(selected)] if selected else ts
    long = show.melt(id_vars="county", value_vars=["social_rented_pct", "private_rented_pct"], var_name="m", value_name="pct")
    long["m"] = long["m"].map({"social_rented_pct": "Social rented (local authority + voluntary body)", "private_rented_pct": "Private rented"})
    ch.show(ch.bars(long, "county", "pct", "Share of households renting, Census 2022 (%)", color="m",
                    color_map={"Social rented (local authority + voluntary body)": T.CATEGORICAL[2], "Private rented": T.CATEGORICAL[0]},
                    ytitle="% of households", hover_fmt=",.1f", barmode="group"), "vn_tenure")
    T.caption("CSO F2004. The existing social stock at Census 2022, not recent delivery or the full waiting list. "
              "Waiting-list and delivery data are listed as future work (see FUTURE_ENHANCEMENTS.md).")

# =============================================================================== homelessness
with tab_home:
    hn = calc.homelessness_national(tables)
    h1, h2 = st.columns(2)
    with h1:
        fig = ch.line(hn, "report_month", "total_persons", None, "People in emergency accommodation (adults + dependants)", ytitle="Persons", hover_fmt=",.0f", legend=False)
        fig.update_traces(connectgaps=False)
        ch.show(fig, "vn_home_trend")
        gaps = pd.date_range(hn["report_month"].min(), hn["report_month"].max(), freq="MS").difference(hn["report_month"])
        T.caption("Dept. of Housing monthly Homelessness Reports (data.gov.ie). " + (f"Months not available in the open-data series: {', '.join(g.strftime('%b %Y') for g in gaps)}." if len(gaps) else ""))
    with h2:
        months = sorted(tables["homelessness_monthly"]["report_month"].unique())
        mchoice = st.selectbox("Report month", [pd.Timestamp(m) for m in reversed(months)], format_func=lambda m: m.strftime("%B %Y"), key="vn_home_month")
        hr = calc.homelessness_by_region(tables, mchoice)
        ch.show(ch.hbar_ranked(hr, "region", "persons_per_10000", f"Persons in emergency accommodation per 10,000 residents, {mchoice:%B %Y}", height=380,
                               value_fmt=",.1f"), "vn_home_region")
        T.caption("Rates use Census 2022 population for the Department's nine regions (HomeScope's county grouping).")
    k1, k2 = st.columns(2)
    with k1:
        comp = tables["homelessness_monthly"].groupby("report_month", as_index=False)[["adults_total", "dependants"]].sum()
        comp = comp.melt(id_vars="report_month", var_name="m", value_name="v")
        comp["m"] = comp["m"].map({"adults_total": "Adults", "dependants": "Dependants (children)"})
        fig = ch.bars(comp, "report_month", "v", "Adults and child dependants", color="m", color_map={"Adults": T.CATEGORICAL[0], "Dependants (children)": T.CATEGORICAL[1]},
                      barmode="stack", ytitle="Persons", hover_fmt=",.0f")
        ch.show(fig, "vn_home_comp")
    with k2:
        fam = hn[["report_month", "families"]]
        ch.show(ch.line(fam, "report_month", "families", None, "Families in emergency accommodation", ytitle="Families", hover_fmt=",.0f", legend=False,
                        ), "vn_home_fam")
    T.caption("The count reflects people in emergency accommodation in the reference week. It excludes hidden homelessness (e.g. sofa-surfing) and some supported accommodation.")
