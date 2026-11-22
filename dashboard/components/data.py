"""Cached data access for the dashboard (PostgreSQL when reachable, processed CSVs otherwise)."""
from __future__ import annotations

import json
from typing import Dict, Tuple

import pandas as pd
import streamlit as st

from src.analysis import insights as insights_mod
from src.indicators import calculations as calc
from src.indicators import scorecard
from src.database import repository
from src.utils.paths import PROCESSED_DIR


@st.cache_resource(show_spinner="Loading housing data...")
def get_tables() -> Tuple[Dict[str, pd.DataFrame], str]:
    """(tables, backend). Treated as read-only by every page."""
    return repository.load_tables()


@st.cache_data(show_spinner=False)
def kpis() -> dict:
    return calc.national_kpis(get_tables()[0])


@st.cache_data(show_spinner=False)
def scorecard_table() -> pd.DataFrame:
    return scorecard.county_scorecard(get_tables()[0])


@st.cache_data(show_spinner=False)
def pressure_table() -> pd.DataFrame:
    return calc.housing_pressure_table(get_tables()[0])


@st.cache_data(show_spinner=False)
def insights_table() -> pd.DataFrame:
    return insights_mod.insights_frame(get_tables()[0])


@st.cache_resource(show_spinner=False)
def counties_geojson() -> dict:
    return json.loads((PROCESSED_DIR / "counties.geojson").read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def quality_report() -> pd.DataFrame:
    return pd.DataFrame(json.loads((PROCESSED_DIR / "data_quality_report.json").read_text(encoding="utf-8")))


def county_list() -> list[str]:
    return sorted(get_tables()[0]["dim_county"]["county"])
