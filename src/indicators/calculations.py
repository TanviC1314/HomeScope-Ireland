"""Housing indicator calculations.

All functions are pure: they take the dictionary of processed tables (``Tables``) and return tidy
DataFrames.  No hidden state, no database access - so every number on the dashboard can be
reproduced and unit-tested.  Definitions, sources, assumptions and limitations of each indicator
are documented in ``registry.py``.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

Tables = Dict[str, pd.DataFrame]

ALL_BEDROOMS = "All bedrooms"
ALL_PROPERTY = "All property types"


# ------------------------------------------------------------------------------------ supply
def annual_completions(t: Tables, by: str = "county") -> pd.DataFrame:
    """Completions per calendar year with quarters reported and a partial-year flag.

    ``by`` in {"county", "la", "national", "nuts3"}.
    """
    c = t["completions_quarterly"].copy()
    if by == "nuts3":
        c = c.merge(t["dim_county"][["county", "nuts3_region"]], on="county", how="left")
        key = ["nuts3_region"]
    elif by == "national":
        key = []
    else:
        key = ["county"] if by == "county" else ["la_name"]
    keys = key + ["year"]
    out = (c.groupby(keys).agg(completions=("completions", "sum"), quarters_reported=("quarter", "nunique")).reset_index())
    out["is_partial_year"] = out["quarters_reported"] < 4
    return out


def latest_full_year(t: Tables) -> int:
    nat = annual_completions(t, "national")
    return int(nat.loc[~nat["is_partial_year"], "year"].max())


def national_supply_growth(t: Tables) -> pd.DataFrame:
    """National completions and year-on-year change (only between two full years)."""
    nat = annual_completions(t, "national").sort_values("year").reset_index(drop=True)
    prev = nat["completions"].shift(1)
    both_full = (~nat["is_partial_year"]) & (~nat["is_partial_year"].shift(1, fill_value=True))
    nat["yoy_change_pct"] = np.where(both_full, 100 * (nat["completions"] - prev) / prev, np.nan)
    return nat


def completions_per_1000(t: Tables, years: Tuple[int, int] | None = None) -> pd.DataFrame:
    """Average annual completions per 1,000 residents (Census 2022 population) over ``years`` (inclusive, full years only)."""
    ac = annual_completions(t, "county")
    ac = ac[~ac["is_partial_year"]]
    if years is None:
        ly = latest_full_year(t)
        years = (ly - 2, ly)
    sel = ac[ac["year"].between(*years)]
    avg = sel.groupby("county").agg(total_completions=("completions", "sum"), years_used=("year", "nunique")).reset_index()
    avg["avg_annual_completions"] = avg["total_completions"] / avg["years_used"]
    pop = t["population_census"].query("census_year == 2022")[["county", "population"]]
    out = avg.merge(pop, on="county")
    out["completions_per_1000"] = 1000 * out["avg_annual_completions"] / out["population"]
    out.attrs["years"] = years
    return out


def commencements_annual(t: Tables, by: str = "national") -> pd.DataFrame:
    c = t["commencements_monthly"]
    keys = ["year"] if by == "national" else ["county", "year"]
    out = c.groupby(keys).agg(units=("units", "sum"), notices=("notices", "sum"), months_reported=("month", "nunique")).reset_index()
    out["is_partial_year"] = out["months_reported"] < 12
    return out


def planning_vs_completions(t: Tables, lag: int = 0, year_from: int = 2015, year_to: Optional[int] = None) -> pd.DataFrame:
    """Planning permissions (units, NUTS3 region) compared with completions.

    ``lag`` shifts permissions forward: with lag=2, completions in year Y are compared with units
    permitted in Y-2.  This is a *simple comparison ratio*, not a conversion rate.
    """
    comp = annual_completions(t, "nuts3").rename(columns={"nuts3_region": "region"})
    plan = (t["planning_permissions"].groupby(["region", "year"], as_index=False)["units"].sum().rename(columns={"units": "permitted_units"}))
    plan["year"] = plan["year"] + lag
    out = comp.merge(plan, on=["region", "year"], how="inner")
    out = out[(out["year"] >= year_from) & (~out["is_partial_year"])]
    if year_to:
        out = out[out["year"] <= year_to]
    out["completions_to_permitted"] = out["completions"] / out["permitted_units"]
    out.attrs["lag"] = lag
    return out.sort_values(["year", "region"]).reset_index(drop=True)


def planning_vs_completions_window(t: Tables, start: int, end: int, lag: int = 0) -> pd.DataFrame:
    """Cumulative completions vs cumulative permitted units for ``start..end`` completions years."""
    df = planning_vs_completions(t, lag=lag, year_from=start, year_to=end)
    out = df.groupby("region").agg(completions=("completions", "sum"), permitted_units=("permitted_units", "sum")).reset_index()
    out["completions_to_permitted"] = out["completions"] / out["permitted_units"]
    return out


# ------------------------------------------------------------------------------------ demand
def census_growth(t: Tables, y0: int = 2016, y1: int = 2022) -> pd.DataFrame:
    """County population, household and housing-stock growth between two Census years (all measured values)."""
    pop = t["population_census"].pivot(index="county", columns="census_year", values="population")
    hh = t["households_census"].pivot(index="county", columns="census_year", values="households")
    st = t["housing_stock_census"].groupby(["county", "census_year"])["total_stock"].sum().unstack()
    out = pd.DataFrame({
        "population_start": pop[y0], "population_end": pop[y1],
        "households_start": hh[y0], "households_end": hh[y1],
        "stock_start": st[y0], "stock_end": st[y1],
    })
    out["population_growth_pct"] = 100 * (out["population_end"] / out["population_start"] - 1)
    out["household_growth_pct"] = 100 * (out["households_end"] / out["households_start"] - 1)
    out["stock_growth_pct"] = 100 * (out["stock_end"] / out["stock_start"] - 1)
    out["households_added"] = out["households_end"] - out["households_start"]
    out["stock_added"] = out["stock_end"] - out["stock_start"]
    out["household_minus_stock_growth_pp"] = out["household_growth_pct"] - out["stock_growth_pct"]
    out["annual_household_growth"] = out["households_added"] / (y1 - y0)
    return out.reset_index()


def national_population(t: Tables) -> pd.DataFrame:
    n = t["population_national"].sort_values("year").copy()
    n["population_growth_pct"] = 100 * n["population_thousand"].pct_change()
    return n


# ------------------------------------------------------------------------------------ affordability
def rent_series(t: Tables, bedrooms: str = ALL_BEDROOMS, property_type: str = ALL_PROPERTY,
                geography_type: str = "county") -> pd.DataFrame:
    r = t["rents_rtb"]
    r = r[(r["bedrooms"] == bedrooms) & (r["property_type"] == property_type) & (r["geography_type"] == geography_type)].copy()
    r["period_label"] = r["year"].astype(str) + "Q" + r["quarter"].astype(str)
    r["period"] = pd.PeriodIndex(r["period_label"], freq="Q").to_timestamp(how="end").normalize()
    return r.sort_values(["location", "year", "quarter"]).reset_index(drop=True)


def latest_rent_period(t: Tables) -> Tuple[int, int]:
    r = t["rents_rtb"]
    y = int(r["year"].max())
    return y, int(r.loc[r["year"] == y, "quarter"].max())


def rent_change(t: Tables, base: Tuple[int, int] = (2019, 4), latest: Optional[Tuple[int, int]] = None,
                bedrooms: str = ALL_BEDROOMS, property_type: str = ALL_PROPERTY) -> pd.DataFrame:
    latest = latest or latest_rent_period(t)
    s = rent_series(t, bedrooms, property_type)
    b = s[(s["year"] == base[0]) & (s["quarter"] == base[1])][["county", "avg_monthly_rent"]].rename(columns={"avg_monthly_rent": "rent_base"})
    c = s[(s["year"] == latest[0]) & (s["quarter"] == latest[1])][["county", "avg_monthly_rent"]].rename(columns={"avg_monthly_rent": "rent_latest"})
    prev = s[(s["year"] == latest[0] - 1) & (s["quarter"] == latest[1])][["county", "avg_monthly_rent"]].rename(columns={"avg_monthly_rent": "rent_year_earlier"})
    out = b.merge(c, on="county").merge(prev, on="county", how="left")
    out["change_since_base_pct"] = 100 * (out["rent_latest"] / out["rent_base"] - 1)
    out["change_1y_pct"] = 100 * (out["rent_latest"] / out["rent_year_earlier"] - 1)
    out["change_since_base_eur"] = out["rent_latest"] - out["rent_base"]
    out.attrs.update(base=base, latest=latest)
    return out.sort_values("change_since_base_pct", ascending=False).reset_index(drop=True)


def national_rent_proxy(t: Tables, bedrooms: str = ALL_BEDROOMS, property_type: str = ALL_PROPERTY) -> pd.DataFrame:
    """Derived national rent series: county RTB averages weighted by Census 2022 private-rented households.

    The RTB/CSO table publishes no national average, so this is a transparent *derived estimate*.
    """
    s = rent_series(t, bedrooms, property_type)
    w = (t["tenure_census"].query("census_year == 2022 and tenure == 'Rented from private landlord'")[["county", "households"]]
         .rename(columns={"households": "weight"}))
    m = s.merge(w, on="county")
    rows = []
    for (year, quarter, period, label), d in m.groupby(["year", "quarter", "period", "period_label"]):
        rows.append({"year": year, "quarter": quarter, "period": period, "period_label": label,
                     "avg_monthly_rent": np.average(d["avg_monthly_rent"], weights=d["weight"]), "counties": d["county"].nunique()})
    g = pd.DataFrame(rows)
    # keep only quarters where all counties report, so the weighted mean is comparable over time
    return g[g["counties"] == g["counties"].max()].sort_values(["year", "quarter"]).reset_index(drop=True)


def property_price_series(t: Tables, geography: str = "National", dwelling_type: str = "all residential properties") -> pd.DataFrame:
    p = t["property_price_index"]
    return p[(p["geography"] == geography) & (p["dwelling_type"] == dwelling_type)].sort_values("period").reset_index(drop=True)


def property_price_summary(t: Tables, geography: str = "National", dwelling_type: str = "all residential properties") -> dict:
    s = property_price_series(t, geography, dwelling_type)
    last = s.iloc[-1]
    peak = s.loc[s.loc[s["period"] < "2015-01-01", "rppi_index"].idxmax()] if (s["period"] < "2015-01-01").any() else None
    return {"latest_period": last["period"], "latest_index": float(last["rppi_index"]), "change_12m_pct": float(last["pct_change_12m"]),
            "index_vs_2015_pct": float(last["rppi_index"] - 100),
            "prior_peak_index": float(peak["rppi_index"]) if peak is not None else None,
            "prior_peak_period": peak["period"] if peak is not None else None,
            "index_vs_prior_peak_pct": float(100 * (last["rppi_index"] / peak["rppi_index"] - 1)) if peak is not None else None}


def rent_to_income_la(t: Tables) -> pd.DataFrame:
    return t["rent_to_income_la"].sort_values("median_rent_pct_income", ascending=False).reset_index(drop=True)


def rent_to_income_county(t: Tables) -> pd.DataFrame:
    """County rent-to-income (CSO/RTB 2024 medians by local authority) weighted by dwelling stock.

    Weighting by dwelling stock is a proxy for tenant numbers (not published by local authority here).
    """
    vac = t["vacancy_estimates"]
    stock = vac[(vac["year"] == vac["year"].max()) & (vac["quarter"] == 4)][["la_name", "dwelling_stock"]]
    m = t["rent_to_income_la"].merge(stock, on="la_name")
    rows = []
    for county, d in m.groupby("county"):
        rows.append({"county": county,
                     "median_rent_pct_income": np.average(d["median_rent_pct_income"], weights=d["dwelling_stock"]),
                     "pct_tenants_40plus": np.average(d["pct_tenants_40plus"], weights=d["dwelling_stock"]),
                     "local_authorities": len(d)})
    return pd.DataFrame(rows).sort_values("median_rent_pct_income", ascending=False).reset_index(drop=True)


def rent_vs_income_per_person(t: Tables, income_year: Optional[int] = None) -> pd.DataFrame:
    """Annualised average rent compared with disposable income per person (relative indicator only).

    Per-person income understates household income, so the level overstates the burden; use it to
    compare counties with each other, not as an absolute affordability threshold.
    """
    inc = t["household_income_county"]
    income_year = income_year or int(inc["year"].max())
    inc = inc[inc["year"] == income_year][["county", "disposable_income_per_person"]]
    ly, lq = latest_rent_period(t)
    rent = rent_series(t)
    rent = rent[(rent["year"] == ly) & (rent["quarter"] == lq)][["county", "avg_monthly_rent"]]
    out = rent.merge(inc, on="county")
    out["annual_rent"] = 12 * out["avg_monthly_rent"]
    out["annual_rent_pct_of_income_per_person"] = 100 * out["annual_rent"] / out["disposable_income_per_person"]
    out.attrs.update(income_year=income_year, rent_period=(ly, lq))
    return out.sort_values("annual_rent_pct_of_income_per_person", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------------------ vacancy
def vacancy_by_county(t: Tables, year: Optional[int] = None) -> pd.DataFrame:
    """ESB-based vacancy (VAC14) aggregated to county from local-authority counts (sums, not averages of rates)."""
    v = t["vacancy_estimates"]
    year = year or int(v["year"].max())
    d = v[(v["year"] == year) & (v["quarter"] == 4)]
    out = d.groupby("county").agg(vacant_dwellings=("vacant_dwellings", "sum"), dwelling_stock=("dwelling_stock", "sum")).reset_index()
    lt = t["long_term_vacancy"]
    lt = lt[(lt["year"] == int(lt["year"].max()))].groupby("county")["vacant_dwellings"].sum().rename("long_term_vacant").reset_index()
    out = out.merge(lt, on="county", how="left")
    out["vacancy_rate_pct"] = 100 * out["vacant_dwellings"] / out["dwelling_stock"]
    out["long_term_share_pct"] = 100 * out["long_term_vacant"] / out["vacant_dwellings"]
    out["long_term_rate_pct"] = 100 * out["long_term_vacant"] / out["dwelling_stock"]
    out.attrs["year"] = year
    return out.sort_values("vacancy_rate_pct", ascending=False).reset_index(drop=True)


def vacancy_trend_national(t: Tables) -> pd.DataFrame:
    v = t["vacancy_estimates"]
    g = v.groupby("year").agg(vacant_dwellings=("vacant_dwellings", "sum"), dwelling_stock=("dwelling_stock", "sum")).reset_index()
    g["vacancy_rate_pct"] = 100 * g["vacant_dwellings"] / g["dwelling_stock"]
    return g


def vacancy_by_la(t: Tables, year: Optional[int] = None) -> pd.DataFrame:
    v = t["vacancy_estimates"]
    year = year or int(v["year"].max())
    d = v[(v["year"] == year) & (v["quarter"] == 4)].copy()
    lt = t["long_term_vacancy"][["la_name", "vacant_dwellings"]].rename(columns={"vacant_dwellings": "long_term_vacant"})
    d = d.merge(lt, on="la_name", how="left")
    d["long_term_share_pct"] = 100 * d["long_term_vacant"] / d["vacant_dwellings"]
    return d.sort_values("vacancy_rate_pct", ascending=False).reset_index(drop=True)


def census_vacancy_by_county(t: Tables, year: int = 2022) -> pd.DataFrame:
    s = t["housing_stock_census"].query("census_year == @year").groupby("county").agg(
        total_stock=("total_stock", "sum"), vacant=("vacant", "sum"), holiday_home=("holiday_home", "sum")).reset_index()
    s["vacancy_rate_pct"] = 100 * s["vacant"] / s["total_stock"]
    s["holiday_home_pct"] = 100 * s["holiday_home"] / s["total_stock"]
    return s.sort_values("vacancy_rate_pct", ascending=False).reset_index(drop=True)


REASON_GROUPS = {
    "Renovation": "Needs work / probate", "Deceased": "Needs work / probate",
    "For Sale": "In market transition", "Rental Property": "In market transition", "New Build": "In market transition",
    "Nursing Home / Hospital": "Family or care circumstances", "With Relatives": "Family or care circumstances",
    "Farmhouse": "Other / not stated", "Emigrated": "Other / not stated", "Other reason / Not Stated": "Other / not stated",
}


def vacancy_reasons(t: Tables, county: Optional[str] = None) -> pd.DataFrame:
    """Census 2022 reasons for vacancy, optionally for one county, with an analytical reuse-pathway grouping."""
    r = t["vacancy_reasons_census"]
    if county:
        r = r[r["county"] == county]
    out = r.groupby("reason", as_index=False)["vacant_dwellings"].sum()
    out["reason_group"] = out["reason"].map(REASON_GROUPS)
    out["share_pct"] = 100 * out["vacant_dwellings"] / out["vacant_dwellings"].sum()
    return out.sort_values("vacant_dwellings", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------------------ social housing & homelessness
def social_need(t: Tables) -> pd.DataFrame:
    """Latest families with children in need of social housing per 1,000 households (county)."""
    n = t["social_housing_need"]
    year = int(n["year"].max())
    cur = n[n["year"] == year][["county", "households_with_children_in_need"]]
    base = n[n["year"] == 2017][["county", "households_with_children_in_need"]].rename(columns={"households_with_children_in_need": "need_2017"})
    hh = t["households_census"].query("census_year == 2022")[["county", "households"]]
    out = cur.merge(base, on="county", how="left").merge(hh, on="county")
    out["need_per_1000_households"] = 1000 * out["households_with_children_in_need"] / out["households"]
    out["change_since_2017_pct"] = 100 * (out["households_with_children_in_need"] / out["need_2017"] - 1)
    out.attrs["year"] = year
    return out.sort_values("need_per_1000_households", ascending=False).reset_index(drop=True)


def tenure_shares(t: Tables, year: int = 2022) -> pd.DataFrame:
    ten = t["tenure_census"].query("census_year == @year")
    p = ten.pivot(index="county", columns="tenure", values="households")
    out = pd.DataFrame({"all_households": p["All types of occupancy"],
                        "social_rented": p["Rented from a local authority"] + p["Rented from a voluntary body"],
                        "private_rented": p["Rented from private landlord"]}).reset_index()
    out["social_rented_pct"] = 100 * out["social_rented"] / out["all_households"]
    out["private_rented_pct"] = 100 * out["private_rented"] / out["all_households"]
    return out.sort_values("social_rented_pct", ascending=False).reset_index(drop=True)


def homelessness_national(t: Tables) -> pd.DataFrame:
    h = t["homelessness_monthly"]
    g = h.groupby("report_month").agg(total_persons=("total_persons", "sum"), adults=("adults_total", "sum"),
                                       families=("families", "sum"), dependants=("dependants", "sum")).reset_index()
    g = g.sort_values("report_month")
    g["yoy_change_pct"] = np.nan
    s = g.set_index("report_month")["total_persons"]
    prev = s.reindex(s.index - pd.DateOffset(years=1)).to_numpy()
    g["yoy_change_pct"] = 100 * (s.to_numpy() / prev - 1)
    return g


def homelessness_by_region(t: Tables, month: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    h = t["homelessness_monthly"]
    month = pd.Timestamp(month) if month is not None else h["report_month"].max()
    d = h[h["report_month"] == month].copy()
    pop = t["dim_county"].merge(t["population_census"].query("census_year == 2022"), on="county").groupby("homeless_region")["population"].sum().rename("population_2022").reset_index()
    d = d.merge(pop, left_on="region", right_on="homeless_region").drop(columns="homeless_region")
    d["persons_per_10000"] = 10000 * d["total_persons"] / d["population_2022"]
    d["share_of_national_pct"] = 100 * d["total_persons"] / d["total_persons"].sum()
    return d.sort_values("persons_per_10000", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------------------ pressure
PRESSURE_INDICATORS = [
    # column, label, direction ("high" = higher value means more pressure), source
    ("rent_latest", "Average monthly rent (latest quarter)", "high", "RTB via CSO RIQ02"),
    ("rent_change_since_2019_pct", "Rent change since Q4 2019 (%)", "high", "RTB via CSO RIQ02"),
    ("rent_pct_income", "Median rent as % of tenant disposable income (2024)", "high", "CSO/RTB TRS38"),
    ("completions_per_1000", "Avg annual completions per 1,000 residents (last 3 full years)", "low", "CSO NDQ06 + Census 2022"),
    ("household_minus_stock_growth_pp", "Household growth minus housing stock growth, 2016-22 (pp)", "high", "Census 2016/2022"),
    ("need_per_1000_households", "Families with children needing social housing per 1,000 households", "high", "CSO SCA10 + Census 2022"),
]


def housing_pressure_table(t: Tables) -> pd.DataFrame:
    """County table of six transparent indicators and a count of 'pressure flags'.

    A flag is raised when a county sits in the most-pressured quartile of the 26 counties for an
    indicator (top quartile when higher = worse, bottom quartile when lower = worse).  There are no
    weights and no composite score: the flag count is simply "in how many of the six indicators is
    this county among the most pressured?".
    """
    rc = rent_change(t)[["county", "rent_latest", "change_since_base_pct"]].rename(columns={"change_since_base_pct": "rent_change_since_2019_pct"})
    ri = rent_to_income_county(t)[["county", "median_rent_pct_income"]].rename(columns={"median_rent_pct_income": "rent_pct_income"})
    cp = completions_per_1000(t)[["county", "completions_per_1000"]]
    cg = census_growth(t)[["county", "household_minus_stock_growth_pp"]]
    sn = social_need(t)[["county", "need_per_1000_households"]]
    df = rc.merge(ri, on="county").merge(cp, on="county").merge(cg, on="county").merge(sn, on="county")
    flags = pd.DataFrame(index=df.index)
    for col, _, direction, _ in PRESSURE_INDICATORS:
        rank = df[col].rank(pct=True, method="average")
        flags[col] = (rank > 0.75) if direction == "high" else (rank <= 0.25)
    df["pressure_flags"] = flags.sum(axis=1).astype(int)
    for col in flags:
        df[f"flag_{col}"] = flags[col]
    return df.sort_values(["pressure_flags", "rent_latest"], ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------------------ national KPI bundle
def national_kpis(t: Tables) -> dict:
    """Headline numbers for the National Overview page (each tied to a documented indicator)."""
    ly = latest_full_year(t)
    sg = national_supply_growth(t).set_index("year")
    nat = annual_completions(t, "national").set_index("year")
    pop = national_population(t)
    pop_latest = pop.iloc[-1]
    vac = vacancy_trend_national(t).iloc[-1]
    price = property_price_summary(t, "National")
    rent = national_rent_proxy(t)
    r_last, r_prev = rent.iloc[-1], rent[(rent["year"] == rent.iloc[-1]["year"] - 1) & (rent["quarter"] == rent.iloc[-1]["quarter"])].iloc[0]
    hl = homelessness_national(t).iloc[-1]
    return {
        "latest_full_year": ly,
        "completions_latest_full_year": int(nat.loc[ly, "completions"]),
        "completions_yoy_pct": float(sg.loc[ly, "yoy_change_pct"]),
        "completions_ytd_year": int(nat.index.max()), "completions_ytd": int(nat.loc[nat.index.max(), "completions"]),
        "population_year": int(pop_latest["year"]), "population_thousand": float(pop_latest["population_thousand"]),
        "population_growth_pct": float(pop_latest["population_growth_pct"]),
        "net_migration_thousand": float(pop_latest["net_migration_thousand"]),
        "rent_proxy": float(r_last["avg_monthly_rent"]), "rent_period": r_last["period_label"],
        "rent_yoy_pct": float(100 * (r_last["avg_monthly_rent"] / r_prev["avg_monthly_rent"] - 1)),
        "price_index": price["latest_index"], "price_period": price["latest_period"], "price_yoy_pct": price["change_12m_pct"],
        "vacancy_year": int(vac["year"]), "vacant_dwellings": int(vac["vacant_dwellings"]), "vacancy_rate_pct": float(vac["vacancy_rate_pct"]),
        "homeless_month": hl["report_month"], "homeless_persons": int(hl["total_persons"]), "homeless_yoy_pct": float(hl["yoy_change_pct"]),
    }
