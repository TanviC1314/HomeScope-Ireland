"""Documented registry of every indicator used in HomeScope Ireland.

For each indicator: what it measures, the exact calculation, the source data, the reference period,
the assumptions made and the limitations.  Rendered on the dashboard "Data & Methodology" page and
exported to ``docs/INDICATORS.md`` (``python -m src.indicators.registry``).

Indicator ``kind``:
  published  - a statistic published as-is by the source (possibly summed across areas)
  derived    - calculated by HomeScope from published statistics (formula shown)
  estimate   - a modelled/proxy value that is not directly measured
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List

import pandas as pd

from src.utils.paths import DOCS_DIR


@dataclass(frozen=True)
class Indicator:
    id: str
    name: str
    category: str
    kind: str
    calculation: str
    sources: str
    reference_period: str
    assumptions: str
    limitations: str


_LIST: List[Indicator] = [
    Indicator("total_completions", "Total housing completions", "Supply", "published",
              "Sum of quarterly new dwelling completions over local authorities (and quarters) in scope.",
              "CSO NDQ06 (New Dwelling Completions)", "Quarterly 2011Q1 to latest quarter; the latest calendar year is partial.",
              "Local authorities are mapped to the 26 counties (Dublin = 4 LAs, Cork = 2, Galway = 2). Partial years are flagged and never compared with full years.",
              "CSO completions are based on ESB Networks new connections, a proxy for completed dwellings; timing can lag actual completion."),
    Indicator("supply_growth_yoy", "Annual housing supply growth", "Supply", "derived",
              "100 x (completions in year t / completions in year t-1 - 1), only between two full calendar years.",
              "CSO NDQ06", "Full calendar years 2012 to latest full year.", "None beyond those of total completions.",
              "Year-on-year changes are volatile and sensitive to the base year; they say nothing about the cumulative shortfall."),
    Indicator("completions_per_1000", "Completions per 1,000 residents", "Supply", "derived",
              "Average annual completions over the last three full years / Census 2022 population x 1,000.",
              "CSO NDQ06; CSO F1003 (Census 2022 population)", "Completions: last three full calendar years. Population: Census April 2022.",
              "Population is held at its 2022 Census level for all years.",
              "Uses a 2022 denominator for later years, so counties that have grown since 2022 are slightly flattered. "
              "Completions say nothing about local need or the quality of what was built."),
    Indicator("population_growth", "Population growth (county, Census)", "Demand", "published",
              "100 x (Census 2022 population / Census 2016 population - 1).", "CSO F1003 (Census population by county)",
              "Census April 2016 to April 2022.", "No additional assumptions: published figures are used as-is.", "Census-to-Census only: no annual county population estimates are used."),
    Indicator("population_growth_national", "Population growth (national, annual)", "Demand", "published",
              "100 x (population in April t / population in April t-1 - 1).", "CSO PEA01, PEA15",
              "April 1950 to April 2026 (latest years are provisional estimates).", "No additional assumptions: published figures are used as-is.", "Estimates are revised when new Census data become available."),
    Indicator("household_growth", "Household growth (county, Census)", "Demand", "published",
              "100 x (private households 2022 / private households 2016 - 1).", "CSO F2001", "Census April 2016 to April 2022.",
              "No additional assumptions: published figures are used as-is.", "Households form from existing stock and from new homes; household growth reflects supply as well as demand."),
    Indicator("stock_growth", "Housing stock growth (county, Census)", "Supply", "published",
              "100 x (Census housing stock 2022 / 2016 - 1), summed over the Census areas in each county.", "CSO F2020",
              "Census April 2016 to April 2022.", "Census areas are aggregated to counties by summing.",
              "Census stock includes vacant dwellings and holiday homes."),
    Indicator("household_minus_stock_growth", "Household growth minus housing-stock growth", "Pressure", "derived",
              "household growth % - housing stock growth %, in percentage points (positive = households grew faster than stock).",
              "CSO F2001, F2020", "Census 2016 to 2022.", "Both series measured at the same two Census dates.",
              "A positive gap can be absorbed by lower vacancy or larger households; it signals pressure, not an exact shortfall."),
    Indicator("rent_level_change", "Rental price level and change", "Affordability", "published",
              "RTB standardised average monthly rent for new tenancies (all bedrooms, all property types); change = latest / base - 1.",
              "CSO RIQ02 (RTB Average Monthly Rent Report)", "Quarterly 2007Q4 to 2025Q4 (latest published).",
              "County rows are used for county analysis; city rows are shown separately.",
              "New-tenancy rents differ from rents paid by existing tenants; averages hide composition effects (property mix, bedrooms)."),
    Indicator("national_rent_proxy", "National average rent (derived)", "Affordability", "estimate",
              "Weighted mean of the 26 county average rents, weighted by Census 2022 private-rented households.",
              "CSO RIQ02, F2004", "Quarterly 2007Q4 to 2025Q4.", "Fixed 2022 weights apply to all periods.",
              "The RTB/CSO table does not publish a national average; this is a transparent estimate, not an official figure."),
    Indicator("property_price_change", "Residential property price index change", "Affordability", "published",
              "CSO RPPI (base January 2015 = 100); 12-month % change as published; change vs the pre-crisis peak = latest / peak - 1.",
              "CSO HPM09", "Monthly 2005 January to latest month (2026 September).", "No additional assumptions: published figures are used as-is.",
              "An index, not a euro price. County-level prices are not published by the CSO; regional series cover houses only."),
    Indicator("rent_to_income_measured", "Rent as % of disposable income (measured)", "Affordability", "published",
              "Median individual RTB tenant rent as % of that tenant's disposable income, by local authority; county value = mean of "
              "its local authorities weighted by dwelling stock.", "CSO TRS38 (CSO analysis of RTB-linked income data)", "Rental year 2024.",
              "Dwelling stock (ESB connections, Q4 2024) is used as a proxy weight for the number of tenants in counties with several LAs.",
              "Individual tenant income may exclude other household members' income; one reference year only."),
    Indicator("rent_vs_income_per_person", "Annual rent vs disposable income per person (relative)", "Affordability", "derived",
              "12 x average monthly rent (latest quarter) / disposable income per person (latest year) x 100.",
              "CSO RIQ02, RAA02", "Rent: latest quarter. Income: latest year published (2024).",
              "Per-person income is the only county income measure available.",
              "Per-person income is lower than household income, so the level overstates the burden. Use only to compare counties, not as an absolute threshold."),
    Indicator("vacancy_rate_esb", "Vacancy rate (estimated)", "Vacancy", "published",
              "Vacant dwellings / dwelling stock x 100, summed from local-authority counts (not an average of rates).",
              "CSO VAC14 (ESB-based estimate of vacant dwellings)", "Q4 2022, Q4 2023, Q4 2024.",
              "A dwelling is classed vacant by the CSO using electricity consumption patterns.",
              "Vacant does not mean habitable, available or suitable. Some vacancy is normal (sale, probate, turnover)."),
    Indicator("long_term_vacancy", "Long-term vacancy share", "Vacancy", "published",
              "Dwellings vacant in each of six consecutive years / all vacant dwellings x 100.", "CSO VAC23, VAC14", "Q4 2024.",
              "No additional assumptions: published figures are used as-is.", "Persistently vacant dwellings are the group where reuse is most plausible but they are not necessarily habitable."),
    Indicator("census_vacancy_rate", "Census vacancy rate", "Vacancy", "derived",
              "Vacant house/apartment / total housing stock x 100 (Census night).", "CSO F2020", "Census April 2022.",
              "Holiday homes are reported separately and are not counted as vacant.", "Census night snapshot; reasons are self-reported."),
    Indicator("vacancy_reason_groups", "Reuse-pathway grouping of Census vacancy reasons", "Vacancy", "estimate",
              "Census 2022 reasons grouped: Needs work/probate (Renovation, Deceased), In market transition (For sale, Rental, New build), "
              "Family or care circumstances (With relatives, Nursing home/hospital), Other.", "CSO F2014", "Census April 2022.",
              "The grouping is an analytical judgement made by HomeScope for screening purposes.",
              "Does not establish that any dwelling is habitable, available or economical to renovate."),
    Indicator("planning_to_completion", "Planning permissions vs completions", "Supply", "derived",
              "Completions in year Y / units granted planning permission in year Y-lag (NUTS3 region); lag selectable 0-3 years.",
              "CSO BHA13, NDQ06", "Annual 2015 to 2025.", "Counties aggregated to NUTS3 regions using the CSO regional grouping (CIRGDP07).",
              "A comparison ratio, not a conversion rate: permissions can lapse, be re-applied for, or be extended; completions also include "
              "dwellings permitted earlier or outside this series."),
    Indicator("commencements", "Construction commencements", "Supply", "published",
              "Sum of residential units in commencement notices.", "CSO HSM13", "Monthly March 2014 to October 2026.",
              "Annual totals use calendar years; partial years are flagged.", "Commencement notices precede completion by many months; not all commenced units complete."),
    Indicator("social_need_per_1000", "Families with children in need of social housing", "Social housing", "derived",
              "Households with children identified as in need of social housing (latest year) / Census 2022 households x 1,000.",
              "CSO SCA10, F2001", "Latest year in SCA10 (county breakdown); households Census 2022.",
              "No additional assumptions: published figures are used as-is.", "Covers only households with children, so it understates total need; the numerator year and denominator year differ."),
    Indicator("social_rented_share", "Social rented share of households", "Social housing", "derived",
              "(Households renting from a local authority + voluntary body) / all households x 100.", "CSO F2004", "Census April 2022.",
              "No additional assumptions: published figures are used as-is.", "Census snapshot of the existing social stock - not a measure of need or recent delivery."),
    Indicator("homelessness", "People in emergency accommodation", "Homelessness", "published",
              "Adults plus dependants in emergency accommodation (Dept. of Housing monthly report); per 10,000 residents using Census 2022 population.",
              "Dept. of Housing, Local Government and Heritage monthly Homelessness Reports (data.gov.ie)", "Monthly, January 2019 to September 2026 (some months absent).",
              "Counties are grouped into the nine Department regions for per-capita rates.",
              "Counts people in emergency accommodation in the reference week only; excludes hidden homelessness and some supported accommodation."),
    Indicator("pressure_flags", "County housing-pressure flags", "Pressure", "derived",
              "Count (0-6) of indicators in which a county is in the most-pressured quartile of the 26 counties: rent level, rent growth since 2019, "
              "rent-to-income, completions per 1,000 (lowest quartile), household-minus-stock growth, social housing need per 1,000.",
              "Rents (RIQ02), TRS38, NDQ06, F1003, F2001, F2020, SCA10", "Mixed: see each component indicator.",
              "Equal treatment of all six indicators; quartile thresholds computed across the 26 counties. No weights, no composite score.",
              "Relative, not absolute: a county can be flagged even when conditions are good by international standards. Quartile boundaries are arbitrary by nature."),
    Indicator("supply_demand_gap", "Housing supply-demand gap (national)", "Demand", "estimate",
              "Total annual household demand - new dwelling completions. Demand = (population change / avg household size) + "
              "replacement demand (0.4 % of housing stock). Three scenario bands (low / central / high) vary net migration at "
              "50 % / 100 % / 150 % of the observed PEA15 figure. Positive gap = shortfall; negative = surplus.",
              "CSO PEA15 (national population and migration), CSO NDQ06 (completions), CSO F2001 (households), CSO F2020 (housing stock)",
              "Annual 2018 to latest full year (2017 used as population base; partial years flagged).",
              "Avg household size interpolated linearly between Census 2016 (2.75) and 2022 (2.74). Replacement rate fixed at 0.4 % of "
              "Census housing stock (European estimate). Migration scenarios are analytical illustrations, not forecasts.",
              "Population-based demand does not capture housing quality, affordability or location mismatch. Completions are ESB-based "
              "proxies. Scenario bands represent migration variation only; natural increase is held at the observed level."),
    Indicator("supply_demand_gap_county", "Housing supply-demand gap (county)", "Demand", "estimate",
              "County-level gap using PEA08 annual population estimates. Demand = (county population change / county avg household size) "
              "+ replacement demand (0.4 % of Census 2022 housing stock). Gap = demand - completions.",
              "CSO PEA08 (county population estimates), CSO NDQ06 (completions), CSO F2001, F2020",
              "Annual 2018 to latest available year in PEA08.",
              "County household size interpolated between Census years. Replacement stock fixed at Census 2022 level per county. "
              "Single central scenario (observed population change).",
              "Annual county estimates are rounded to the nearest hundred persons (CSO PEA08 methodology), introducing rounding uncertainty "
              "in the household-demand calculation. County completions are aggregated from local authorities; small counties can show large "
              "swings from individual large developments. No scenario band at county level."),
    Indicator("affordability_pressure_index", "Housing Affordability Pressure Index", "Affordability", "derived",
              "Four components per county: (1) median rent as % of tenant disposable income (TRS38), (2) annual average rent as % of disposable income per person, "
              "(3) rise in annual rent since Q4 2019 as % of income per person = 100 x 12 x (rent_latest - rent_Q4_2019) / income per person, "
              "(4) % change in the CSO regional house-price index (houses) since Dec 2019. Each is min-max standardised across the 26 counties to 0-100 "
              "(0 = lowest pressure, 100 = highest). Index = 0.35 x (1) + 0.25 x (2) + 0.20 x (3) + 0.20 x (4), a 0-100 relative score; rank 1 = least affordable.",
              "CSO TRS38, RIQ02 (RTB), RAA02, HPM09", "Rents: Q4 2019 to latest quarter; income: latest year; burden: 2024; prices: Dec 2019 to latest month.",
              "Weights are a documented judgement, not estimated from data: the directly measured tenant rent burden gets the largest weight, the two rent-vs-income "
              "lenses 0.45 in total, prices 0.20. The dashboard lets the user change them. Euro rent rise (not % growth) is used so that counties that started with low rents "
              "do not score high merely from a low base.",
              "Relative ranking only (not an absolute affordability threshold, not a forecast). No county price levels exist, so prices enter as REGIONAL growth shared by all "
              "counties in a region. Per-person income overstates burdens. Component weights drive rankings: see the sensitivity indicator. Mortgage affordability is not covered."),
    Indicator("affordability_index_sensitivity", "Affordability index sensitivity analysis", "Affordability", "estimate",
              "Rank stability of the index under (a) six named weighting scenarios, (b) dropping each component in turn (weights renormalised), (c) three standardisation methods "
              "(min-max, z-score, percentile rank), (d) 5,000 random weight sets: flat Dirichlet (any weighting equally likely) and Dirichlet concentrated around the baseline weights "
              "(concentration 50). Reported as rank ranges (5th-95th percentile), share of draws in the top 5, and Spearman rank correlation with the baseline.",
              "CSO TRS38, RIQ02 (RTB), RAA02, HPM09 (through the index components)", "Same as the index.",
              "Random weights are uniform over the weight simplex (flat) or centred on the baseline (local); they represent uncertainty about how to weight, not statistical sampling error. "
              "Fixed seed (42) so results are reproducible.",
              "Shows how much the ranking depends on analyst choices; it does not validate the index against any external measure of affordability. "
              "Components are correlated and some (regional prices) have only eight distinct values."),
]

INDICATORS: Dict[str, Indicator] = {i.id: i for i in _LIST}


def indicator_table() -> pd.DataFrame:
    return pd.DataFrame([asdict(i) for i in _LIST])


def to_markdown() -> str:
    lines = ["# Indicator definitions", "",
             "Every indicator on the dashboard, with its calculation, sources, reference period, assumptions and limitations. "
             "`published` = as published by the source; `derived` = calculated by HomeScope from published figures; "
             "`estimate` = a proxy or modelled value (not directly measured).", ""]
    for cat in dict.fromkeys(i.category for i in _LIST):
        lines += [f"## {cat}", ""]
        for i in (x for x in _LIST if x.category == cat):
            lines += [f"### {i.name}  \n`{i.id}` · **{i.kind}**", "",
                      f"- **Calculation:** {i.calculation}", f"- **Source data:** {i.sources}",
                      f"- **Reference period:** {i.reference_period}", f"- **Assumptions:** {i.assumptions}",
                      f"- **Limitations:** {i.limitations}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "INDICATORS.md").write_text(to_markdown(), encoding="utf-8")
    print("wrote docs/INDICATORS.md")
