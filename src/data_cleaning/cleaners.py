"""Reusable, testable cleaning functions - one per source dataset.

Every function takes a *raw* DataFrame (as read by ``read_cso_csv``) and returns a tidy analytical
table.  Raw files are never modified.  Conventions
------------------------------------------------
* Official statistics are never imputed.  Blank/suppressed values stay missing (NaN).
* Names are standardised through ``reference.py`` (26 counties, 31 local authorities, regions).
* National/"Ireland" total rows are used to *reconcile* the sum of the parts and then removed,
  so that no analysis can double count them.
* Every check or repair is written to the optional ``QualityReport``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.data_cleaning import reference as ref
from src.data_cleaning.quality import QualityReport, check_duplicates, check_missing, check_range, reconcile


# ----------------------------------------------------------------------------- helpers
def read_cso_csv(path: Path | str) -> pd.DataFrame:
    """Read a raw CSO PxStat CSV (UTF-8 with BOM) as strings; fall back to cp1252 if needed."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m src.data_collection.download` or follow the manual "
            "download instructions in data/raw/MANIFEST.json."
        )
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"cannot decode {path}")


def _find(df: pd.DataFrame, *names: str) -> str:
    for n in names:
        if n in df.columns:
            return n
    raise KeyError(f"none of {names} in columns {list(df.columns)}")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _stat_col(df: pd.DataFrame) -> str:
    return _find(df, "Statistic Label", "STATISTIC Label")


def _quarter_parts(q: pd.Series) -> pd.DataFrame:
    parts = q.str.extract(r"^(\d{4})\s*Q([1-4])$")
    return pd.DataFrame({"year": parts[0].astype("Int64"), "quarter": parts[1].astype("Int64")})


def _map_la(df: pd.DataFrame, col: str, dataset: str, report: Optional[QualityReport]) -> pd.DataFrame:
    df = df.copy()
    df["la_name"] = df[col].map(ref.standardise_la)
    unknown = df.loc[df["la_name"].isna() & ~df[col].map(ref.is_national), col].unique()
    if len(unknown) and report is not None:
        report.add(dataset, "unmapped local authority names", "warning", len(unknown), f"{list(unknown)[:5]}", "rows dropped")
    elif report is not None:
        report.add(dataset, "local authority names standardised", "pass", 0, "all names map to the 31 local authorities")
    df["county"] = df["la_name"].map(lambda n: ref._COUNTY_BY_LA.get(n) if n else None)
    return df


# ----------------------------------------------------------------------------- supply
def clean_completions(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """NDQ06 -> la_name, county, year, quarter, dwelling_type, completions."""
    ds = "NDQ06"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df = df.rename(columns={"Type of House": "dwelling_type", "Local Authority": "area"})
    df = pd.concat([df, _quarter_parts(df["Quarter"])], axis=1)

    national = df[df["area"].map(ref.is_national)]
    parts = df[~df["area"].map(ref.is_national)].copy()
    # types reconcile to 'All house types'
    typed = parts[parts["dwelling_type"] != "All house types"]
    allt = parts[parts["dwelling_type"] == "All house types"]
    reconcile(report, ds, "single + scheme + apartment = all house types",
              typed["value"].sum(), allt["value"].sum(), tolerance=0.5)
    # local authorities reconcile to the published national total
    nat_typed = national[national["dwelling_type"] != "All house types"]
    reconcile(report, ds, "sum of local authorities = published Ireland total",
              typed["value"].sum(), nat_typed["value"].sum(), tolerance=0.5)

    parts = _map_la(typed, "area", ds, report).dropna(subset=["la_name"])
    check_missing(parts, ["value"], ds, report)
    parts = check_range(parts, "value", 0, 20000, ds, report)
    out = parts.rename(columns={"value": "completions"})[
        ["la_name", "county", "year", "quarter", "dwelling_type", "completions"]]
    out = check_duplicates(out, ["la_name", "year", "quarter", "dwelling_type"], ds, report)
    last = out.sort_values(["year", "quarter"]).iloc[-1]
    if report is not None:
        report.add(ds, "reporting period", "info", 0, f"quarterly {out['year'].min()}Q1 to {int(last['year'])}Q{int(last['quarter'])}; "
                   f"{int(last['year'])} is a partial calendar year" if last["quarter"] < 4 else "complete calendar years",
                   "annual totals flag partial years (is_partial_year)")
    return out.reset_index(drop=True)


def clean_commencements(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """HSM13 -> la_name, county, period, year, month, notices, units, one_off_units."""
    ds = "HSM13"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df["period"] = pd.to_datetime(df["Month"], format="%Y %B")
    measure = {"Number of notices for residential development": "notices",
               "Number of residential units": "units",
               "Number of one-off residential units": "one_off_units"}
    df["measure"] = df["Residential Units Commenced"].map(measure)
    df = df.rename(columns={"Local Authority": "area"})
    national = df[df["area"].map(ref.is_national)]
    parts = df[~df["area"].map(ref.is_national)]
    reconcile(report, ds, "sum of local authorities = published Ireland total (units)",
              parts.loc[parts["measure"] == "units", "value"].sum(),
              national.loc[national["measure"] == "units", "value"].sum(), rel_tolerance=1e-4,
              fail_status="info", note="Source rounding/revision difference; the project always sums local authorities.")
    parts = _map_la(parts, "area", ds, report).dropna(subset=["la_name"])
    wide = parts.pivot_table(index=["la_name", "county", "period"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    wide["year"] = wide["period"].dt.year
    wide["month"] = wide["period"].dt.month
    check_missing(wide, ["notices", "units", "one_off_units"], ds, report)
    wide = check_range(wide, "units", 0, 20000, ds, report)
    wide = check_duplicates(wide, ["la_name", "period"], ds, report)
    if report is not None:
        report.add(ds, "reporting period", "info", 0, f"monthly {wide['period'].min():%Y-%m} to {wide['period'].max():%Y-%m}",
                   "annual totals flag partial years")
    return wide[["la_name", "county", "period", "year", "month", "notices", "units", "one_off_units"]].reset_index(drop=True)


def clean_planning(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """BHA13 -> region (NUTS3), year, dwelling_type, permissions, units, floor_area_000_sqm."""
    ds = "BHA13"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    stat = {"Planning Permissions Granted": "permissions", "Units for which Permission Granted": "units",
            "Total Floor Area for which Permission Granted": "floor_area_000_sqm",
            "Average Floor Area per Unit": "avg_floor_area_sqm"}
    df["measure"] = df[_stat_col(df)].map(stat)
    df = df.rename(columns={"NUTS 3 Region": "region", "Type of Dwelling": "dwelling_type", "Year": "year"})
    df["year"] = df["year"].astype(int)
    wide = df.pivot_table(index=["region", "year", "dwelling_type"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    nat = wide[wide["region"] == "Ireland"]
    regions = wide[wide["region"].isin(ref.NUTS3_REGIONS)].copy()
    # reconcile regions to published national total for a recent year where all data exist
    chk = regions[(regions["year"] == 2019) & (regions["dwelling_type"] != "All houses")]["units"].sum()
    exp = nat[(nat["year"] == 2019) & (nat["dwelling_type"] != "All houses")]["units"].sum()
    reconcile(report, ds, "2019: sum of 8 NUTS3 regions = Ireland (units, houses + apartments)", chk, exp, tolerance=0.5)
    # 'All houses' = one-off + multi development; drop it to prevent double counting
    houses = regions[regions["dwelling_type"].isin(["One off houses", "Multi development houses"])].groupby(["region", "year"])["units"].sum(min_count=2)
    allh = regions[regions["dwelling_type"] == "All houses"].set_index(["region", "year"])["units"]
    joined = pd.concat([houses.rename("sum"), allh.rename("all")], axis=1).dropna()
    reconcile(report, ds, "one-off + multi-development houses = all houses (units)", joined["sum"].sum(), joined["all"].sum(), tolerance=0.5)
    regions = regions[regions["dwelling_type"] != "All houses"]
    check_missing(regions[regions["year"] >= 2011], ["units"], ds, report, note="no gaps expected from 2011")
    regions = check_duplicates(regions, ["region", "year", "dwelling_type"], ds, report)
    regions = check_range(regions, "units", 0, 40000, ds, report)
    if report is not None:
        report.add(ds, "geographic grain", "info", 0, "planning permissions are published by NUTS3 region only",
                   "comparisons with completions are made at NUTS3 level (counties aggregated)")
    return regions[["region", "year", "dwelling_type", "permissions", "units", "floor_area_000_sqm", "avg_floor_area_sqm"]].reset_index(drop=True)


# ----------------------------------------------------------------------------- demand
def clean_population_census(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """F1003 -> county, census_year, population, change_since_previous, pct_change_since_previous."""
    ds = "F1003"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    m = {"Population": "population", "Actual change since previous census": "change_since_previous",
         "Percentage change since previous census": "pct_change_since_previous"}
    df["measure"] = df[_stat_col(df)].map(m)
    df["census_year"] = df["Census Year"].astype(int)
    state = df[(df["County"] == "State") & (df["measure"] == "population")].set_index("census_year")["value"]
    df = df[df["County"] != "State"].copy()
    df["county"] = df["County"].map(ref.standardise_county)
    bad = df["county"].isna().sum()
    if report is not None:
        report.add(ds, "county names standardised", "pass" if bad == 0 else "warning", int(bad), "all names map to the 26 counties")
    wide = df.pivot_table(index=["county", "census_year"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    sums = wide.groupby("census_year")["population"].sum()
    for y in (2011, 2016, 2022):
        reconcile(report, ds, f"{y}: sum of counties = State population", sums.get(y, np.nan), state.get(y, np.nan), tolerance=0.5)
    wide = check_duplicates(wide, ["county", "census_year"], ds, report)
    return wide[["county", "census_year", "population", "change_since_previous", "pct_change_since_previous"]]


def clean_population_national(pea01: pd.DataFrame, pea15: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """PEA01 + PEA15 -> national annual population estimate and components (thousands, April)."""
    ds = "PEA01/PEA15"
    a = pea01.copy()
    a["value"] = _num(a["VALUE"])
    a = a[(a["Age Group"] == "All ages") & (a["Sex"] == "Both sexes")][["Year", "value"]]
    a = a.rename(columns={"value": "population_thousand"})
    a["year"] = a.pop("Year").astype(int)
    b = pea15.copy()
    b["value"] = _num(b["VALUE"])
    comp = {"Annual births": "births_thousand", "Annual deaths": "deaths_thousand", "Natural increase": "natural_increase_thousand",
            "Immigrants": "immigrants_thousand", "Emigrants": "emigrants_thousand", "Net migration": "net_migration_thousand",
            "Population change": "population_change_thousand"}
    b = b[b["Component"].isin(comp)].copy()
    b["measure"] = b["Component"].map(comp)
    b["year"] = b["Year"].astype(int)
    bw = b.pivot_table(index="year", columns="measure", values="value", aggfunc="first").reset_index()
    bw.columns.name = None
    out = a.merge(bw, on="year", how="outer").sort_values("year")
    check_missing(out[out["year"] >= 2000], ["population_thousand"], ds, report)
    out = check_duplicates(out, ["year"], ds, report)
    if report is not None:
        report.add(ds, "reference period", "info", 0, f"April estimates {int(out['year'].min())}-{int(out['year'].max())}",
                   "latest year(s) are provisional CSO estimates")
    return out.reset_index(drop=True)


def clean_households(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """F2001 -> county, census_year, households, persons_in_households, avg_household_size."""
    ds = "F2001"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df["measure"] = df["Persons per Household"].map({"Total private households": "households",
                                                     "All persons in private households": "persons_in_households"})
    df["census_year"] = df["Census Year"].astype(int)
    nat = df[df["County"] == "Ireland"]
    df = df[df["County"] != "Ireland"].copy()
    df["county"] = df["County"].map(ref.standardise_county)
    wide = df.pivot_table(index=["county", "census_year"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    exp = nat[(nat["measure"] == "households") & (nat["census_year"] == 2022)]["value"].sum()
    reconcile(report, ds, "2022: sum of counties = Ireland households", wide.loc[wide["census_year"] == 2022, "households"].sum(), exp, 0.5)
    wide["avg_household_size"] = (wide["persons_in_households"] / wide["households"]).round(3)
    wide = check_range(wide, "avg_household_size", 1.5, 5.0, ds, report)
    wide = check_duplicates(wide, ["county", "census_year"], ds, report)
    return wide[["county", "census_year", "households", "persons_in_households", "avg_household_size"]]


def clean_housing_stock(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """F2020 -> area_name, county, census_year, total_stock, occupied, temporarily_absent, vacant, holiday_home."""
    ds = "F2020"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df = df[(df[_stat_col(df)] == "Housing stock") & (df["Type of Private Household"] == "All households")]
    m = {"Total housing stock": "total_stock", "Occupied": "occupied", "Temporarily absent": "temporarily_absent",
         "Vacant house/apartment": "vacant", "Holiday home": "holiday_home"}
    df = df.assign(measure=df["Housing Stock"].map(m), census_year=df["CensusYear"].astype(int))
    nat = df[df["County and City"] == "State"]
    parts = df[df["County and City"] != "State"].copy()
    parts["area_name"] = parts["County and City"].map(lambda n: ref.standardise_la(n) or n)
    parts["county"] = parts["County and City"].map(ref.standardise_county)
    wide = parts.pivot_table(index=["area_name", "county", "census_year"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    exp = nat[(nat["measure"] == "total_stock") & (nat["census_year"] == 2022)]["value"].sum()
    reconcile(report, ds, "2022: sum of areas = State total housing stock", wide.loc[wide["census_year"] == 2022, "total_stock"].sum(), exp, 0.5)
    parts_sum = wide[["occupied", "temporarily_absent", "vacant", "holiday_home"]].sum(axis=1)
    diff = (wide["total_stock"] - parts_sum).abs()
    if report is not None:
        report.add(ds, "occupied+absent+vacant+holiday = total stock", "pass" if (diff <= 1).all() else "info", int((diff > 1).sum()),
                   f"max difference {diff.max():.0f} dwellings", "none (differences, if any, are other unoccupied categories)")
    wide["vacancy_rate_pct"] = (100 * wide["vacant"] / wide["total_stock"]).round(2)
    wide = check_duplicates(wide, ["area_name", "census_year"], ds, report)
    return wide[["area_name", "county", "census_year", "total_stock", "occupied", "temporarily_absent", "vacant",
                 "holiday_home", "vacancy_rate_pct"]]


def clean_tenure(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """F2004 -> county, census_year, tenure, households (all ages, all persons-per-room bands)."""
    ds = "F2004"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df = df[(df["Persons per room"] == "All households") & (df["Age Group of Reference Person"] == "All ages")]
    nat = df[df["County"] == "Ireland"]
    df = df[df["County"] != "Ireland"].copy()
    df["county"] = df["County"].map(ref.standardise_county)
    df = df.rename(columns={"Nature of Occupancy": "tenure", "Census Year": "census_year"})
    df["census_year"] = df["census_year"].astype(int)
    out = df[["county", "census_year", "tenure", "value"]].rename(columns={"value": "households"})
    out = check_duplicates(out, ["county", "census_year", "tenure"], ds, report)
    allt = out[out["tenure"] == "All types of occupancy"]["households"].sum()
    parts = out[~out["tenure"].isin(["All types of occupancy"])]["households"].sum()
    reconcile(report, ds, "tenure categories sum to all occupancy types", parts, allt, tolerance=1)
    exp = nat[nat["Nature of Occupancy"] == "All types of occupancy"]["value"].sum()
    reconcile(report, ds, "sum of counties = Ireland (all households)", allt, exp, tolerance=1)
    check_missing(out, ["households"], ds, report)
    return out.reset_index(drop=True)


# ----------------------------------------------------------------------------- vacancy
def clean_vacancy_estimates(raw: pd.DataFrame, dataset: str = "VAC14", report: Optional[QualityReport] = None) -> pd.DataFrame:
    """VAC14 / VAC23 -> la_name, county, year, quarter, vacant_dwellings, dwelling_stock, vacancy_rate_pct."""
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    m = {"Number of Vacant Dwellings": "vacant_dwellings", "Dwelling Stock (ESB residential connections)": "dwelling_stock",
         "Vacancy Rate": "vacancy_rate_pct"}
    df["measure"] = df[_stat_col(df)].map(m)
    df = pd.concat([df, _quarter_parts(df["Quarter"])], axis=1)
    df = _map_la(df, "Local Authority", dataset, report).dropna(subset=["la_name"])
    wide = df.pivot_table(index=["la_name", "county", "year", "quarter"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    calc = 100 * wide["vacant_dwellings"] / wide["dwelling_stock"]
    gap = (calc - wide["vacancy_rate_pct"]).abs()
    if report is not None:
        report.add(dataset, "published vacancy rate = vacant / stock", "pass" if gap.max() < 0.06 else "warning", int((gap >= 0.06).sum()),
                   f"max difference {gap.max():.3f} percentage points (rounding)")
    wide = check_range(wide, "vacancy_rate_pct", 0, 30, dataset, report)
    wide = check_duplicates(wide, ["la_name", "year", "quarter"], dataset, report)
    return wide[["la_name", "county", "year", "quarter", "vacant_dwellings", "dwelling_stock", "vacancy_rate_pct"]].reset_index(drop=True)


def clean_vacancy_reasons(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """F2014 -> la_name, county, reason, vacant_dwellings (Census 2022)."""
    ds = "F2014"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df = df.rename(columns={"Reason for Vacancy": "reason"})
    nat = df[df["Administrative Counties"].map(ref.is_national)]
    parts = _map_la(df[~df["Administrative Counties"].map(ref.is_national)], "Administrative Counties", ds, report)
    parts = parts.dropna(subset=["la_name"])
    detail = parts[parts["reason"] != "Total vacancies"]
    reconcile(report, ds, "reasons sum to total vacancies",
              detail["value"].sum(), parts[parts["reason"] == "Total vacancies"]["value"].sum(), tolerance=1)
    reconcile(report, ds, "sum of local authorities = Ireland total vacancies",
              parts[parts["reason"] == "Total vacancies"]["value"].sum(), nat[nat["reason"] == "Total vacancies"]["value"].sum(), tolerance=1)
    out = detail.rename(columns={"value": "vacant_dwellings"})[["la_name", "county", "reason", "vacant_dwellings"]]
    out = check_duplicates(out, ["la_name", "reason"], ds, report)
    return out.reset_index(drop=True)


# ----------------------------------------------------------------------------- affordability
def clean_rents(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """RIQ02 -> location, county, geography_type, year, quarter, bedrooms, property_type, avg_monthly_rent."""
    ds = "RIQ02"
    df = raw.copy()
    df["avg_monthly_rent"] = _num(df["VALUE"])
    df = pd.concat([df, _quarter_parts(df["Quarter"])], axis=1)
    df = df.rename(columns={"Location": "location", "Number of Bedrooms": "bedrooms", "Property Type": "property_type"})
    is_city = df["location"].map(lambda x: ref._fold(x) in ref.CITY_KEYS)
    df["geography_type"] = np.where(is_city, "city", "county")
    # city-level locations (e.g. 'Kilkenny City') belong to the county of the same name
    df["county"] = df["location"].map(lambda x: ref.standardise_county(re.sub(r"\s+City$", "", x)))
    unknown = df["county"].isna().sum()
    if report is not None:
        report.add(ds, "location names standardised", "pass" if unknown == 0 else "warning", int(unknown),
                   "31 locations: 26 counties + 5 city-level areas")
    n_missing = int(df["avg_monthly_rent"].isna().sum())
    if report is not None:
        report.add(ds, "missing values in 'avg_monthly_rent'", "info", n_missing,
                   "no published average for that location/bedroom/property-type/quarter combination (small samples)",
                   "rows removed from the analytical table; absence is NOT treated as zero")
    df = df.dropna(subset=["avg_monthly_rent"])
    df = check_range(df, "avg_monthly_rent", 150, 6000, ds, report)
    out = df[["location", "county", "geography_type", "year", "quarter", "bedrooms", "property_type", "avg_monthly_rent"]]
    out = check_duplicates(out, ["location", "year", "quarter", "bedrooms", "property_type"], ds, report)
    if report is not None:
        report.add(ds, "reporting period", "info", 0, f"quarterly {int(out['year'].min())}Q{int(out.loc[out['year'].idxmin(),'quarter'])} to "
                   f"{int(out['year'].max())}Q{int(out[out['year'] == out['year'].max()]['quarter'].max())}",
                   "RTB figures describe standardised average rents for tenancies registered in the quarter")
    return out.reset_index(drop=True)


def clean_property_prices(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """HPM09 -> geography, dwelling_type, period, rppi_index, pct_change_1m/3m/12m."""
    ds = "HPM09"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    stat = {"Residential Property Price Index": "rppi_index",
            "Percentage Change over 1 month for Residential Property Price Index": "pct_change_1m",
            "Percentage Change over 3 months for Residential Property Price Index": "pct_change_3m",
            "Percentage Change over 12 months for Residential Property Price Index": "pct_change_12m"}
    df["measure"] = df[_stat_col(df)].map(stat)
    split = df["Type of Residential Property"].str.split(" - ", n=1, expand=True)
    df["geography"] = split[0].str.strip()
    df["dwelling_type"] = split[1].str.strip()
    df["period"] = pd.to_datetime(df["Month"], format="%Y %B")
    wide = df.pivot_table(index=["geography", "dwelling_type", "period"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    n_missing = int(wide["rppi_index"].isna().sum())
    if report is not None:
        report.add(ds, "missing values in 'rppi_index'", "info", n_missing,
                   "index not published for some sub-national series in early years", "rows without an index removed")
    wide = wide.dropna(subset=["rppi_index"])
    wide = check_range(wide, "rppi_index", 20, 400, ds, report)
    wide = check_duplicates(wide, ["geography", "dwelling_type", "period"], ds, report)
    if report is not None:
        report.add(ds, "measure", "info", 0, "index (base 2015=100) - not euro prices; county euro prices are not published by the CSO")
    return wide[["geography", "dwelling_type", "period", "rppi_index", "pct_change_1m", "pct_change_3m", "pct_change_12m"]].reset_index(drop=True)


def clean_income(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """RAA02 -> (county table, national table): disposable income per person etc."""
    ds = "RAA02"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    stat = {"Disposable Income per Person": "disposable_income_per_person",
            "Total Income per Person": "total_income_per_person",
            "Disposable Household Income": "disposable_household_income_m",
            "Total Household Income": "total_household_income_m"}
    df["measure"] = df[_stat_col(df)].map(stat)
    df = df.dropna(subset=["measure"])
    df["year"] = df["Year"].astype(int)
    df["geo"] = df["County"].map(lambda c: "Ireland" if ref.is_national(c) else ref.standardise_county(c))
    wide = df.pivot_table(index=["geo", "year"], columns="measure", values="value", aggfunc="first").reset_index().rename(columns={"geo": "county"})
    wide.columns.name = None
    national = wide[wide["county"] == "Ireland"].drop(columns="county")
    counties = wide[wide["county"] != "Ireland"].copy()
    counties = check_range(counties, "disposable_income_per_person", 5000, 80000, ds, report)
    counties = check_duplicates(counties, ["county", "year"], ds, report)
    check_missing(counties, ["disposable_income_per_person"], ds, report)
    reconcile(report, ds, "2022: sum of county disposable household income = Ireland (EUR m)",
              counties.loc[counties["year"] == 2022, "disposable_household_income_m"].sum(),
              national.loc[national["year"] == 2022, "disposable_household_income_m"].sum(), tolerance=5)
    return counties.reset_index(drop=True), national.reset_index(drop=True)


def clean_rent_to_income(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """TRS38 -> la_name, county, year, median_rent_pct_income, pct_tenants_40plus, ..._45plus, ..._50plus."""
    ds = "TRS38"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    def label(s: str) -> str:
        if s.startswith("Median"):
            return "median_rent_pct_income"
        for t in ("40", "45", "50"):
            if f"{t}% or More" in s:
                return f"pct_tenants_{t}plus"
        return "other"
    df["measure"] = df[_stat_col(df)].map(label)
    df = _map_la(df, "Local Authority", ds, report).dropna(subset=["la_name"])
    df["year"] = df["Rental Year"].astype(int)
    wide = df.pivot_table(index=["la_name", "county", "year"], columns="measure", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    wide = check_range(wide, "median_rent_pct_income", 0, 100, ds, report)
    wide = check_duplicates(wide, ["la_name", "year"], ds, report)
    check_missing(wide, ["median_rent_pct_income"], ds, report)
    return wide[["la_name", "county", "year", "median_rent_pct_income", "pct_tenants_40plus", "pct_tenants_45plus", "pct_tenants_50plus"]]


# ----------------------------------------------------------------------------- social / homelessness
def clean_social_need(raw: pd.DataFrame, report: Optional[QualityReport] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SCA10 -> (county table, national table) of households with children in need of social housing."""
    ds = "SCA10"
    df = raw.copy()
    df["value"] = _num(df["VALUE"])
    df = df[(df["Household Structure"] == "All households with children") & (df["Number of Children"] == "All households with children")]
    df["year"] = df["Year"].astype(int)
    nat = df[df["County"] == "All Counties"]
    national = nat[["year", "value"]].rename(columns={"value": "households_with_children_in_need"}).dropna()
    df = df[df["County"] != "All Counties"].copy()
    df["county"] = df["County"].map(ref.standardise_county)
    out = df[["county", "year", "value"]].rename(columns={"value": "households_with_children_in_need"})
    years_missing = sorted(out.groupby("year")["households_with_children_in_need"].apply(lambda s: s.isna().all()).loc[lambda s: s].index)
    if report is not None:
        report.add(ds, "years without county breakdown", "info", len(years_missing),
                   f"county values not published for {years_missing}; only the national total exists for those years",
                   "county table restricted to years with county data; national totals kept separately")
    out = out.dropna(subset=["households_with_children_in_need"])
    s = out.groupby("year")["households_with_children_in_need"].sum()
    for y in sorted(s.index):
        e = national.loc[national["year"] == y, "households_with_children_in_need"].sum()
        reconcile(report, ds, f"{y}: sum of counties = All Counties", s[y], e, tolerance=1, fail_status="info",
                  note="Published All-Counties total differs from the sum of county values in the source; "
                       "county values are used for county analysis, the All-Counties total for the national trend.")
    out = check_duplicates(out, ["county", "year"], ds, report)
    if report is not None:
        report.add(ds, "coverage", "info", 0, "households with children only; excludes single adults and couples without children",
                   "labelled as 'families with children' everywhere it is displayed")
    return out.reset_index(drop=True), national.reset_index(drop=True)


_HOMELESS_RENAME = {
    "Region": "region", "Total Adults": "adults_total", "Number of single adults": "single_adults",
    "Male Adults": "adults_male", "Female Adults": "adults_female",
    "Adults Aged 18-24": "adults_18_24", "Adults Aged 25-44": "adults_25_44", "Adults Aged 45-64": "adults_45_64", "Adults Aged 65+": "adults_65_plus",
    "Number of people who accessed Private Emergency Accommodation": "private_emergency",
    "Number of people who accessed Supported Temporary Accommodation": "supported_temporary",
    "Number of people who accessed Temporary Emergency Accommodation": "temporary_emergency",
    "Number of people who accessed Other Accommodation": "other_accommodation",
    "Number of Families": "families", "Number of Adults in Families": "adults_in_families",
    "Number of Single-Parent families": "single_parent_families",
    "Number of Dependants in Families": "dependants", "Number of Child Dependants in Families": "dependants",
}
_HOMELESS_REGION = {"dublin": "Dublin", "mid east": "Mid-East", "midlands": "Midlands", "mid west": "Mid-West",
                    "north east": "North-East", "north west": "North-West", "south east": "South-East",
                    "south west": "South-West", "west": "West"}
_MONTHS = {m.lower(): i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                               "August", "September", "October", "November", "December"], 1)}


def parse_homeless_month(filename: str) -> pd.Timestamp:
    m = re.search(r"homelessness-report-([a-z]+)-(\d{4})", filename.lower())
    if not m or m.group(1) not in _MONTHS:
        raise ValueError(f"cannot parse report month from {filename}")
    return pd.Timestamp(year=int(m.group(2)), month=_MONTHS[m.group(1)], day=1)


def clean_homelessness(directory: Path | str, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """Monthly Dept. of Housing homelessness reports -> one tidy table (region x month)."""
    ds = "HOMELESSNESS_MONTHLY"
    directory = Path(directory)
    files = sorted(directory.glob("homelessness-report-*.csv"))
    if not files:
        raise FileNotFoundError(f"no homelessness CSVs in {directory}; run the downloader")
    frames, problems = [], []
    for f in files:
        try:
            # some reports write thousands as "4,258": parse them as numbers instead of silently losing them
            d = pd.read_csv(f, encoding="utf-8-sig", thousands=",")
            d = d.rename(columns=lambda c: _HOMELESS_RENAME.get(c.strip(), c.strip()))
            d["report_month"] = parse_homeless_month(f.name)
            frames.append(d)
        except Exception as exc:  # unreadable file: record and continue
            problems.append(f"{f.name}: {exc}")
    if problems and report is not None:
        report.add(ds, "unreadable files", "warning", len(problems), "; ".join(problems[:3]), "skipped")
    df = pd.concat(frames, ignore_index=True, sort=False)
    df["region"] = df["region"].map(lambda r: _HOMELESS_REGION.get(ref._fold(r)))
    dropped = int(df["region"].isna().sum())
    if report is not None:
        report.add(ds, "non-region rows (totals) removed", "info" if dropped else "pass", dropped, "regions standardised to 9 Dept. regions")
    df = df.dropna(subset=["region"])
    numeric = [c for c in df.columns if c not in ("region", "report_month")]
    before_na = int(df[numeric].isna().sum().sum())
    df[numeric] = df[numeric].apply(lambda s: pd.to_numeric(s.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")
                                    if s.dtype == object else s)
    if report is not None:
        lost = int(df[numeric].isna().sum().sum()) - before_na
        report.add(ds, "values lost during numeric conversion", "pass" if lost == 0 else "warning", lost,
                   "thousands separators (e.g. '4,258') are parsed; no value is silently dropped")
    df["total_persons"] = df["adults_total"] + df["dependants"]
    df = check_duplicates(df, ["region", "report_month"], ds, report)
    df = check_range(df, "adults_total", 0, 20000, ds, report)
    per_month = df.groupby("report_month")["region"].nunique()
    if report is not None:
        report.add(ds, "9 regions in every month", "pass" if (per_month == 9).all() else "warning", int((per_month != 9).sum()),
                   f"{len(per_month)} monthly reports {per_month.index.min():%Y-%m} to {per_month.index.max():%Y-%m}")
        full = pd.date_range(per_month.index.min(), per_month.index.max(), freq="MS")
        gaps = [d.strftime("%Y-%m") for d in full if d not in per_month.index]
        report.add(ds, "month gaps", "pass" if not gaps else "info", len(gaps), f"missing months: {gaps}" if gaps else "contiguous monthly series",
                   "" if not gaps else "gaps are left as gaps")
        national = df.groupby("report_month")["total_persons"].sum().sort_index()
        jump = national.pct_change().abs()
        big = jump[jump > 0.20]
        report.add(ds, "month-on-month anomaly check (national total, >20% jump)", "pass" if big.empty else "warning", len(big),
                   "no implausible month-to-month jumps" if big.empty else f"jumps at {[d.strftime('%Y-%m') for d in big.index]}",
                   "" if big.empty else "investigate source layout changes")
        report.add(ds, "column harmonisation", "info", 0, "report layouts changed over time (e.g. citizenship columns added 2022; 'Child Dependants' renamed)",
                   "common columns harmonised; optional columns kept where present")
    keep = ["region", "report_month", "adults_total", "adults_male", "adults_female", "adults_18_24", "adults_25_44", "adults_45_64",
            "adults_65_plus", "private_emergency", "supported_temporary", "temporary_emergency", "other_accommodation",
            "families", "adults_in_families", "single_parent_families", "dependants", "total_persons"]
    for c in keep:
        if c not in df.columns:
            df[c] = np.nan
    return df[keep].sort_values(["report_month", "region"]).reset_index(drop=True)
