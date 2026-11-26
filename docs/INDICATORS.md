# Indicator definitions

Every indicator on the dashboard, with its calculation, sources, reference period, assumptions and limitations. `published` = as published by the source; `derived` = calculated by HomeScope from published figures; `estimate` = a proxy or modelled value (not directly measured).

## Supply

### Total housing completions  
`total_completions` · **published**

- **Calculation:** Sum of quarterly new dwelling completions over local authorities (and quarters) in scope.
- **Source data:** CSO NDQ06 (New Dwelling Completions)
- **Reference period:** Quarterly 2011Q1 to latest quarter; the latest calendar year is partial.
- **Assumptions:** Local authorities are mapped to the 26 counties (Dublin = 4 LAs, Cork = 2, Galway = 2). Partial years are flagged and never compared with full years.
- **Limitations:** CSO completions are based on ESB Networks new connections, a proxy for completed dwellings; timing can lag actual completion.

### Annual housing supply growth  
`supply_growth_yoy` · **derived**

- **Calculation:** 100 x (completions in year t / completions in year t-1 - 1), only between two full calendar years.
- **Source data:** CSO NDQ06
- **Reference period:** Full calendar years 2012 to latest full year.
- **Assumptions:** None beyond those of total completions.
- **Limitations:** Year-on-year changes are volatile and sensitive to the base year; they say nothing about the cumulative shortfall.

### Completions per 1,000 residents  
`completions_per_1000` · **derived**

- **Calculation:** Average annual completions over the last three full years / Census 2022 population x 1,000.
- **Source data:** CSO NDQ06; CSO F1003 (Census 2022 population)
- **Reference period:** Completions: last three full calendar years. Population: Census April 2022.
- **Assumptions:** Population is held at its 2022 Census level for all years.
- **Limitations:** Uses a 2022 denominator for later years, so counties that have grown since 2022 are slightly flattered. Completions say nothing about local need or the quality of what was built.

### Housing stock growth (county, Census)  
`stock_growth` · **published**

- **Calculation:** 100 x (Census housing stock 2022 / 2016 - 1), summed over the Census areas in each county.
- **Source data:** CSO F2020
- **Reference period:** Census April 2016 to April 2022.
- **Assumptions:** Census areas are aggregated to counties by summing.
- **Limitations:** Census stock includes vacant dwellings and holiday homes.

### Planning permissions vs completions  
`planning_to_completion` · **derived**

- **Calculation:** Completions in year Y / units granted planning permission in year Y-lag (NUTS3 region); lag selectable 0-3 years.
- **Source data:** CSO BHA13, NDQ06
- **Reference period:** Annual 2015 to 2025.
- **Assumptions:** Counties aggregated to NUTS3 regions using the CSO regional grouping (CIRGDP07).
- **Limitations:** A comparison ratio, not a conversion rate: permissions can lapse, be re-applied for, or be extended; completions also include dwellings permitted earlier or outside this series.

### Construction commencements  
`commencements` · **published**

- **Calculation:** Sum of residential units in commencement notices.
- **Source data:** CSO HSM13
- **Reference period:** Monthly March 2014 to October 2026.
- **Assumptions:** Annual totals use calendar years; partial years are flagged.
- **Limitations:** Commencement notices precede completion by many months; not all commenced units complete.

## Demand

### Population growth (county, Census)  
`population_growth` · **published**

- **Calculation:** 100 x (Census 2022 population / Census 2016 population - 1).
- **Source data:** CSO F1003 (Census population by county)
- **Reference period:** Census April 2016 to April 2022.
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** Census-to-Census only: no annual county population estimates are used.

### Population growth (national, annual)  
`population_growth_national` · **published**

- **Calculation:** 100 x (population in April t / population in April t-1 - 1).
- **Source data:** CSO PEA01, PEA15
- **Reference period:** April 1950 to April 2026 (latest years are provisional estimates).
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** Estimates are revised when new Census data become available.

### Household growth (county, Census)  
`household_growth` · **published**

- **Calculation:** 100 x (private households 2022 / private households 2016 - 1).
- **Source data:** CSO F2001
- **Reference period:** Census April 2016 to April 2022.
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** Households form from existing stock and from new homes; household growth reflects supply as well as demand.

### Housing supply-demand gap (national)  
`supply_demand_gap` · **estimate**

- **Calculation:** Total annual household demand - new dwelling completions. Demand = (population change / avg household size) + replacement demand (0.4 % of housing stock). Three scenario bands (low / central / high) vary net migration at 50 % / 100 % / 150 % of the observed PEA15 figure. Positive gap = shortfall; negative = surplus.
- **Source data:** CSO PEA15 (national population and migration), CSO NDQ06 (completions), CSO F2001 (households), CSO F2020 (housing stock)
- **Reference period:** Annual 2018 to latest full year (2017 used as population base; partial years flagged).
- **Assumptions:** Avg household size interpolated linearly between Census 2016 (2.75) and 2022 (2.74). Replacement rate fixed at 0.4 % of Census housing stock (European estimate). Migration scenarios are analytical illustrations, not forecasts.
- **Limitations:** Population-based demand does not capture housing quality, affordability or location mismatch. Completions are ESB-based proxies. Scenario bands represent migration variation only; natural increase is held at the observed level.

### Housing supply-demand gap (county)  
`supply_demand_gap_county` · **estimate**

- **Calculation:** County-level gap using PEA08 annual population estimates. Demand = (county population change / county avg household size) + replacement demand (0.4 % of Census 2022 housing stock). Gap = demand - completions.
- **Source data:** CSO PEA08 (county population estimates), CSO NDQ06 (completions), CSO F2001, F2020
- **Reference period:** Annual 2018 to latest available year in PEA08.
- **Assumptions:** County household size interpolated between Census years. Replacement stock fixed at Census 2022 level per county. Single central scenario (observed population change).
- **Limitations:** Annual county estimates are rounded to the nearest hundred persons (CSO PEA08 methodology), introducing rounding uncertainty in the household-demand calculation. County completions are aggregated from local authorities; small counties can show large swings from individual large developments. No scenario band at county level.

## Pressure

### Household growth minus housing-stock growth  
`household_minus_stock_growth` · **derived**

- **Calculation:** household growth % - housing stock growth %, in percentage points (positive = households grew faster than stock).
- **Source data:** CSO F2001, F2020
- **Reference period:** Census 2016 to 2022.
- **Assumptions:** Both series measured at the same two Census dates.
- **Limitations:** A positive gap can be absorbed by lower vacancy or larger households; it signals pressure, not an exact shortfall.

### County housing-pressure flags  
`pressure_flags` · **derived**

- **Calculation:** Count (0-6) of indicators in which a county is in the most-pressured quartile of the 26 counties: rent level, rent growth since 2019, rent-to-income, completions per 1,000 (lowest quartile), household-minus-stock growth, social housing need per 1,000.
- **Source data:** Rents (RIQ02), TRS38, NDQ06, F1003, F2001, F2020, SCA10
- **Reference period:** Mixed: see each component indicator.
- **Assumptions:** Equal treatment of all six indicators; quartile thresholds computed across the 26 counties. No weights, no composite score.
- **Limitations:** Relative, not absolute: a county can be flagged even when conditions are good by international standards. Quartile boundaries are arbitrary by nature.

## Affordability

### Rental price level and change  
`rent_level_change` · **published**

- **Calculation:** RTB standardised average monthly rent for new tenancies (all bedrooms, all property types); change = latest / base - 1.
- **Source data:** CSO RIQ02 (RTB Average Monthly Rent Report)
- **Reference period:** Quarterly 2007Q4 to 2025Q4 (latest published).
- **Assumptions:** County rows are used for county analysis; city rows are shown separately.
- **Limitations:** New-tenancy rents differ from rents paid by existing tenants; averages hide composition effects (property mix, bedrooms).

### National average rent (derived)  
`national_rent_proxy` · **estimate**

- **Calculation:** Weighted mean of the 26 county average rents, weighted by Census 2022 private-rented households.
- **Source data:** CSO RIQ02, F2004
- **Reference period:** Quarterly 2007Q4 to 2025Q4.
- **Assumptions:** Fixed 2022 weights apply to all periods.
- **Limitations:** The RTB/CSO table does not publish a national average; this is a transparent estimate, not an official figure.

### Residential property price index change  
`property_price_change` · **published**

- **Calculation:** CSO RPPI (base January 2015 = 100); 12-month % change as published; change vs the pre-crisis peak = latest / peak - 1.
- **Source data:** CSO HPM09
- **Reference period:** Monthly 2005 January to latest month (2026 September).
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** An index, not a euro price. County-level prices are not published by the CSO; regional series cover houses only.

### Rent as % of disposable income (measured)  
`rent_to_income_measured` · **published**

- **Calculation:** Median individual RTB tenant rent as % of that tenant's disposable income, by local authority; county value = mean of its local authorities weighted by dwelling stock.
- **Source data:** CSO TRS38 (CSO analysis of RTB-linked income data)
- **Reference period:** Rental year 2024.
- **Assumptions:** Dwelling stock (ESB connections, Q4 2024) is used as a proxy weight for the number of tenants in counties with several LAs.
- **Limitations:** Individual tenant income may exclude other household members' income; one reference year only.

### Annual rent vs disposable income per person (relative)  
`rent_vs_income_per_person` · **derived**

- **Calculation:** 12 x average monthly rent (latest quarter) / disposable income per person (latest year) x 100.
- **Source data:** CSO RIQ02, RAA02
- **Reference period:** Rent: latest quarter. Income: latest year published (2024).
- **Assumptions:** Per-person income is the only county income measure available.
- **Limitations:** Per-person income is lower than household income, so the level overstates the burden. Use only to compare counties, not as an absolute threshold.

### Housing Affordability Pressure Index  
`affordability_pressure_index` · **derived**

- **Calculation:** Four components per county: (1) median rent as % of tenant disposable income (TRS38), (2) annual average rent as % of disposable income per person, (3) rise in annual rent since Q4 2019 as % of income per person = 100 x 12 x (rent_latest - rent_Q4_2019) / income per person, (4) % change in the CSO regional house-price index (houses) since Dec 2019. Each is min-max standardised across the 26 counties to 0-100 (0 = lowest pressure, 100 = highest). Index = 0.35 x (1) + 0.25 x (2) + 0.20 x (3) + 0.20 x (4), a 0-100 relative score; rank 1 = least affordable.
- **Source data:** CSO TRS38, RIQ02 (RTB), RAA02, HPM09
- **Reference period:** Rents: Q4 2019 to latest quarter; income: latest year; burden: 2024; prices: Dec 2019 to latest month.
- **Assumptions:** Weights are a documented judgement, not estimated from data: the directly measured tenant rent burden gets the largest weight, the two rent-vs-income lenses 0.45 in total, prices 0.20. The dashboard lets the user change them. Euro rent rise (not % growth) is used so that counties that started with low rents do not score high merely from a low base.
- **Limitations:** Relative ranking only (not an absolute affordability threshold, not a forecast). No county price levels exist, so prices enter as REGIONAL growth shared by all counties in a region. Per-person income overstates burdens. Component weights drive rankings: see the sensitivity indicator. Mortgage affordability is not covered.

### Affordability index sensitivity analysis  
`affordability_index_sensitivity` · **estimate**

- **Calculation:** Rank stability of the index under (a) six named weighting scenarios, (b) dropping each component in turn (weights renormalised), (c) three standardisation methods (min-max, z-score, percentile rank), (d) 5,000 random weight sets: flat Dirichlet (any weighting equally likely) and Dirichlet concentrated around the baseline weights (concentration 50). Reported as rank ranges (5th-95th percentile), share of draws in the top 5, and Spearman rank correlation with the baseline.
- **Source data:** CSO TRS38, RIQ02 (RTB), RAA02, HPM09 (through the index components)
- **Reference period:** Same as the index.
- **Assumptions:** Random weights are uniform over the weight simplex (flat) or centred on the baseline (local); they represent uncertainty about how to weight, not statistical sampling error. Fixed seed (42) so results are reproducible.
- **Limitations:** Shows how much the ranking depends on analyst choices; it does not validate the index against any external measure of affordability. Components are correlated and some (regional prices) have only eight distinct values.

## Vacancy

### Vacancy rate (estimated)  
`vacancy_rate_esb` · **published**

- **Calculation:** Vacant dwellings / dwelling stock x 100, summed from local-authority counts (not an average of rates).
- **Source data:** CSO VAC14 (ESB-based estimate of vacant dwellings)
- **Reference period:** Q4 2022, Q4 2023, Q4 2024.
- **Assumptions:** A dwelling is classed vacant by the CSO using electricity consumption patterns.
- **Limitations:** Vacant does not mean habitable, available or suitable. Some vacancy is normal (sale, probate, turnover).

### Long-term vacancy share  
`long_term_vacancy` · **published**

- **Calculation:** Dwellings vacant in each of six consecutive years / all vacant dwellings x 100.
- **Source data:** CSO VAC23, VAC14
- **Reference period:** Q4 2024.
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** Persistently vacant dwellings are the group where reuse is most plausible but they are not necessarily habitable.

### Census vacancy rate  
`census_vacancy_rate` · **derived**

- **Calculation:** Vacant house/apartment / total housing stock x 100 (Census night).
- **Source data:** CSO F2020
- **Reference period:** Census April 2022.
- **Assumptions:** Holiday homes are reported separately and are not counted as vacant.
- **Limitations:** Census night snapshot; reasons are self-reported.

### Reuse-pathway grouping of Census vacancy reasons  
`vacancy_reason_groups` · **estimate**

- **Calculation:** Census 2022 reasons grouped: Needs work/probate (Renovation, Deceased), In market transition (For sale, Rental, New build), Family or care circumstances (With relatives, Nursing home/hospital), Other.
- **Source data:** CSO F2014
- **Reference period:** Census April 2022.
- **Assumptions:** The grouping is an analytical judgement made by HomeScope for screening purposes.
- **Limitations:** Does not establish that any dwelling is habitable, available or economical to renovate.

## Social housing

### Families with children in need of social housing  
`social_need_per_1000` · **derived**

- **Calculation:** Households with children identified as in need of social housing (latest year) / Census 2022 households x 1,000.
- **Source data:** CSO SCA10, F2001
- **Reference period:** Latest year in SCA10 (county breakdown); households Census 2022.
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** Covers only households with children, so it understates total need; the numerator year and denominator year differ.

### Social rented share of households  
`social_rented_share` · **derived**

- **Calculation:** (Households renting from a local authority + voluntary body) / all households x 100.
- **Source data:** CSO F2004
- **Reference period:** Census April 2022.
- **Assumptions:** No additional assumptions: published figures are used as-is.
- **Limitations:** Census snapshot of the existing social stock - not a measure of need or recent delivery.

## Homelessness

### People in emergency accommodation  
`homelessness` · **published**

- **Calculation:** Adults plus dependants in emergency accommodation (Dept. of Housing monthly report); per 10,000 residents using Census 2022 population.
- **Source data:** Dept. of Housing, Local Government and Heritage monthly Homelessness Reports (data.gov.ie)
- **Reference period:** Monthly, January 2019 to September 2026 (some months absent).
- **Assumptions:** Counties are grouped into the nine Department regions for per-capita rates.
- **Limitations:** Counts people in emergency accommodation in the reference week only; excludes hidden homelessness and some supported accommodation.
