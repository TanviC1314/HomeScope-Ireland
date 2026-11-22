"""HomeScope Ireland - Housing Crisis Intelligence Platform (Streamlit entry point).

Run from the repository root:   streamlit run dashboard/app.py

Page scripts live in ``dashboard/views/``. The folder is deliberately not called ``pages/``: Streamlit
auto-discovers a ``pages/`` directory and would bypass the grouped navigation defined below.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="HomeScope Ireland | Housing Crisis Intelligence Platform", page_icon="🏠", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = {
    "Overview": [
        st.Page("views/national_overview.py", title="National Housing Overview", icon="🇮🇪", default=True),
        st.Page("views/county_comparison.py", title="County Comparison", icon="🗺️"),
    ],
    "Analysis": [
        st.Page("views/affordability.py", title="Housing Affordability", icon="💶"),
        st.Page("views/supply.py", title="Housing Supply", icon="🏗️"),
        st.Page("views/vacancy_needs.py", title="Vacancy and Housing Needs", icon="🔑"),
    ],
    "Decision support": [
        st.Page("views/insights.py", title="Insights and Recommendations", icon="💡"),
        st.Page("views/simulator.py", title="Policy Scenario Simulator", icon="🧪"),
    ],
    "About": [
        st.Page("views/methodology.py", title="Data and Methodology", icon="📚"),
    ],
}

st.navigation(PAGES).run()
