"""Visual identity: palette, CSS, page header, KPI cards, badges, notes.

Palette = the validated categorical set from the data-viz method (fixed order, max 8), a one-hue blue
sequential ramp for magnitude, a blue<->red diverging pair, and reserved status colours.
"""
from __future__ import annotations

import html
from typing import Optional

import streamlit as st

# categorical slots 1-8, assigned in this fixed order and never cycled
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#eda100", "#e87ba4", "#008300", "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = ["#2a78d6", "#f0efec", "#e34948"]
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
NAVY = "#0d366b"
ACCENT = "#1baf7a"
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

KIND_LABEL = {"published": "Published statistic", "derived": "Derived indicator", "estimate": "Estimate / proxy", "hypothetical": "Hypothetical"}
KIND_COLOR = {"published": "#184f95", "derived": "#6250d6", "estimate": "#9a6700", "hypothetical": "#b42318"}

CSS = f"""
<style>
html, body, [class*="css"] {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1280px; }}
.hs-brand {{ font-size: .78rem; letter-spacing: .09em; text-transform: uppercase; color: {INK_2}; margin-bottom: .15rem; }}
.hs-brand b {{ color: {NAVY}; }}
.hs-title {{ font-size: 2rem; font-weight: 700; color: {INK}; line-height: 1.15; margin: 0 0 .25rem 0; }}
.hs-sub {{ color: {INK_2}; font-size: 1.02rem; margin-bottom: 1rem; max-width: 60rem; }}
.hs-rule {{ height: 3px; width: 64px; background: {ACCENT}; border-radius: 2px; margin: .15rem 0 1.1rem 0; }}
.hs-card {{ background: {SURFACE}; border: 1px solid rgba(11,11,11,.10); border-radius: 10px; padding: .85rem 1rem .8rem 1rem; height: 100%; }}
.hs-card .lbl {{ font-size: .78rem; color: {INK_2}; font-weight: 600; letter-spacing: .02em; }}
.hs-card .val {{ font-size: 1.85rem; font-weight: 700; color: {INK}; line-height: 1.2; margin-top: .1rem; }}
.hs-card .dlt {{ font-size: .82rem; margin-top: .1rem; color: {INK_2}; }}
.hs-card .per {{ font-size: .74rem; color: {MUTED}; margin-top: .25rem; }}
.hs-badge {{ display: inline-block; font-size: .66rem; font-weight: 600; padding: 1px 7px; border-radius: 999px; color: #fff; margin-left: .4rem; vertical-align: middle; white-space: nowrap; }}
.hs-card .per .hs-badge {{ margin-left: 0; margin-top: .3rem; display: block; width: fit-content; }}
.hs-note {{ border-left: 4px solid {ACCENT}; background: #fff; padding: .6rem .9rem; border-radius: 4px; color: {INK_2}; font-size: .9rem; margin: .4rem 0 1rem 0; }}
.hs-warn {{ border-left: 4px solid {STATUS['warning']}; background: #fffaf0; padding: .6rem .9rem; border-radius: 4px; color: #5c4400; font-size: .92rem; margin: .4rem 0 1rem 0; }}
.hs-hypo {{ border: 2px dashed #b42318; background: #fff5f4; padding: .7rem 1rem; border-radius: 8px; color: #7a1b13; font-weight: 600; margin: .3rem 0 1rem 0; }}
.hs-insight {{ background: {SURFACE}; border: 1px solid rgba(11,11,11,.10); border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: .9rem; }}
.hs-insight h4 {{ margin: 0 0 .5rem 0; font-size: 1.02rem; color: {INK}; line-height: 1.4; }}
.hs-insight .meta {{ font-size: .78rem; color: {MUTED}; margin-bottom: .5rem; }}
.hs-insight .row {{ font-size: .9rem; color: {INK_2}; margin: .25rem 0; }}
.hs-insight .row b {{ color: {INK}; }}
.hs-cap {{ font-size: .78rem; color: {MUTED}; margin-top: -.3rem; margin-bottom: .8rem; }}
[data-testid="stSidebar"] {{ background: #ffffff; border-right: 1px solid rgba(11,11,11,.08); }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    inject_css()
    st.markdown('<div class="hs-brand"><b>HomeScope Ireland</b> · Housing Crisis Intelligence Platform</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hs-title">{html.escape(title)}</div><div class="hs-rule"></div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="hs-sub">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def badge(kind: str) -> str:
    return f'<span class="hs-badge" style="background:{KIND_COLOR.get(kind, MUTED)}">{html.escape(KIND_LABEL.get(kind, kind))}</span>'


def kpi_card(label: str, value: str, delta: str = "", period: str = "", kind: str = "published", delta_good: Optional[bool] = None) -> None:
    """KPI card. Colour of the delta is only used when the direction has an unambiguous 'good/bad' reading."""
    colour = INK_2 if delta_good is None else (STATUS["good"] if delta_good else STATUS["critical"])
    arrow = ""
    st.markdown(
        f'<div class="hs-card"><div class="lbl">{html.escape(label)}</div>'
        f'<div class="val">{html.escape(value)}</div>'
        f'<div class="dlt" style="color:{colour}">{arrow}{html.escape(delta)}</div>'
        f'<div class="per">{html.escape(period)}{badge(kind)}</div></div>', unsafe_allow_html=True)


def note(text: str, kind: str = "info") -> None:
    css = {"info": "hs-note", "warn": "hs-warn", "hypo": "hs-hypo"}[kind]
    st.markdown(f'<div class="{css}">{text}</div>', unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<div class="hs-cap">{html.escape(text)}</div>', unsafe_allow_html=True)


def sidebar_brand(backend: str) -> None:
    with st.sidebar:
        st.markdown(f'<div style="font-weight:700;color:{NAVY};font-size:1.15rem">HomeScope Ireland</div>'
                    f'<div style="color:{INK_2};font-size:.8rem;margin-bottom:.6rem">Housing Crisis Intelligence Platform</div>',
                    unsafe_allow_html=True)
        st.caption(f"Data backend: **{'PostgreSQL' if backend == 'postgres' else 'processed CSV files'}**")
