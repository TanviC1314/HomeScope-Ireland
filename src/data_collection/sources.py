"""Registry of every external dataset used by HomeScope Ireland.

Each entry documents *where* a dataset comes from, *who* publishes it, under
which licence it can be reused, and what it is used for in the project.  The
registry is the single source of truth for the downloader, the manifest, the
data catalogue (``docs/DATA_CATALOGUE.md``) and the ``data_source`` table in
PostgreSQL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

CSO_API = "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API"
CSO_LICENCE = "Creative Commons Attribution 4.0 (CC BY 4.0)"
DEPT = "Department of Housing, Local Government and Heritage"


@dataclass(frozen=True)
class DatasetSource:
    key: str                      # short unique key, also used as file stem
    provider: str                 # publishing organisation
    title: str                    # official dataset title
    theme: str                    # analytical theme in HomeScope
    landing_url: str              # human-readable page for the dataset
    download_url: str             # machine download URL (CSV / GeoJSON)
    licence: str
    granularity: str              # spatial / temporal grain of the data
    use_in_project: str
    raw_subdir: str = "cso"
    file_name: str = ""
    code: str = ""                # CSO PxStat table code where relevant
    notes: str = ""
    required_columns: List[str] = field(default_factory=list)
    # Optional server-side subset (CSO PxStat JSON-RPC) for tables that exceed the API cell limit.
    subset_dimension: str = ""            # dimension id, e.g. "C03004V03625"
    subset_labels: tuple = ()             # category labels to request

    @property
    def raw_filename(self) -> str:
        return self.file_name or f"{self.key}.csv"


COUNTY_AND_CITY_LOCATIONS = (
    "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Dublin", "Galway", "Kerry", "Kildare", "Kilkenny",
    "Laois", "Leitrim", "Limerick", "Longford", "Louth", "Mayo", "Meath", "Monaghan", "Offaly",
    "Roscommon", "Sligo", "Tipperary", "Waterford", "Westmeath", "Wexford", "Wicklow",
    "Cork City", "Galway City", "Limerick City", "Waterford City", "Kilkenny City",
)


def _cso(code: str, title: str, theme: str, granularity: str, use: str,
         notes: str = "", required: List[str] | None = None, **extra) -> DatasetSource:
    return DatasetSource(
        key=code, code=code, provider="Central Statistics Office (CSO)", title=title,
        theme=theme, landing_url=f"https://data.cso.ie/table/{code}",
        download_url=f"{CSO_API}.ReadDataset/{code}/CSV/1.0/en",
        licence=CSO_LICENCE, granularity=granularity, use_in_project=use,
        notes=notes, required_columns=required or ["VALUE"], **extra,
    )


CSO_DATASETS: List[DatasetSource] = [
    _cso("NDQ06", "New Dwelling Completions by Local Authority and Dwelling Type (quarterly)",
         "supply", "Local authority x dwelling type x quarter, 2011Q1 onwards",
         "Housing completions by county/year; supply trends",
         "Based on ESB Networks new connections. 'Completions' are new dwellings connected to the grid, "
         "a CSO proxy for completions. Latest year is partial.",
         ["STATISTIC", "VALUE"]),
    _cso("HSM13", "Commencement Notices (monthly, by local authority)",
         "supply", "Local authority x month, 2014 onwards",
         "Construction commencements", "Source: Dept. of Housing Building Control Management System."),
    _cso("BHA13", "Planning Permissions Granted for New Houses and Apartments (annual, NUTS3 region)",
         "supply", "NUTS3 region x dwelling type x year, 1975 onwards",
         "Planning permissions vs completions",
         "Regional (not county) grain: planning data are only available by NUTS3 region from the CSO."),
    _cso("F1003", "Census Population and Actual and Percentage Change (by county)",
         "demand", "County x census year, 1926-2022", "Population growth"),
    _cso("PEA01", "Population Estimates (Persons in April) 1950-latest",
         "demand", "State x age x sex x year", "National population trend"),
    _cso("PEA15", "Annual Population Change (births, deaths, migration)",
         "demand", "State x component x year", "National population change drivers"),
    _cso("F2001", "Private Households in Permanent Housing Units (county, 1971-2022)",
         "demand", "County x census year", "Household formation"),
    _cso("F2020", "Housing Stock by County/City and Occupancy Status (Census 2016 & 2022)",
         "supply", "Local authority area x occupancy status x census year",
         "Housing stock and Census vacancy counts"),
    _cso("F2004", "Private Households by Nature of Occupancy (county, Census)",
         "social", "County x tenure x census year", "Tenure incl. local-authority and voluntary-body rented"),
    _cso("F2014", "Vacant Housing Stock by Reason for Vacancy (Census 2022)",
         "vacancy", "Local authority x reason", "Reasons for vacancy -> reuse potential"),
    _cso("VAC14", "Local Authority Vacant Dwelling Numbers (GeoDirectory/ESB based)",
         "vacancy", "Local authority x Q4 2022, 2023, 2024", "Vacancy rates",
         "Vacant = no/low electricity consumption. Does NOT imply the dwelling is habitable or available."),
    _cso("VAC23", "Six-Year Long-term Local Authority Vacant Dwelling Numbers",
         "vacancy", "Local authority x 2024Q4", "Long-term vacancy"),
    _cso("RIQ02", "RTB Average Monthly Rent Report (quarterly)",
         "affordability", "Location x bedrooms x property type x quarter, 2007Q4 onwards",
         "Rental price trends",
         "Standardised average rent for new tenancies registered with the RTB. The full table (446 locations) "
         "exceeds the API download limit, so only county and city-level locations are requested via a "
         "PxStat subset query; values are served unmodified.",
         subset_dimension="C03004V03625", subset_labels=COUNTY_AND_CITY_LOCATIONS),
    _cso("HPM09", "Residential Property Price Index (monthly)",
         "affordability", "National / Dublin / regions x property type x month, 2005 onwards",
         "Property price trends",
         "Index (base 2015=100), not euro prices. County detail is not published by the CSO."),
    _cso("RAA02", "Estimates of Household Income by County",
         "affordability", "County x year, 2000-2024", "Income for affordability measures"),
    _cso("TRS38", "RTB Rent as Percentage of Disposable Income by Local Authority (2024)",
         "affordability", "Local authority x 2024", "Rent-to-income indicator (directly measured)"),
    _cso("SCA10", "Households with Children identified as being in need of Social Housing",
         "social", "County x household type x year", "Social housing need (families with children only)",
         "Covers only households with children, not all households on the list."),
]

GEO_SOURCES: List[DatasetSource] = [
    DatasetSource(
        key="counties_osi_2019_gen20m", provider="Tailte Éireann (formerly Ordnance Survey Ireland)",
        title="Counties - National Statutory Boundaries - 2019 - Generalised 20m",
        theme="geography",
        landing_url="https://data-osi.opendata.arcgis.com/datasets/osi::counties-national-statutory-boundaries-2019-generalised-20m",
        download_url="https://data-osi.opendata.arcgis.com/api/download/v1/items/7ef9c5102d61424295e98505a00251ea/geojson?layers=0",
        licence="Creative Commons Attribution 4.0 (CC BY 4.0) - Tailte Éireann open data",
        granularity="26 counties (Dublin and Tipperary as single areas)",
        use_in_project="Interactive county map", raw_subdir="geo", file_name="counties_osi_2019_gen20m.geojson",
        notes="Boundaries are for visualisation only (generalised).",
    )
]

HOMELESSNESS_CKAN = "https://data.gov.ie/api/3/action"
HOMELESSNESS_PUBLISHER = DEPT
HOMELESSNESS_LICENCE = "Creative Commons Attribution Share-Alike 4.0 (CC BY-SA 4.0)"
HOMELESSNESS_LANDING = "https://data.gov.ie/organization/department-of-housing-local-government-and-heritage"

ALL_STATIC: List[DatasetSource] = CSO_DATASETS + GEO_SOURCES
BY_KEY: Dict[str, DatasetSource] = {s.key: s for s in ALL_STATIC}
