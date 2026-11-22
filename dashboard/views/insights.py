"""Page 6 - Insights and Recommendations (automatically generated from the data)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import html  # noqa: E402

import streamlit as st  # noqa: E402

from dashboard.components import data as D  # noqa: E402
from dashboard.components import theme as T  # noqa: E402
from src.indicators import INDICATORS  # noqa: E402

T.page_header("Insights and Recommendations",
              "Findings generated automatically from the latest data. Each one says what the data show, where and when, why it matters, "
              "and a possible intervention or area for further investigation.")
tables, backend = D.get_tables()
T.sidebar_brand(backend)
ins = D.insights_table()

T.note("<b>How these are produced.</b> Every sentence below is computed from the loaded datasets at run time - nothing is hard-coded. The data identify "
       "<i>patterns</i>; they do not prove causes. 'Next step' suggestions are prompts for investigation, not policy prescriptions.")

# ------------------------------------------------------------------------------ filters
c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
with c1:
    themes = st.multiselect("Theme", sorted(ins["theme"].unique()), default=[], key="in_theme", placeholder="All themes")
with c2:
    county = st.selectbox("County", ["All counties"] + D.county_list(), key="in_county")
with c3:
    ymin, ymax = int(ins["year"].min()), int(ins["year"].max())
    yr = st.slider("Reference year", ymin, ymax, (ymin, ymax), key="in_years")
with c4:
    names = {i.name: i.id for i in INDICATORS.values() if i.id in set(ins["indicator"])}
    chosen = st.multiselect("Indicator", sorted(names), default=[], key="in_indicator", placeholder="All indicators")
kinds = st.multiselect("Evidence type", ["published", "derived", "estimate"], default=["published", "derived", "estimate"], key="in_kind")

view = ins.copy()
if themes:
    view = view[view["theme"].isin(themes)]
if county != "All counties":
    view = view[view["counties"].map(lambda cs: county in cs)]
view = view[view["year"].between(*yr)]
if chosen:
    view = view[view["indicator"].isin([names[n] for n in chosen])]
view = view[view["kind"].isin(kinds)]

st.markdown(f"**{len(view)} of {len(ins)} insights shown**")
if view.empty:
    T.note("No insight matches these filters. Widen the county, year or indicator selection.", "warn")

for r in view.itertuples():
    ind_name = INDICATORS[r.indicator].name if r.indicator in INDICATORS else r.indicator
    st.markdown(
        f'<div class="hs-insight"><div class="meta">{html.escape(r.theme)} · {html.escape(ind_name)} {T.badge(r.kind)}</div>'
        f'<h4>{html.escape(r.headline)}</h4>'
        f'<div class="row"><b>Where / when:</b> {html.escape(r.location)} · {html.escape(r.period)}</div>'
        f'<div class="row"><b>Why it matters:</b> {html.escape(r.why_it_matters)}</div>'
        f'<div class="row"><b>Possible intervention / further investigation:</b> {html.escape(r.next_step)}</div>'
        f'<div class="row" style="color:{T.MUTED};font-size:.78rem">Source: {html.escape(r.sources)}</div></div>', unsafe_allow_html=True)

with st.expander("Table view of all insights"):
    st.dataframe(view[["theme", "headline", "location", "period", "why_it_matters", "next_step", "sources", "kind"]], hide_index=True)
