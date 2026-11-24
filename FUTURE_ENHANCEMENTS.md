# Future enhancements (Phase 2 backlog)

Phase 1 (this repository's initial version) is complete and usable on its own. The items below are the
planned follow-up work. Each one is intended to be a separate, tested, documented commit/PR.

| Day | Feature | Goal | Definition of done |
|---|---|---|---|
| 2 | **Advanced Housing Affordability Index** (**done** - see `docs/AFFORDABILITY_INDEX.md`) | A transparent county-level affordability measure combining rental costs, property prices and income. | Documented formula with explicit weights/standardisation, sensitivity analysis, ranked county table, new dashboard tab, unit tests. |
| 3 | **Housing Supply and Demand Gap** | Compare completions with population and household growth to find regions where supply may not be keeping pace. | Household-based demand model (household size, migration assumptions), gap by county/NUTS3, uncertainty bands, tests. |
| 4 | **Housing Price Forecasting** | Experiment with time-series forecasting for rents and property prices. | Baselines (naive, seasonal naive) vs ARIMA/ETS/gradient boosting, walk-forward back-testing (MAE/MAPE), prediction intervals, clear limitations. |
| 5 | **Vacancy Reuse Opportunity Analysis** | Identify areas with higher vacancy and investigate opportunities to bring *suitable* homes back into use. | Separation of vacant vs habitable vs available stock, use of long-term vacancy and vacancy reasons, per-area opportunity ranges (not point promises). |
| 6 | **Advanced Ireland Housing Map** | Detailed county-level geographical analysis. | Switchable map layers (supply, affordability, vacancy), local-authority/LEA drill-down where data allows, linked county comparison panel. |
| 7 | **Automated Analytics Pipeline and Reporting** | Scheduled refreshes and automated QA. | Scheduled data updates (GitHub Actions/cron), automated data-quality checks that fail loudly, structured logging, monthly PDF/HTML housing report, final documentation polish. |

## Additional ideas (not yet scheduled)

* Local Electoral Area level supply and rent-to-income analysis (CSO tables NDQ09 / TRS39).
* Dwelling-type mix and BER (energy rating) of vacant stock.
* Social housing delivery data from the Department of Housing once a machine-readable, up-to-date series is available.
* Euro-denominated county property prices (Property Price Register) with transaction volumes.
* CI workflow running `pytest` and linting on every push.
