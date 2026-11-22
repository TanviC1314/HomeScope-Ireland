-- HomeScope Ireland - PostgreSQL schema
-- Idempotent: safe to run repeatedly (use `python -m src.database.loader --reset` to rebuild from scratch).
--
-- Model overview
--   data_source                provenance of every dataset (publisher, licence, publication date, reference period)
--   dim_region                 NUTS3 regions (planning data) and Dept. homeless regions (homelessness data)
--   dim_county                 26 counties -> province, NUTS3 region, homeless region
--   dim_local_authority        31 local authorities -> county
--   fact_*                     one table per analytical theme, keyed by (area, period[, category])
--   v_*                        convenience views used by the SQL analytics and the dashboard

CREATE TABLE IF NOT EXISTS data_source (
    source_key          VARCHAR(30)  PRIMARY KEY,
    title               TEXT         NOT NULL,
    provider            TEXT         NOT NULL,
    theme               VARCHAR(30),
    landing_url         TEXT,
    download_url        TEXT,
    licence             TEXT,
    granularity         TEXT,
    publication_updated DATE,
    reference_period    TEXT,
    retrieved_utc       TIMESTAMPTZ,
    raw_rows            INTEGER,
    status              VARCHAR(20),
    use_in_project      TEXT,
    notes               TEXT
);

-- ------------------------------------------------------------------ dimensions
CREATE TABLE IF NOT EXISTS dim_region (
    region_id    SERIAL       PRIMARY KEY,
    region_name  VARCHAR(30)  NOT NULL,
    region_type  VARCHAR(10)  NOT NULL CHECK (region_type IN ('NUTS3', 'HOMELESS')),
    UNIQUE (region_type, region_name)
);

CREATE TABLE IF NOT EXISTS dim_county (
    county_id           SERIAL       PRIMARY KEY,
    county_name         VARCHAR(30)  NOT NULL UNIQUE,
    province            VARCHAR(20)  NOT NULL,
    nuts3_region_id     INTEGER      NOT NULL REFERENCES dim_region (region_id),
    homeless_region_id  INTEGER      NOT NULL REFERENCES dim_region (region_id)
);

CREATE TABLE IF NOT EXISTS dim_local_authority (
    la_id      SERIAL       PRIMARY KEY,
    la_name    VARCHAR(60)  NOT NULL UNIQUE,
    county_id  INTEGER      NOT NULL REFERENCES dim_county (county_id),
    la_type    VARCHAR(20)
);

-- ------------------------------------------------------------------ housing supply
-- NDQ06: new dwelling completions (ESB connections based), by local authority, quarter and type
CREATE TABLE IF NOT EXISTS fact_completions (
    la_id          INTEGER      NOT NULL REFERENCES dim_local_authority (la_id),
    year           SMALLINT     NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    quarter        SMALLINT     NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    dwelling_type  VARCHAR(20)  NOT NULL CHECK (dwelling_type IN ('Single house', 'Scheme house', 'Apartment')),
    completions    INTEGER      CHECK (completions >= 0),
    PRIMARY KEY (la_id, year, quarter, dwelling_type)
);
CREATE INDEX IF NOT EXISTS ix_completions_year ON fact_completions (year, quarter);

-- HSM13: commencement notices by local authority and month
CREATE TABLE IF NOT EXISTS fact_commencements (
    la_id          INTEGER   NOT NULL REFERENCES dim_local_authority (la_id),
    period         DATE      NOT NULL,
    year           SMALLINT  NOT NULL,
    month          SMALLINT  NOT NULL CHECK (month BETWEEN 1 AND 12),
    notices        INTEGER   CHECK (notices >= 0),
    units          INTEGER   CHECK (units >= 0),
    one_off_units  INTEGER   CHECK (one_off_units >= 0),
    PRIMARY KEY (la_id, period)
);
CREATE INDEX IF NOT EXISTS ix_commencements_year ON fact_commencements (year);

-- BHA13: planning permissions granted for new dwellings, by NUTS3 region
CREATE TABLE IF NOT EXISTS fact_planning_permissions (
    region_id           INTEGER      NOT NULL REFERENCES dim_region (region_id),
    year                SMALLINT     NOT NULL,
    dwelling_type       VARCHAR(30)  NOT NULL,
    permissions         INTEGER      CHECK (permissions >= 0),
    units               INTEGER      CHECK (units >= 0),
    floor_area_000_sqm  NUMERIC(10, 2),
    avg_floor_area_sqm  NUMERIC(8, 2),
    PRIMARY KEY (region_id, year, dwelling_type)
);

-- ------------------------------------------------------------------ population and households
CREATE TABLE IF NOT EXISTS fact_population_census (
    county_id                  INTEGER   NOT NULL REFERENCES dim_county (county_id),
    census_year                SMALLINT  NOT NULL,
    population                 INTEGER   NOT NULL CHECK (population > 0),
    change_since_previous      INTEGER,
    pct_change_since_previous  NUMERIC(6, 2),
    PRIMARY KEY (county_id, census_year)
);

CREATE TABLE IF NOT EXISTS fact_population_national (
    year                         SMALLINT PRIMARY KEY,
    population_thousand          NUMERIC(8, 1),
    births_thousand              NUMERIC(8, 1),
    deaths_thousand              NUMERIC(8, 1),
    natural_increase_thousand    NUMERIC(8, 1),
    immigrants_thousand          NUMERIC(8, 1),
    emigrants_thousand           NUMERIC(8, 1),
    net_migration_thousand       NUMERIC(8, 1),
    population_change_thousand   NUMERIC(8, 1)
);

CREATE TABLE IF NOT EXISTS fact_households_census (
    county_id               INTEGER   NOT NULL REFERENCES dim_county (county_id),
    census_year             SMALLINT  NOT NULL,
    households              INTEGER   NOT NULL CHECK (households > 0),
    persons_in_households   INTEGER,
    avg_household_size      NUMERIC(5, 3),
    PRIMARY KEY (county_id, census_year)
);

-- ------------------------------------------------------------------ housing stock, tenure, vacancy
-- F2020 (Census 2016 and 2022). Area grain is the Census "county and city" area (Cork is one area).
CREATE TABLE IF NOT EXISTS fact_housing_stock_census (
    area_name            VARCHAR(60)  NOT NULL,
    county_id            INTEGER      NOT NULL REFERENCES dim_county (county_id),
    census_year          SMALLINT     NOT NULL,
    total_stock          INTEGER      NOT NULL CHECK (total_stock > 0),
    occupied             INTEGER,
    temporarily_absent   INTEGER,
    vacant               INTEGER      CHECK (vacant >= 0),
    holiday_home         INTEGER,
    vacancy_rate_pct     NUMERIC(5, 2),
    PRIMARY KEY (area_name, census_year)
);

CREATE TABLE IF NOT EXISTS fact_tenure_census (
    county_id    INTEGER      NOT NULL REFERENCES dim_county (county_id),
    census_year  SMALLINT     NOT NULL,
    tenure       VARCHAR(60)  NOT NULL,
    households   INTEGER      CHECK (households >= 0),
    PRIMARY KEY (county_id, census_year, tenure)
);

-- VAC14: vacant dwellings (ESB electricity-consumption based), by local authority, Q4 of 2022-2024
CREATE TABLE IF NOT EXISTS fact_vacancy_estimate (
    la_id             INTEGER   NOT NULL REFERENCES dim_local_authority (la_id),
    year              SMALLINT  NOT NULL,
    quarter           SMALLINT  NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    vacant_dwellings  INTEGER   NOT NULL CHECK (vacant_dwellings >= 0),
    dwelling_stock    INTEGER   NOT NULL CHECK (dwelling_stock > 0),
    vacancy_rate_pct  NUMERIC(5, 2),
    PRIMARY KEY (la_id, year, quarter)
);

-- VAC23: dwellings vacant for six consecutive years (long-term vacancy)
CREATE TABLE IF NOT EXISTS fact_long_term_vacancy (
    la_id             INTEGER   NOT NULL REFERENCES dim_local_authority (la_id),
    year              SMALLINT  NOT NULL,
    quarter           SMALLINT  NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    vacant_dwellings  INTEGER   NOT NULL CHECK (vacant_dwellings >= 0),
    dwelling_stock    INTEGER   NOT NULL CHECK (dwelling_stock > 0),
    vacancy_rate_pct  NUMERIC(5, 2),
    PRIMARY KEY (la_id, year, quarter)
);

-- F2014: Census 2022 vacant housing stock by reason for vacancy
CREATE TABLE IF NOT EXISTS fact_vacancy_reason_census (
    la_id             INTEGER      NOT NULL REFERENCES dim_local_authority (la_id),
    reason            VARCHAR(40)  NOT NULL,
    vacant_dwellings  INTEGER      NOT NULL CHECK (vacant_dwellings >= 0),
    PRIMARY KEY (la_id, reason)
);

-- ------------------------------------------------------------------ affordability
-- RIQ02: RTB average monthly rent (standardised, new tenancies), county and city locations
CREATE TABLE IF NOT EXISTS fact_rent_rtb (
    location          VARCHAR(40)  NOT NULL,
    county_id         INTEGER      NOT NULL REFERENCES dim_county (county_id),
    geography_type    VARCHAR(10)  NOT NULL CHECK (geography_type IN ('county', 'city')),
    year              SMALLINT     NOT NULL,
    quarter           SMALLINT     NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    bedrooms          VARCHAR(20)  NOT NULL,
    property_type     VARCHAR(30)  NOT NULL,
    avg_monthly_rent  NUMERIC(8, 2) NOT NULL CHECK (avg_monthly_rent > 0),
    PRIMARY KEY (location, year, quarter, bedrooms, property_type)
);
CREATE INDEX IF NOT EXISTS ix_rent_county_period ON fact_rent_rtb (county_id, year, quarter);

-- HPM09: Residential Property Price Index (base 2015 = 100)
CREATE TABLE IF NOT EXISTS fact_property_price_index (
    geography      VARCHAR(40)  NOT NULL,
    dwelling_type  VARCHAR(40)  NOT NULL,
    period         DATE         NOT NULL,
    rppi_index     NUMERIC(7, 2) NOT NULL CHECK (rppi_index > 0),
    pct_change_1m  NUMERIC(6, 2),
    pct_change_3m  NUMERIC(6, 2),
    pct_change_12m NUMERIC(6, 2),
    PRIMARY KEY (geography, dwelling_type, period)
);

-- RAA02: estimates of household income by county
CREATE TABLE IF NOT EXISTS fact_household_income_county (
    county_id                      INTEGER   NOT NULL REFERENCES dim_county (county_id),
    year                           SMALLINT  NOT NULL,
    disposable_income_per_person   NUMERIC(10, 2),
    total_income_per_person        NUMERIC(10, 2),
    disposable_household_income_m  NUMERIC(12, 2),
    total_household_income_m       NUMERIC(12, 2),
    PRIMARY KEY (county_id, year)
);

CREATE TABLE IF NOT EXISTS fact_household_income_national (
    year                           SMALLINT PRIMARY KEY,
    disposable_income_per_person   NUMERIC(10, 2),
    total_income_per_person        NUMERIC(10, 2),
    disposable_household_income_m  NUMERIC(12, 2),
    total_household_income_m       NUMERIC(12, 2)
);

-- TRS38: RTB tenants' rent as a share of disposable income (2024), by local authority
CREATE TABLE IF NOT EXISTS fact_rent_to_income_la (
    la_id                   INTEGER   NOT NULL REFERENCES dim_local_authority (la_id),
    year                    SMALLINT  NOT NULL,
    median_rent_pct_income  NUMERIC(5, 2) CHECK (median_rent_pct_income BETWEEN 0 AND 100),
    pct_tenants_40plus      NUMERIC(5, 2),
    pct_tenants_45plus      NUMERIC(5, 2),
    pct_tenants_50plus      NUMERIC(5, 2),
    PRIMARY KEY (la_id, year)
);

-- ------------------------------------------------------------------ social housing and homelessness
CREATE TABLE IF NOT EXISTS fact_social_housing_need (
    county_id                          INTEGER   NOT NULL REFERENCES dim_county (county_id),
    year                               SMALLINT  NOT NULL,
    households_with_children_in_need   INTEGER   NOT NULL CHECK (households_with_children_in_need >= 0),
    PRIMARY KEY (county_id, year)
);

CREATE TABLE IF NOT EXISTS fact_social_housing_need_national (
    year                               SMALLINT PRIMARY KEY,
    households_with_children_in_need   INTEGER  NOT NULL CHECK (households_with_children_in_need >= 0)
);

-- Dept. of Housing monthly homelessness report (adults + dependants in emergency accommodation)
CREATE TABLE IF NOT EXISTS fact_homelessness (
    region_id               INTEGER   NOT NULL REFERENCES dim_region (region_id),
    report_month            DATE      NOT NULL,
    adults_total            INTEGER   CHECK (adults_total >= 0),
    adults_male             INTEGER,
    adults_female           INTEGER,
    adults_18_24            INTEGER,
    adults_25_44            INTEGER,
    adults_45_64            INTEGER,
    adults_65_plus          INTEGER,
    private_emergency       INTEGER,
    supported_temporary     INTEGER,
    temporary_emergency     INTEGER,
    other_accommodation     INTEGER,
    families                INTEGER,
    adults_in_families      INTEGER,
    single_parent_families  INTEGER,
    dependants              INTEGER,
    total_persons           INTEGER   CHECK (total_persons >= 0),
    PRIMARY KEY (region_id, report_month)
);
CREATE INDEX IF NOT EXISTS ix_homelessness_month ON fact_homelessness (report_month);

-- ------------------------------------------------------------------ views
-- Completions per county and calendar year (partial years flagged)
CREATE OR REPLACE VIEW v_completions_county_year AS
SELECT c.county_name,
       f.year,
       SUM(f.completions)::INTEGER           AS completions,
       COUNT(DISTINCT f.quarter)::SMALLINT   AS quarters_reported,
       (COUNT(DISTINCT f.quarter) < 4)       AS is_partial_year
FROM fact_completions f
JOIN dim_local_authority la ON la.la_id = f.la_id
JOIN dim_county c           ON c.county_id = la.county_id
GROUP BY c.county_name, f.year;

-- Latest Census population / households per county
CREATE OR REPLACE VIEW v_county_census_2022 AS
SELECT c.county_name,
       p.population,
       h.households,
       h.avg_household_size
FROM dim_county c
JOIN fact_population_census p ON p.county_id = c.county_id AND p.census_year = 2022
JOIN fact_households_census h ON h.county_id = c.county_id AND h.census_year = 2022;
