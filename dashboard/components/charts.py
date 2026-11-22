"""Plotly chart helpers with one consistent, accessible style (thin marks, hairline grid, direct end labels)."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.components import theme as T

CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"], "responsive": True}

# Colour follows the entity, never its rank or the filter state: key counties keep one colour everywhere.
FIXED_COUNTY_ORDER = ["Dublin", "Cork", "Galway", "Limerick", "Waterford", "Kildare", "Kerry", "Donegal"]


def entity_colors(names: Sequence[str], preferred: Sequence[str] = FIXED_COUNTY_ORDER) -> Dict[str, str]:
    """Stable colour per entity: preferred names keep their fixed slot; others take the next free slot (max 8)."""
    mapping: Dict[str, str] = {}
    free = list(range(len(T.CATEGORICAL)))
    for n in names:
        if n in preferred:
            idx = list(preferred).index(n)
            mapping[n] = T.CATEGORICAL[idx]
            if idx in free:
                free.remove(idx)
    for n in names:
        if n not in mapping and free:
            mapping[n] = T.CATEGORICAL[free.pop(0)]
    return mapping


def show(fig: go.Figure, key: Optional[str] = None) -> None:
    try:
        st.plotly_chart(fig, width="stretch", config=CONFIG, key=key)
    except TypeError:  # older Streamlit
        st.plotly_chart(fig, use_container_width=True, config=CONFIG, key=key)


def show_df(df: pd.DataFrame, **kw) -> None:
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)


def style(fig: go.Figure, title: str = "", height: int = 360, legend: bool = True, ytitle: str = "", xtitle: str = "",
          yfmt: Optional[str] = None, hover: str = "x unified") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15, color=T.INK)),
        height=height, margin=dict(l=8, r=12, t=46, b=8), paper_bgcolor=T.SURFACE, plot_bgcolor=T.SURFACE,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", size=12, color=T.INK_2),
        hovermode=hover, showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, x=0, font=dict(size=11), title_text=""),
        hoverlabel=dict(bgcolor="#ffffff", font_size=12),
    )
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", ticks="outside", tickcolor="#c3c2b7", title=xtitle, title_font=dict(size=11, color=T.MUTED),
                     automargin=True)
    fig.update_yaxes(gridcolor=T.GRID, gridwidth=1, zeroline=False, title=ytitle, title_font=dict(size=11, color=T.MUTED), tickformat=yfmt)
    return fig


def line(df: pd.DataFrame, x: str, y: str, color: Optional[str] = None, title: str = "", color_map: Optional[Dict[str, str]] = None,
         height: int = 360, ytitle: str = "", yfmt: Optional[str] = None, label_last: bool = True, hover_fmt: str = ",.1f",
         legend: Optional[bool] = None, dash_map: Optional[Dict[str, str]] = None) -> go.Figure:
    fig = go.Figure()
    groups = [(None, df)] if color is None else list(df.groupby(color, sort=False))
    cmap = color_map or {}
    for i, (name, d) in enumerate(groups):
        d = d.sort_values(x)
        col = cmap.get(name, T.CATEGORICAL[i % len(T.CATEGORICAL)]) if name is not None else T.CATEGORICAL[0]
        fig.add_trace(go.Scatter(
            x=d[x], y=d[y], mode="lines", name=str(name) if name is not None else y,
            line=dict(color=col, width=2, dash=(dash_map or {}).get(name, "solid")),
            hovertemplate=f"{name if name is not None else y}: %{{y:{hover_fmt}}}<extra></extra>"))
        if label_last and len(groups) <= 4 and len(d):
            last = d.dropna(subset=[y]).tail(1)
            if len(last):
                fig.add_trace(go.Scatter(x=last[x], y=last[y], mode="markers", marker=dict(color=col, size=8, line=dict(color=T.SURFACE, width=2)),
                                         showlegend=False, hoverinfo="skip"))
    multi = len(groups) >= 2
    return style(fig, title, height, legend=multi if legend is None else legend, ytitle=ytitle, yfmt=yfmt)


def bars(df: pd.DataFrame, x: str, y: str, title: str = "", color: Optional[str] = None, color_map: Optional[Dict[str, str]] = None,
         height: int = 360, ytitle: str = "", yfmt: Optional[str] = None, barmode: str = "group", hover_fmt: str = ",.0f",
         single_color: str = T.CATEGORICAL[0], opacity_col: Optional[str] = None) -> go.Figure:
    fig = go.Figure()
    if color is None:
        marker = dict(color=single_color, cornerradius=4) if True else {}
        op = None
        if opacity_col is not None:
            op = [0.45 if flag else 1.0 for flag in df[opacity_col]]
        fig.add_trace(go.Bar(x=df[x], y=df[y], marker=dict(color=single_color, opacity=op, cornerradius=4) if op else dict(color=single_color, cornerradius=4),
                             name=y, hovertemplate=f"%{{x}}: %{{y:{hover_fmt}}}<extra></extra>"))
        return style(fig, title, height, legend=False, ytitle=ytitle, yfmt=yfmt, hover="closest")
    cmap = color_map or {}
    for i, (name, d) in enumerate(df.groupby(color, sort=False)):
        fig.add_trace(go.Bar(x=d[x], y=d[y], name=str(name), marker=dict(color=cmap.get(name, T.CATEGORICAL[i % 8]), cornerradius=4,
                                                                      line=dict(color=T.SURFACE, width=2 if barmode == "stack" else 0)),
                             hovertemplate=f"{name}: %{{y:{hover_fmt}}}<extra></extra>"))
    fig.update_layout(barmode=barmode)
    return style(fig, title, height, legend=True, ytitle=ytitle, yfmt=yfmt, hover="x unified")


def hbar_ranked(df: pd.DataFrame, label: str, value: str, title: str = "", highlight: Iterable[str] = (), height: int = 640,
                value_fmt: str = ",.1f", unit_suffix: str = "") -> go.Figure:
    """Ranked horizontal bars; highlighted entities in the accent blue, the rest muted."""
    d = df.sort_values(value, ascending=True)
    hl = set(highlight)
    colors = [T.CATEGORICAL[0] if (not hl or n in hl) else "#b8c4d6" for n in d[label]]
    fig = go.Figure(go.Bar(x=d[value], y=d[label], orientation="h", marker=dict(color=colors, cornerradius=3),
                           text=[f"{v:{value_fmt}}{unit_suffix}" for v in d[value]], textposition="outside", textfont=dict(size=10, color=T.INK_2),
                           hovertemplate=f"%{{y}}: %{{x:{value_fmt}}}{unit_suffix}<extra></extra>", cliponaxis=False))
    fig = style(fig, title, height, legend=False, hover="closest")
    fig.update_yaxes(showgrid=False, gridcolor=None, tickfont=dict(size=11))
    fig.update_xaxes(showgrid=True, gridcolor=T.GRID, showline=False)
    return fig


def county_map(df: pd.DataFrame, geojson: dict, value: str, label: str, highlight: Sequence[str] = (), fmt: str = ",.1f",
               height: int = 560) -> go.Figure:
    """Choropleth of the 26 counties (OSi boundaries). Sequential one-hue blue; selected counties outlined."""
    fig = px.choropleth(df, geojson=geojson, locations="county", featureidkey="id", color=value, hover_name="county",
                        color_continuous_scale=T.SEQUENTIAL_BLUE, labels={value: label})
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=1.0, hovertemplate=f"<b>%{{location}}</b><br>{label}: %{{z:{fmt}}}<extra></extra>")
    if highlight:
        fig.add_trace(go.Choropleth(geojson=geojson, locations=list(highlight), z=[1] * len(highlight), featureidkey="id",
                                    colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
                                    marker_line_color=T.INK, marker_line_width=2.0, hoverinfo="skip"))
    # explicit Mercator view over the island of Ireland (fitbounds is unreliable inside resizable containers)
    fig.update_geos(projection_type="mercator", lonaxis_range=[-10.9, -5.8], lataxis_range=[51.25, 55.55], visible=False, bgcolor=T.SURFACE,
                    showframe=False, showcountries=False, showcoastlines=False, showland=False, showocean=False, showlakes=False)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor=T.SURFACE,
                      coloraxis_colorbar=dict(title=dict(text=label, font=dict(size=11)), thickness=12, len=0.7, tickfont=dict(size=10)),
                      font=dict(family="system-ui, sans-serif", color=T.INK_2))
    return fig


def scatter(df: pd.DataFrame, x: str, y: str, label: str, title: str = "", xtitle: str = "", ytitle: str = "", height: int = 420,
            highlight: Sequence[str] = ()) -> go.Figure:
    hl = set(highlight)
    colors = [T.CATEGORICAL[0] if (not hl or n in hl) else "#b8c4d6" for n in df[label]]
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="markers+text", text=[n if (not hl or n in hl) else "" for n in df[label]],
                               textposition="top center", textfont=dict(size=10, color=T.INK_2),
                               marker=dict(size=10, color=colors, line=dict(color=T.SURFACE, width=2)),
                               hovertemplate="<b>%{customdata}</b><br>" + f"{xtitle or x}: %{{x:,.1f}}<br>{ytitle or y}: %{{y:,.1f}}<extra></extra>",
                               customdata=df[label]))
    fig = style(fig, title, height, legend=False, xtitle=xtitle, ytitle=ytitle, hover="closest")
    fig.update_xaxes(showgrid=True, gridcolor=T.GRID)
    return fig


def add_annotation_vline(fig: go.Figure, x, text: str) -> go.Figure:
    fig.add_vline(x=x, line=dict(color=T.MUTED, width=1, dash="dot"))
    fig.add_annotation(x=x, y=1.0, yref="paper", text=text, showarrow=False, font=dict(size=10, color=T.INK_2), xanchor="left", yanchor="top")
    return fig
