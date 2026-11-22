"""Page 8 - Data and Methodology."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from dashboard.components import charts as ch  # noqa: E402
from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import indicator_table  # noqa: E402

T.page_header("Data and Methodology",
              "Where the data come from, how they were cleaned, how every indicator is calculated, and what the limitations are.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)

tab_src, tab_ind, tab_dq, tab_lim = st.tabs(["Data sources", "Indicator definitions", "Cleaning and data quality", "Limitations"])

with tab_src:
    ds = tables["data_sources"].copy()
    st.markdown("All datasets are official open data. Licences permit reuse with attribution (CSO: CC BY 4.0; Department of Housing: CC BY-SA 4.0; "
                "Tailte Eireann boundaries: open data). Raw files are preserved unmodified; checksums are in `data/raw/MANIFEST.json`.")
    theme = st.multiselect("Theme", sorted(ds["theme"].dropna().unique()), default=[], key="me_theme", placeholder="All themes")
    if theme:
        ds = ds[ds["theme"].isin(theme)]
    view = ds[["source_key", "title", "provider", "theme", "publication_updated", "reference_period", "licence", "granularity", "landing_url"]]
    view.columns = ["Dataset", "Title", "Publisher", "Theme", "Published / updated", "Reference period", "Licence", "Granularity", "Source page"]
    st.dataframe(view, hide_index=True, column_config={"Source page": st.column_config.LinkColumn("Source page")})
    with st.expander("Notes on individual datasets"):
        for r in ds.itertuples():
            if r.notes:
                st.markdown(f"- **{r.source_key}** - {r.notes}")

with tab_ind:
    ind = indicator_table()
    q = st.text_input("Search indicators", "", key="me_search", placeholder="e.g. rent, vacancy, planning")
    cat = st.multiselect("Category", sorted(ind["category"].unique()), default=[], key="me_cat", placeholder="All categories")
    kind = st.multiselect("Type", ["published", "derived", "estimate"], default=[], key="me_kind", placeholder="All types")
    v = ind
    if q:
        mask = v.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)
        v = v[mask]
    if cat:
        v = v[v["category"].isin(cat)]
    if kind:
        v = v[v["kind"].isin(kind)]
    st.markdown(f"**{len(v)} indicators**")
    for r in v.itertuples():
        with st.expander(f"{r.name}  -  {r.kind}"):
            st.markdown(f"**Calculation.** {r.calculation}")
            st.markdown(f"**Source data.** {r.sources}")
            st.markdown(f"**Reference period.** {r.reference_period}")
            st.markdown(f"**Assumptions.** {r.assumptions}")
            st.markdown(f"**Limitations.** {r.limitations}")

with tab_dq:
    rep = D.quality_report()
    counts = rep["status"].value_counts()
    c = st.columns(4)
    c[0].metric("Checks recorded", len(rep))
    c[1].metric("Passed", int(counts.get("pass", 0)))
    c[2].metric("Repairs applied", int(counts.get("fixed", 0)))
    c[3].metric("Warnings", int(counts.get("warning", 0)))
    st.markdown("Cleaning rules: raw files are never modified; official statistics are never imputed (blank stays blank); national total rows are used to "
                "reconcile the sum of the parts and then removed; names are standardised to 26 counties / 31 local authorities; duplicates keep the first record. "
                "Every decision is listed below (also in `docs/DATA_QUALITY.md`).")
    ds_filter = st.multiselect("Dataset", sorted(rep["dataset"].unique()), default=[], key="me_dq_ds", placeholder="All datasets")
    st_filter = st.multiselect("Status", sorted(rep["status"].unique()), default=[], key="me_dq_status", placeholder="All statuses")
    view = rep
    if ds_filter:
        view = view[view["dataset"].isin(ds_filter)]
    if st_filter:
        view = view[view["status"].isin(st_filter)]
    ch.show_df(view)

with tab_lim:
    st.markdown("""
**What this project cannot tell you**

- **Vacant is not available.** Vacancy statistics are estimates (electricity-use based) or Census-night snapshots. They do not show habitability, ownership, or the cost of restoring a home.
- **Completions are a proxy.** CSO completions come from ESB Networks new connections; timing and counts can differ from actual completion.
- **Geography is uneven.** Planning permissions are available only by NUTS3 region (from 2018); homelessness only by Department region; property prices only as an index and only for a few areas; there are no county euro prices.
- **Periods differ.** Census figures are April 2016/2022; vacancy is Q4 2022-2024; rents run to Q4 2025; prices to September 2026; homelessness to September 2026; income to 2024. Comparisons across different periods are labelled.
- **Latest years are incomplete.** 2026 completions cover only Q1-Q3 and 2026 commencements only 10 months; partial years are flagged and not used for year-on-year change.
- **Missing data are not imputed.** Some RTB rent cells are unpublished (small samples); some commencement and planning series have gaps or lumpy spikes; three months of homelessness reports (Jun-Aug 2023) are absent from the open-data portal.
- **Social housing coverage is partial.** Only families with children identified as in need (CSO SCA10) and Census tenure are used; the full social housing waiting list and delivery data are not included.
- **Affordability measures are partial.** Measured rent-to-income uses tenants' own income; the per-person county comparison overstates burdens; no mortgage-affordability data are included.
- **The simulator is hypothetical.** It is arithmetic on assumptions, not a forecast, and ignores demand, prices, migration and delivery constraints.
- **Not a solution.** A dashboard cannot solve the housing crisis. It provides evidence to support better-informed decisions.
""")
