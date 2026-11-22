-- =====================================================================================================
-- HomeScope Ireland - SQL analytics (PostgreSQL)
-- Each block starts with "-- name:" and documents the question it answers and the SQL techniques used.
-- Run all of them with:  python -m src.database.run_queries
-- Notes
--   * "Completions" are CSO new dwelling completions (ESB connections). Latest year may be partial.
--   * Vacancy figures are statistical estimates; vacant does NOT mean habitable or available.
--   * Census-based comparisons use Census 2016 -> 2022 (April to April).
-- =====================================================================================================

-- name: Q01_completions_by_county_year
-- question: Which counties delivered the most new dwellings each year, and what share of national output is that?
-- techniques: JOIN (via view), window SUM/RANK, filter on full years
SELECT county_name, year, completions,
       ROUND(100.0 * completions / SUM(completions) OVER (PARTITION BY year), 1) AS pct_of_national,
       RANK() OVER (PARTITION BY year ORDER BY completions DESC)                 AS rank_in_year
FROM v_completions_county_year
WHERE NOT is_partial_year AND year >= 2015
ORDER BY year DESC, rank_in_year;

-- name: Q02_national_completions_annual_change
-- question: How has national housing supply changed year on year, and is the latest year complete?
-- techniques: CTE, LAG window function, CASE
WITH annual AS (
    SELECT year, SUM(completions) AS completions, COUNT(DISTINCT quarter) AS quarters
    FROM fact_completions
    GROUP BY year
)
SELECT year, completions, quarters,
       LAG(completions) OVER (ORDER BY year) AS previous_year,
       CASE WHEN quarters = 4 AND LAG(quarters) OVER (ORDER BY year) = 4
            THEN ROUND(100.0 * (completions - LAG(completions) OVER (ORDER BY year))
                       / NULLIF(LAG(completions) OVER (ORDER BY year), 0), 1) END AS yoy_change_pct,
       CASE WHEN quarters < 4 THEN 'partial year (not comparable)' ELSE 'full year' END AS coverage
FROM annual
ORDER BY year;

-- name: Q03_completions_per_1000_residents_latest_year
-- question: In the latest full year, which counties built the most (and fewest) homes relative to their population?
-- techniques: CTEs, subquery with HAVING, JOIN, RANK, NTILE
WITH latest AS (
    SELECT MAX(year) AS year
    FROM (SELECT year FROM fact_completions GROUP BY year HAVING COUNT(DISTINCT quarter) = 4) full_years
),
c AS (
    SELECT v.county_name, v.year, v.completions
    FROM v_completions_county_year v JOIN latest l ON l.year = v.year
)
SELECT c.county_name, c.year, c.completions, p.population AS population_2022,
       ROUND(1000.0 * c.completions / p.population, 2)                         AS completions_per_1000_residents,
       RANK()  OVER (ORDER BY c.completions::numeric / p.population DESC)      AS rank_high_to_low,
       NTILE(4) OVER (ORDER BY c.completions::numeric / p.population DESC)     AS quartile_1_is_highest
FROM c
JOIN dim_county dc               ON dc.county_name = c.county_name
JOIN fact_population_census p    ON p.county_id = dc.county_id AND p.census_year = 2022
ORDER BY rank_high_to_low;

-- name: Q04_population_growth_by_county_2016_2022
-- question: Which counties grew fastest between Census 2016 and Census 2022?
-- techniques: CTE, conditional aggregation (CASE), RANK, CASE banding
WITH pivoted AS (
    SELECT c.county_name,
           MAX(CASE WHEN p.census_year = 2016 THEN p.population END) AS pop_2016,
           MAX(CASE WHEN p.census_year = 2022 THEN p.population END) AS pop_2022
    FROM fact_population_census p
    JOIN dim_county c USING (county_id)
    GROUP BY c.county_name
)
SELECT county_name, pop_2016, pop_2022, pop_2022 - pop_2016 AS absolute_change,
       ROUND(100.0 * (pop_2022 - pop_2016) / pop_2016, 2) AS pct_change,
       RANK() OVER (ORDER BY (pop_2022 - pop_2016)::numeric / pop_2016 DESC) AS growth_rank,
       CASE WHEN pop_2022::numeric / pop_2016 >= 1.10 THEN 'fast (10%+)'
            WHEN pop_2022::numeric / pop_2016 >= 1.05 THEN 'moderate (5-10%)'
            ELSE 'slow (under 5%)' END AS growth_band
FROM pivoted
ORDER BY growth_rank;

-- name: Q05_households_vs_housing_stock_growth
-- question: Did the number of households grow faster than the housing stock in each county (Census 2016 -> 2022)?
-- techniques: three CTEs, FILTER aggregation, JOIN, CASE
WITH pop AS (
    SELECT county_id,
           MAX(population) FILTER (WHERE census_year = 2016) AS pop16,
           MAX(population) FILTER (WHERE census_year = 2022) AS pop22
    FROM fact_population_census GROUP BY county_id
), hh AS (
    SELECT county_id,
           MAX(households) FILTER (WHERE census_year = 2016) AS hh16,
           MAX(households) FILTER (WHERE census_year = 2022) AS hh22
    FROM fact_households_census GROUP BY county_id
), stock AS (
    SELECT county_id,
           SUM(total_stock) FILTER (WHERE census_year = 2016) AS stock16,
           SUM(total_stock) FILTER (WHERE census_year = 2022) AS stock22
    FROM fact_housing_stock_census GROUP BY county_id
)
SELECT c.county_name,
       ROUND(100.0 * (pop22 - pop16)     / pop16,   1) AS population_growth_pct,
       ROUND(100.0 * (hh22 - hh16)       / hh16,    1) AS household_growth_pct,
       ROUND(100.0 * (stock22 - stock16) / stock16, 1) AS housing_stock_growth_pct,
       ROUND(100.0 * (hh22 - hh16) / hh16 - 100.0 * (stock22 - stock16) / stock16, 1) AS household_minus_stock_growth_pp,
       CASE WHEN (hh22 - hh16)::numeric / hh16 > (stock22 - stock16)::numeric / stock16
            THEN 'households grew faster than stock'
            ELSE 'stock grew at least as fast as households' END AS reading
FROM dim_county c
JOIN pop   USING (county_id)
JOIN hh    USING (county_id)
JOIN stock USING (county_id)
ORDER BY household_minus_stock_growth_pp DESC;

-- name: Q06_rent_trend_by_county
-- question: How have average RTB rents (Q4, all bedrooms, all property types) moved each year, county by county?
-- techniques: CTE, JOIN, LAG and rolling-average window functions with a named WINDOW
WITH q4 AS (
    SELECT c.county_name, r.year, r.avg_monthly_rent
    FROM fact_rent_rtb r
    JOIN dim_county c USING (county_id)
    WHERE r.geography_type = 'county' AND r.bedrooms = 'All bedrooms'
      AND r.property_type = 'All property types' AND r.quarter = 4 AND r.year >= 2015
)
SELECT county_name, year, avg_monthly_rent,
       ROUND(100.0 * (avg_monthly_rent - LAG(avg_monthly_rent) OVER w) / LAG(avg_monthly_rent) OVER w, 1) AS yoy_change_pct,
       ROUND(AVG(avg_monthly_rent) OVER (PARTITION BY county_name ORDER BY year ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) AS rolling_3yr_avg
FROM q4
WINDOW w AS (PARTITION BY county_name ORDER BY year)
ORDER BY county_name, year;

-- name: Q07_rent_growth_since_2019
-- question: Which counties saw the biggest rent increases between Q4 2019 and the latest published quarter?
-- techniques: CTEs, scalar subquery for the latest period, RANK, CASE
WITH latest AS (
    SELECT year, quarter FROM fact_rent_rtb ORDER BY year DESC, quarter DESC LIMIT 1
), base AS (
    SELECT county_id, avg_monthly_rent AS rent_2019q4
    FROM fact_rent_rtb
    WHERE geography_type = 'county' AND bedrooms = 'All bedrooms' AND property_type = 'All property types'
      AND year = 2019 AND quarter = 4
), cur AS (
    SELECT r.county_id, r.avg_monthly_rent AS rent_latest, r.year, r.quarter
    FROM fact_rent_rtb r JOIN latest l ON l.year = r.year AND l.quarter = r.quarter
    WHERE r.geography_type = 'county' AND r.bedrooms = 'All bedrooms' AND r.property_type = 'All property types'
)
SELECT c.county_name, b.rent_2019q4, cur.rent_latest, cur.year AS latest_year, cur.quarter AS latest_quarter,
       cur.rent_latest - b.rent_2019q4 AS euro_change,
       ROUND(100.0 * (cur.rent_latest - b.rent_2019q4) / b.rent_2019q4, 1) AS pct_change,
       RANK() OVER (ORDER BY (cur.rent_latest - b.rent_2019q4) / b.rent_2019q4 DESC) AS growth_rank,
       CASE WHEN cur.rent_latest / b.rent_2019q4 >= 1.40 THEN '40%+ rise'
            WHEN cur.rent_latest / b.rent_2019q4 >= 1.25 THEN '25-40% rise'
            ELSE 'under 25% rise' END AS band
FROM base b
JOIN cur USING (county_id)
JOIN dim_county c USING (county_id)
ORDER BY growth_rank;

-- name: Q08_property_price_index_annual_and_drawdown
-- question: How have residential property prices (CSO RPPI, base 2015=100) changed each year, and how far is each area from its previous peak?
-- techniques: CTE, EXTRACT, LAG, running MAX window (ROWS UNBOUNDED PRECEDING)
WITH annual AS (
    SELECT geography, EXTRACT(YEAR FROM period)::int AS year, AVG(rppi_index) AS avg_index, COUNT(*) AS months_in_year
    FROM fact_property_price_index
    WHERE dwelling_type = 'all residential properties'
    GROUP BY geography, EXTRACT(YEAR FROM period)
)
SELECT geography, year, months_in_year, ROUND(avg_index, 1) AS avg_index,
       ROUND(100.0 * (avg_index / LAG(avg_index) OVER (PARTITION BY geography ORDER BY year) - 1), 1) AS yoy_change_pct,
       ROUND(100.0 * (avg_index / MAX(avg_index) OVER (PARTITION BY geography ORDER BY year ROWS UNBOUNDED PRECEDING) - 1), 1) AS vs_previous_peak_pct
FROM annual
ORDER BY geography, year;

-- name: Q09_completions_vs_household_growth_2016_2021
-- question: Were enough new dwellings completed (2016-2021) to cover the households added between Census 2016 and 2022?
-- techniques: CTEs, FILTER aggregation, JOIN, NULLIF, CASE
-- caveat: calendar years 2016-2021 approximate the April-to-April Census interval; new households can also occupy existing stock.
WITH comp AS (
    SELECT county_name, SUM(completions) AS completions_2016_2021
    FROM v_completions_county_year
    WHERE year BETWEEN 2016 AND 2021
    GROUP BY county_name
), hh AS (
    SELECT county_id,
           MAX(households) FILTER (WHERE census_year = 2016) AS hh16,
           MAX(households) FILTER (WHERE census_year = 2022) AS hh22
    FROM fact_households_census GROUP BY county_id
)
SELECT c.county_name, comp.completions_2016_2021, hh.hh22 - hh.hh16 AS households_added,
       ROUND(comp.completions_2016_2021::numeric / NULLIF(hh.hh22 - hh.hh16, 0), 2) AS completions_per_added_household,
       CASE WHEN comp.completions_2016_2021 < hh.hh22 - hh.hh16 THEN 'fewer new dwellings than new households'
            ELSE 'new dwellings at least equal to new households' END AS reading
FROM dim_county c
JOIN comp ON comp.county_name = c.county_name
JOIN hh   ON hh.county_id = c.county_id
ORDER BY completions_per_added_household;

-- name: Q10_vacancy_rate_by_nuts3_region
-- question: Where is vacancy concentrated by region, and how much of it is long-term (vacant six years running)?
-- techniques: multi-table JOIN, LEFT JOIN, GROUP BY, scalar subquery, RANK
SELECT r.region_name,
       SUM(v.vacant_dwellings) AS vacant_dwellings,
       SUM(v.dwelling_stock)   AS dwelling_stock,
       ROUND(100.0 * SUM(v.vacant_dwellings) / SUM(v.dwelling_stock), 2) AS vacancy_rate_pct,
       SUM(lt.vacant_dwellings) AS long_term_vacant,
       ROUND(100.0 * SUM(lt.vacant_dwellings) / SUM(v.vacant_dwellings), 1) AS long_term_share_of_vacant_pct,
       RANK() OVER (ORDER BY SUM(v.vacant_dwellings)::numeric / SUM(v.dwelling_stock) DESC) AS rate_rank
FROM fact_vacancy_estimate v
JOIN dim_local_authority la ON la.la_id = v.la_id
JOIN dim_county c           ON c.county_id = la.county_id
JOIN dim_region r           ON r.region_id = c.nuts3_region_id
LEFT JOIN fact_long_term_vacancy lt ON lt.la_id = v.la_id AND lt.year = v.year AND lt.quarter = v.quarter
WHERE v.quarter = 4 AND v.year = (SELECT MAX(year) FROM fact_vacancy_estimate)
GROUP BY r.region_name
ORDER BY rate_rank;

-- name: Q11_planning_permissions_vs_completions_by_region
-- question: Are planning permissions translating into completed homes? (same-year and two-year-lag comparison by NUTS3 region)
-- techniques: three CTEs, JOIN across dimensions, LAG(…, 2), NULLIF
-- caveat: permissions are not commencements; permissions lapse, are re-applied for, or are for sites never built.
WITH comp AS (
    SELECT r.region_name, f.year, SUM(f.completions) AS completions, COUNT(DISTINCT f.quarter) AS quarters
    FROM fact_completions f
    JOIN dim_local_authority la ON la.la_id = f.la_id
    JOIN dim_county c           ON c.county_id = la.county_id
    JOIN dim_region r           ON r.region_id = c.nuts3_region_id
    GROUP BY r.region_name, f.year
), plan AS (
    SELECT r.region_name, p.year, SUM(p.units) AS permitted_units
    FROM fact_planning_permissions p
    JOIN dim_region r ON r.region_id = p.region_id
    GROUP BY r.region_name, p.year
), plan_lag AS (
    SELECT region_name, year, permitted_units,
           LAG(permitted_units, 2) OVER (PARTITION BY region_name ORDER BY year) AS permitted_units_2yrs_earlier
    FROM plan
)
SELECT c.region_name, c.year, c.completions, p.permitted_units, p.permitted_units_2yrs_earlier,
       ROUND(c.completions::numeric / NULLIF(p.permitted_units, 0), 2)               AS completions_to_permitted_same_year,
       ROUND(c.completions::numeric / NULLIF(p.permitted_units_2yrs_earlier, 0), 2)  AS completions_to_permitted_2yr_lag
FROM comp c
JOIN plan_lag p ON p.region_name = c.region_name AND p.year = c.year
WHERE c.quarters = 4 AND c.year BETWEEN 2015 AND 2025
ORDER BY c.year DESC, c.region_name;

-- name: Q12_commencements_vs_completions_by_county
-- question: Are construction starts running ahead of or behind completions, county by county and year by year?
-- techniques: CTEs, JOIN, month-completeness filter, LAG
WITH cm AS (
    SELECT c.county_name, f.year, SUM(f.units) AS commenced_units, COUNT(DISTINCT f.month) AS months
    FROM fact_commencements f
    JOIN dim_local_authority la ON la.la_id = f.la_id
    JOIN dim_county c           ON c.county_id = la.county_id
    GROUP BY c.county_name, f.year
), cp AS (
    SELECT county_name, year, completions FROM v_completions_county_year WHERE NOT is_partial_year
), j AS (
    SELECT cm.county_name, cm.year, cm.commenced_units, cp.completions,
           LAG(cm.commenced_units) OVER (PARTITION BY cm.county_name ORDER BY cm.year) AS commenced_prev_year
    FROM cm JOIN cp ON cp.county_name = cm.county_name AND cp.year = cm.year
    WHERE cm.months = 12
)
SELECT county_name, year, commenced_units, completions, commenced_prev_year,
       ROUND(completions::numeric / NULLIF(commenced_prev_year, 0), 2) AS completions_to_prev_year_commencements
FROM j
WHERE year BETWEEN 2016 AND 2025
ORDER BY year DESC, completions DESC;

-- name: Q13_social_housing_need_per_1000_households
-- question: Which counties have the most families with children identified as needing social housing, relative to household numbers?
-- techniques: CTEs, scalar MAX subquery, JOIN, RANK, NTILE
WITH latest AS (SELECT MAX(year) AS year FROM fact_social_housing_need),
now_ AS (
    SELECT n.county_id, n.year, n.households_with_children_in_need AS need
    FROM fact_social_housing_need n JOIN latest l ON l.year = n.year
), base AS (
    SELECT county_id, households_with_children_in_need AS need_2017
    FROM fact_social_housing_need WHERE year = 2017
)
SELECT c.county_name, now_.year, now_.need AS families_in_need, base.need_2017,
       ROUND(100.0 * (now_.need - base.need_2017) / NULLIF(base.need_2017, 0), 1) AS change_since_2017_pct,
       h.households AS households_2022,
       ROUND(1000.0 * now_.need / h.households, 1) AS need_per_1000_households,
       RANK()   OVER (ORDER BY now_.need::numeric / h.households DESC) AS rank_high_to_low,
       NTILE(4) OVER (ORDER BY now_.need::numeric / h.households DESC) AS quartile_1_is_highest
FROM now_
JOIN dim_county c ON c.county_id = now_.county_id
JOIN base         ON base.county_id = now_.county_id
JOIN fact_households_census h ON h.county_id = now_.county_id AND h.census_year = 2022
ORDER BY rank_high_to_low;

-- name: Q14_tenure_mix_social_and_private_rented_2022
-- question: How large are social rented and private rented sectors in each county (Census 2022)?
-- techniques: FILTER aggregation, GROUP BY, RANK
SELECT c.county_name,
       SUM(t.households) FILTER (WHERE t.tenure = 'All types of occupancy')           AS all_households,
       SUM(t.households) FILTER (WHERE t.tenure = 'Rented from a local authority')    AS rented_from_local_authority,
       SUM(t.households) FILTER (WHERE t.tenure = 'Rented from a voluntary body')     AS rented_from_voluntary_body,
       SUM(t.households) FILTER (WHERE t.tenure = 'Rented from private landlord')     AS rented_from_private_landlord,
       ROUND(100.0 * SUM(t.households) FILTER (WHERE t.tenure IN ('Rented from a local authority', 'Rented from a voluntary body'))
             / SUM(t.households) FILTER (WHERE t.tenure = 'All types of occupancy'), 1) AS social_rented_pct,
       ROUND(100.0 * SUM(t.households) FILTER (WHERE t.tenure = 'Rented from private landlord')
             / SUM(t.households) FILTER (WHERE t.tenure = 'All types of occupancy'), 1) AS private_rented_pct,
       RANK() OVER (ORDER BY SUM(t.households) FILTER (WHERE t.tenure = 'Rented from private landlord')::numeric
                    / SUM(t.households) FILTER (WHERE t.tenure = 'All types of occupancy') DESC) AS private_rented_rank
FROM fact_tenure_census t
JOIN dim_county c USING (county_id)
WHERE t.census_year = 2022
GROUP BY c.county_name
ORDER BY private_rented_rank;

-- name: Q15_homelessness_national_trend
-- question: How has the number of people in emergency accommodation changed, and what is the year-on-year trend?
-- techniques: CTE, date-based self-join (robust to missing months), rolling window average
WITH monthly AS (
    SELECT report_month, SUM(total_persons) AS persons, SUM(families) AS families, SUM(dependants) AS child_dependants
    FROM fact_homelessness
    GROUP BY report_month
)
SELECT m.report_month, m.persons, m.families, m.child_dependants,
       prev.persons AS persons_12_months_earlier,
       ROUND(100.0 * (m.persons - prev.persons) / NULLIF(prev.persons, 0), 1) AS yoy_change_pct,
       ROUND(AVG(m.persons) OVER (ORDER BY m.report_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) AS rolling_3m_avg
FROM monthly m
LEFT JOIN monthly prev ON prev.report_month = (m.report_month - INTERVAL '12 months')::date
ORDER BY m.report_month;

-- name: Q16_homelessness_per_10000_by_region_latest
-- question: Which Department regions have the highest homelessness relative to population in the latest report?
-- techniques: CTEs, JOIN, GROUP BY, RANK
WITH latest AS (SELECT MAX(report_month) AS m FROM fact_homelessness),
pop AS (
    SELECT c.homeless_region_id AS region_id, SUM(p.population) AS population_2022
    FROM fact_population_census p
    JOIN dim_county c USING (county_id)
    WHERE p.census_year = 2022
    GROUP BY c.homeless_region_id
)
SELECT r.region_name, h.report_month, h.total_persons, h.families, h.dependants, pop.population_2022,
       ROUND(10000.0 * h.total_persons / pop.population_2022, 1) AS persons_per_10000_residents,
       RANK() OVER (ORDER BY h.total_persons::numeric / pop.population_2022 DESC) AS rank_high_to_low
FROM fact_homelessness h
JOIN latest l ON l.m = h.report_month
JOIN dim_region r ON r.region_id = h.region_id
JOIN pop ON pop.region_id = h.region_id
ORDER BY rank_high_to_low;

-- name: Q17_regional_affordability_differences
-- question: How do rent levels, income and the measured rent-to-income burden differ across counties?
-- techniques: 4 CTEs, stock-weighted aggregation, scalar subqueries for latest periods, RANK, CASE
-- note: county rent-to-income = local-authority medians (CSO/RTB 2024) weighted by dwelling stock (a proxy for tenant numbers).
WITH stock AS (
    SELECT v.la_id, la.county_id, v.dwelling_stock
    FROM fact_vacancy_estimate v JOIN dim_local_authority la ON la.la_id = v.la_id
    WHERE v.quarter = 4 AND v.year = (SELECT MAX(year) FROM fact_vacancy_estimate)
), r2i AS (
    SELECT s.county_id,
           SUM(t.median_rent_pct_income * s.dwelling_stock) / SUM(s.dwelling_stock) AS rent_pct_income,
           SUM(t.pct_tenants_40plus     * s.dwelling_stock) / SUM(s.dwelling_stock) AS pct_tenants_paying_40plus
    FROM fact_rent_to_income_la t JOIN stock s ON s.la_id = t.la_id
    GROUP BY s.county_id
), rent AS (
    SELECT county_id, avg_monthly_rent
    FROM fact_rent_rtb
    WHERE geography_type = 'county' AND bedrooms = 'All bedrooms' AND property_type = 'All property types'
      AND (year, quarter) = (SELECT year, quarter FROM fact_rent_rtb ORDER BY year DESC, quarter DESC LIMIT 1)
), inc AS (
    SELECT county_id, year AS income_year, disposable_income_per_person
    FROM fact_household_income_county
    WHERE year = (SELECT MAX(year) FROM fact_household_income_county)
)
SELECT c.county_name, rent.avg_monthly_rent, inc.income_year, inc.disposable_income_per_person,
       ROUND(r2i.rent_pct_income, 1)             AS median_rent_pct_of_disposable_income,
       ROUND(r2i.pct_tenants_paying_40plus, 1)   AS pct_tenants_paying_40plus,
       RANK() OVER (ORDER BY r2i.rent_pct_income DESC) AS burden_rank,
       CASE NTILE(3) OVER (ORDER BY r2i.rent_pct_income DESC)
            WHEN 1 THEN 'highest third of counties'
            WHEN 2 THEN 'middle third of counties'
            ELSE 'lowest third of counties' END AS burden_band_relative
FROM dim_county c
JOIN r2i  USING (county_id)
JOIN rent USING (county_id)
JOIN inc  USING (county_id)
ORDER BY burden_rank;

-- name: Q18_regional_demand_indicators_vs_national
-- question: How do NUTS3 regions compare with the national average on population growth, household growth and recent building?
-- techniques: CTE built from sums (not averages of ratios), nested aggregation, window functions against the national total
WITH county_base AS (
    SELECT c.county_id, c.county_name, c.nuts3_region_id,
           MAX(p.population)  FILTER (WHERE p.census_year = 2016) AS pop16,
           MAX(p.population)  FILTER (WHERE p.census_year = 2022) AS pop22,
           MAX(h.households)  FILTER (WHERE h.census_year = 2016) AS hh16,
           MAX(h.households)  FILTER (WHERE h.census_year = 2022) AS hh22
    FROM dim_county c
    JOIN fact_population_census p USING (county_id)
    JOIN fact_households_census h USING (county_id)
    GROUP BY c.county_id, c.county_name, c.nuts3_region_id
), recent AS (
    SELECT county_name, SUM(completions) AS completions_2023_2025
    FROM v_completions_county_year WHERE year BETWEEN 2023 AND 2025 GROUP BY county_name
), region AS (
    SELECT r.region_name,
           SUM(cb.pop16) AS pop16, SUM(cb.pop22) AS pop22, SUM(cb.hh16) AS hh16, SUM(cb.hh22) AS hh22,
           SUM(rc.completions_2023_2025) AS completions_2023_2025
    FROM county_base cb
    JOIN dim_region r ON r.region_id = cb.nuts3_region_id
    JOIN recent rc    ON rc.county_name = cb.county_name
    GROUP BY r.region_name
)
SELECT region_name,
       ROUND(100.0 * (pop22 - pop16) / pop16, 1)  AS population_growth_pct,
       ROUND(100.0 * (hh22 - hh16) / hh16, 1)     AS household_growth_pct,
       ROUND(1000.0 * completions_2023_2025 / pop22, 1) AS completions_2023_25_per_1000_residents,
       ROUND(100.0 * (hh22 - hh16) / hh16
             - 100.0 * (SUM(hh22) OVER () - SUM(hh16) OVER ()) / SUM(hh16) OVER (), 1) AS household_growth_vs_national_pp,
       ROUND(1000.0 * completions_2023_2025 / pop22
             - 1000.0 * SUM(completions_2023_2025) OVER () / SUM(pop22) OVER (), 1)    AS completions_vs_national_per_1000
FROM region
ORDER BY household_growth_pct DESC;

-- name: Q19_vacancy_reasons_and_reuse_pathways_by_county
-- question: Among vacant dwellings recorded in Census 2022, how many were vacant for reasons that point to a possible reuse pathway?
-- techniques: JOIN, CASE-based grouping, FILTER aggregation, ranking
-- caveat: reason groups are an analytical grouping of Census-night reasons. They do NOT prove a dwelling is habitable, available or suitable.
WITH grouped AS (
    SELECT c.county_name,
           v.vacant_dwellings,
           CASE WHEN v.reason IN ('Renovation', 'Deceased')                        THEN 'needs_work_or_probate'
                WHEN v.reason IN ('For Sale', 'Rental Property', 'New Build')      THEN 'in_market_transition'
                WHEN v.reason IN ('Nursing Home / Hospital', 'With Relatives')     THEN 'family_or_care_circumstances'
                ELSE 'other_or_not_stated' END AS reason_group
    FROM fact_vacancy_reason_census v
    JOIN dim_local_authority la ON la.la_id = v.la_id
    JOIN dim_county c           ON c.county_id = la.county_id
)
SELECT county_name,
       SUM(vacant_dwellings) AS census_vacant_dwellings,
       SUM(vacant_dwellings) FILTER (WHERE reason_group = 'needs_work_or_probate')         AS needs_work_or_probate,
       SUM(vacant_dwellings) FILTER (WHERE reason_group = 'in_market_transition')           AS in_market_transition,
       SUM(vacant_dwellings) FILTER (WHERE reason_group = 'family_or_care_circumstances')   AS family_or_care_circumstances,
       ROUND(100.0 * SUM(vacant_dwellings) FILTER (WHERE reason_group = 'needs_work_or_probate') / SUM(vacant_dwellings), 1) AS needs_work_or_probate_pct,
       RANK() OVER (ORDER BY SUM(vacant_dwellings) FILTER (WHERE reason_group = 'needs_work_or_probate') DESC) AS rank_by_count
FROM grouped
GROUP BY county_name
ORDER BY rank_by_count;

-- name: Q20_long_term_vacancy_and_change_by_local_authority
-- question: Which local authorities have the largest share of persistently (six-year) vacant dwellings, and is vacancy rising or falling?
-- techniques: three-way JOIN, conditional aggregation across years, RANK, CASE
WITH rates AS (
    SELECT la_id,
           MAX(vacant_dwellings) FILTER (WHERE year = 2022 AND quarter = 4) AS vacant_2022,
           MAX(vacant_dwellings) FILTER (WHERE year = 2024 AND quarter = 4) AS vacant_2024,
           MAX(dwelling_stock)   FILTER (WHERE year = 2024 AND quarter = 4) AS stock_2024
    FROM fact_vacancy_estimate GROUP BY la_id
)
SELECT la.la_name, rates.vacant_2022, rates.vacant_2024,
       ROUND(100.0 * (rates.vacant_2024 - rates.vacant_2022) / NULLIF(rates.vacant_2022, 0), 1) AS change_2022_2024_pct,
       ROUND(100.0 * rates.vacant_2024 / rates.stock_2024, 2) AS vacancy_rate_2024_pct,
       lt.vacant_dwellings AS six_year_vacant_2024,
       ROUND(100.0 * lt.vacant_dwellings / NULLIF(rates.vacant_2024, 0), 1) AS long_term_share_pct,
       RANK() OVER (ORDER BY lt.vacant_dwellings::numeric / NULLIF(rates.vacant_2024, 0) DESC) AS long_term_share_rank,
       CASE WHEN rates.vacant_2024 < rates.vacant_2022 THEN 'vacancy falling'
            WHEN rates.vacant_2024 > rates.vacant_2022 THEN 'vacancy rising'
            ELSE 'unchanged' END AS direction
FROM rates
JOIN dim_local_authority la ON la.la_id = rates.la_id
JOIN fact_long_term_vacancy lt ON lt.la_id = rates.la_id AND lt.year = 2024 AND lt.quarter = 4
ORDER BY long_term_share_rank;
