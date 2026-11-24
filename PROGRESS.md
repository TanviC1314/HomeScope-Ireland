# Progress log

## Phase 1 - complete working project (Day 1)

| Module | Status | Evidence |
|---|---|---|
| A. Data collection | Done | `src/data_collection` - registry of 19 datasets + 90 monthly reports, retries, graceful failure with manual instructions, provenance manifest with SHA-256, PxStat subset query for the oversized rents table |
| B. Cleaning | Done | `src/data_cleaning` - 87 recorded checks, 0 warnings; reconciliation to published totals; raw files untouched |
| C. PostgreSQL | Done | `database/schema.sql`, generated `seed_data.sql`, loader (full refresh), Docker Compose |
| D. SQL analytics | Done | 20 documented queries, all executed; results snapshot in `docs/SQL_RESULTS.md` |
| E. Indicators | Done | `src/indicators` - 23 documented indicators; no arbitrary composite scores |
| F. Dashboard | Done | 8 pages, interactive filters, OSi county map, KPI cards, insights |
| G. Scenario simulator | Done | Hypothetical, documented assumptions, renovation capped by an assumed suitable pool |
| H. Testing | Done | 113 pytest tests: loading, cleaning, KPIs vs raw source files, scenarios, PostgreSQL, dashboard (AppTest) |
| J. Phase 2, Day 2 - Affordability Index | Done | `src/indicators/affordability_index.py`: 4-component county index, adjustable weights, sensitivity analysis (6 scenarios, drop-one, 3 standardisations, 5,000 random weight sets), dashboard page, `docs/AFFORDABILITY_INDEX.md`, 27 new tests (140 total) |
| I. Documentation | Done | README, DATA_CATALOGUE, DATA_QUALITY, INDICATORS, SQL_RESULTS, screenshots |

## Decisions and findings worth knowing

* **Rents:** the CSO table `RIQ02` is too large for the API's single-download limit (HTTP 403), so county and city locations are requested through a PxStat subset query. Values are stored as served.
* **No national rent series is published** by the CSO/RTB table, so the national line is a documented estimate (county rents weighted by private-rented households, Census 2022).
* **Homelessness parsing bug caught and fixed:** early files contain values like `4,258`; they had been turned into missing values, understating January 2019 as 3,023 (true: 9,987). A month-on-month anomaly check and a regression test now guard this.
* **Boundaries:** OSi GeoJSON arrives in Irish Transverse Mercator; converted to WGS84 with a tested projection function (known-point test).
* **Planning data:** the regional split exists only from 2018; the national series is built from "All houses" + "Apartments" so it is continuous.
* **Commencements** contain exceptional spike months (e.g. 18,700 units in April 2024); the dashboard and insights warn against reading single years as trends.
* **Dashboard folder** is `dashboard/views/` rather than `pages/` because Streamlit auto-discovers `pages/` and bypasses `st.navigation`.
* **Port 5433** is used for the project database because 5432 was already in use on the development machine.
* **Not included (documented):** Central Bank mortgage data, the full social-housing waiting list and recent delivery, county euro property prices, Local Electoral Area analysis.

## Environment notes

* Developed on Windows 11, Python 3.11, Docker Desktop, PostgreSQL 16 (container), pandas 3.x, Streamlit 1.67.
* `gh` (GitHub CLI) is not installed on the development machine; Git itself is.

## Phase 2

See [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md).
