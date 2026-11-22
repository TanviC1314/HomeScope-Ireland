"""Automatic, data-driven insights.

Every insight is computed from the processed tables at run time: nothing is hard-coded or invented.
Each insight states (1) what the data show, (2) where/when, (3) why it matters and (4) a possible
intervention or area for further investigation.  The wording of (3) and (4) is deliberately cautious:
the data identify *patterns*, they do not prove causes.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.indicators import calculations as calc

Tables = Dict[str, pd.DataFrame]


@dataclass
class Insight:
    id: str
    theme: str                 # Supply | Affordability | Vacancy | Social housing | Homelessness | Demand | Pressure
    indicator: str             # registry id of the main indicator
    headline: str              # what the data shows
    location: str              # where
    period: str                # when
    why_it_matters: str
    next_step: str             # possible intervention / area for further investigation
    year: int                  # reference year (for filtering)
    counties: List[str] = field(default_factory=list)
    kind: str = "published"    # published | derived | estimate
    sources: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _fmt(n: float, d: int = 0) -> str:
    return f"{n:,.{d}f}"


def _names(items, k=3) -> str:
    items = list(items)[:k]
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else (items[0] if items else "")


# ------------------------------------------------------------------------------------ individual insights
def _completions(t: Tables) -> Optional[Insight]:
    g = calc.national_supply_growth(t)
    ly = calc.latest_full_year(t)
    full = g[~g["is_partial_year"]].set_index("year")
    low = full.loc[2012:ly, "completions"].idxmin()
    cur = int(full.loc[ly, "completions"])
    cty = calc.annual_completions(t, "county")
    dub = int(cty[(cty["county"] == "Dublin") & (cty["year"] == ly)]["completions"].iloc[0])
    return Insight(
        "completions_trend", "Supply", "total_completions",
        f"New dwelling completions reached {_fmt(cur)} in {ly}, {_fmt(full.loc[ly, 'yoy_change_pct'], 1)}% above {ly - 1} "
        f"and {_fmt(cur / full.loc[low, 'completions'], 1)} times the low of {_fmt(full.loc[low, 'completions'])} in {low}. "
        f"Dublin accounted for {_fmt(100 * dub / cur, 0)}% of the {ly} total.",
        "Ireland", f"{low}-{ly}",
        "Output has recovered strongly from its low, but supply is only meaningful relative to need; a single strong year does not close an accumulated shortfall.",
        "Test whether the current output rate is sufficient against a household-formation based demand estimate (planned Phase 2: supply-demand gap) "
        "and identify which counties are not sharing in the recovery.", ly, ["Dublin"], "published", "CSO NDQ06")


def _household_need(t: Tables) -> Optional[Insight]:
    cg = calc.census_growth(t)
    annual_hh = cg["annual_household_growth"].sum()
    ly = calc.latest_full_year(t)
    comp = int(calc.annual_completions(t, "national").set_index("year").loc[ly, "completions"])
    pop = calc.national_population(t).set_index("year")["population_thousand"]
    cagr_a = 100 * ((pop[2022] / pop[2016]) ** (1 / 6) - 1)
    last_pop_year = int(pop.index.max())
    cagr_b = 100 * ((pop[last_pop_year] / pop[2022]) ** (1 / (last_pop_year - 2022)) - 1)
    faster = "faster" if cagr_b > cagr_a else "slower"
    return Insight(
        "completions_vs_household_growth", "Demand", "household_growth",
        f"Between Census 2016 and 2022 the number of private households grew by about {_fmt(annual_hh)} per year. "
        f"Completions in {ly} ({_fmt(comp)}) were {_fmt(comp / annual_hh, 1)} times that average annual household growth. "
        f"Population grew {faster} after Census 2022 ({_fmt(cagr_b, 1)}% a year to April {last_pop_year}) than between 2016 and 2022 ({_fmt(cagr_a, 1)}% a year).",
        "Ireland", f"Census 2016-2022 vs completions {ly}",
        "Completions now exceed the average household growth of the last Census period, but this is a proxy: it ignores any accumulated shortfall, "
        "obsolescence and demolition, and household growth after 2022 may differ from 2016-2022.",
        "Build a demand model from current population and household projections before concluding whether current output is sufficient.",
        ly, [], "derived", "CSO NDQ06, F2001")


def _supply_laggards(t: Tables) -> Optional[Insight]:
    cp = calc.completions_per_1000(t).sort_values("completions_per_1000")
    yrs = cp.attrs["years"]
    nat = cp["avg_annual_completions"].sum() / cp["population"].sum() * 1000
    low = cp.head(3)
    pg = calc.census_growth(t).set_index("county")["population_growth_pct"]
    detail = "; ".join(f"{r.county} ({_fmt(r.completions_per_1000, 1)})" for r in low.itertuples())
    return Insight(
        "low_completions_counties", "Supply", "completions_per_1000",
        f"The lowest average annual completions per 1,000 residents in {yrs[0]}-{yrs[1]} were in {detail}, against {_fmt(nat, 1)} nationally.",
        _names(low["county"]), f"{yrs[0]}-{yrs[1]}",
        "Low building relative to population can mean a county is not sharing in national supply recovery, particularly if its population or household numbers are growing.",
        f"Compare with local household growth (e.g. {_names(low['county'], 2)} grew {', '.join(_fmt(pg[c], 1) + '%' for c in low['county'].head(2))} in 2016-22), "
        "and investigate planning, servicing and viability constraints locally.", yrs[1], list(low["county"]), "derived", "CSO NDQ06, F1003")


def _households_outpace_stock(t: Tables) -> Optional[Insight]:
    cg = calc.census_growth(t).sort_values("household_minus_stock_growth_pp", ascending=False)
    top = cg.head(3)
    n_pos = int((cg["household_minus_stock_growth_pp"] > 0).sum())
    detail = "; ".join(f"{r.county} (+{_fmt(r.household_minus_stock_growth_pp, 1)} pp)" for r in top.itertuples())
    return Insight(
        "households_vs_stock", "Pressure", "household_minus_stock_growth",
        f"Between Census 2016 and 2022 households grew faster than the housing stock in {n_pos} of 26 counties. The largest gaps were {detail}.",
        _names(top["county"]), "Census 2016-2022",
        "When households multiply faster than the number of dwellings, the gap is met by tighter occupancy, falling vacancy or unmet demand - all of which raise pressure on rents and prices.",
        "Review recent completions and pipeline (commencements, permissions) in these counties and whether vacancy was already low.",
        2022, list(top["county"]), "derived", "CSO F2001, F2020")


def _rent_growth(t: Tables) -> Optional[Insight]:
    rc = calc.rent_change(t)
    (by, bq), (ly, lq) = rc.attrs["base"], rc.attrs["latest"]
    top = rc.head(3)
    dub = rc[rc["county"] == "Dublin"].iloc[0]
    hi = rc.sort_values("rent_latest", ascending=False).iloc[0]
    detail = "; ".join(f"{r.county} (+{_fmt(r.change_since_base_pct, 0)}%)" for r in top.itertuples())
    return Insight(
        "rent_growth", "Affordability", "rent_level_change",
        f"Average RTB rents rose most between Q{bq} {by} and Q{lq} {ly} in {detail}. "
        + (f"Dublin still has the highest level (EUR {_fmt(hi.rent_latest)} per month) but rose {_fmt(dub.change_since_base_pct, 0)}% from a higher base."
           if hi.county == "Dublin" else
           f"{hi.county} has the highest level (EUR {_fmt(hi.rent_latest)} per month); Dublin rose {_fmt(dub.change_since_base_pct, 0)}% from a higher base."),
        _names(top["county"]), f"Q{bq} {by} to Q{lq} {ly}",
        "Fast percentage growth from lower starting rents is closing the gap between Dublin and the rest of the country, which can put pressure on local incomes outside the capital.",
        "Compare with local incomes and supply by county (see Affordability and Supply pages) to separate demand-driven from supply-constrained growth.",
        ly, list(top["county"]) + ["Dublin"], "published", "CSO RIQ02 (RTB)")


def _rent_burden(t: Tables) -> Optional[Insight]:
    la = calc.rent_to_income_la(t)
    top = la.head(3)
    yr = int(la["year"].iloc[0])
    detail = "; ".join(f"{r.la_name.replace(' County Council', '').replace(' City Council', ' City')} ({_fmt(r.median_rent_pct_income, 1)}%)" for r in top.itertuples())
    worst40 = la.sort_values("pct_tenants_40plus", ascending=False).iloc[0]
    return Insight(
        "rent_burden", "Affordability", "rent_to_income_measured",
        f"The median RTB tenant spent the largest share of disposable income on rent in {detail} ({yr}). "
        f"In {worst40.la_name.replace(' County Council', '')}, {_fmt(worst40.pct_tenants_40plus, 0)}% of tenants paid 40% or more of their disposable income.",
        _names(top["county"]), str(yr),
        "A common rule of thumb treats rent above about 30% of income as an affordability strain; high shares leave little for other costs and make saving for a deposit harder.",
        "Examine rent-pressure-zone settings, the supply of cost-rental and social homes, and income support in these areas.",
        yr, list(top["county"]), "published", "CSO TRS38")


def _prices(t: Tables) -> Optional[Insight]:
    nat = calc.property_price_summary(t, "National")
    dub = calc.property_price_summary(t, "Dublin")
    ex = calc.property_price_summary(t, "National excluding Dublin")
    p = nat["latest_period"].strftime("%B %Y")
    return Insight(
        "property_prices", "Affordability", "property_price_change",
        f"The CSO residential property price index was {_fmt(nat['latest_index'], 1)} in {p} (2015 = 100), up {_fmt(nat['change_12m_pct'], 1)}% in 12 months "
        f"and {_fmt(nat['index_vs_prior_peak_pct'], 0)}% above its pre-crisis peak. Outside Dublin the 12-month change was {_fmt(ex['change_12m_pct'], 1)}% "
        f"versus {_fmt(dub['change_12m_pct'], 1)}% in Dublin.",
        "Ireland, Dublin, rest of Ireland", p,
        "Prices well above their pre-crisis peak, with growth continuing, reduce affordability for first-time buyers and widen the gap between owners and renters.",
        "Pair price data with county incomes and mortgage-lending data (not yet in this project) to measure purchase affordability.",
        int(nat["latest_period"].year), ["Dublin"], "published", "CSO HPM09")


def _planning(t: Tables) -> Optional[Insight]:
    ly = calc.latest_full_year(t)
    w0 = calc.planning_vs_completions_window(t, ly - 4, ly, lag=0).sort_values("completions_to_permitted")
    w2 = calc.planning_vs_completions_window(t, ly - 4, ly, lag=2).sort_values("completions_to_permitted")
    low = w0.head(2)
    return Insight(
        "planning_to_completion", "Supply", "planning_to_completion",
        f"Over {ly - 4}-{ly}, completions equalled {_fmt(low.iloc[0].completions_to_permitted * 100, 0)}% of units granted planning permission in the {low.iloc[0].region} region "
        f"and {_fmt(low.iloc[1].completions_to_permitted * 100, 0)}% in {low.iloc[1].region} (lowest two regions); with a two-year lag the lowest was {w2.iloc[0].region} "
        f"({_fmt(w2.iloc[0].completions_to_permitted * 100, 0)}%).",
        _names(low["region"]), f"{ly - 4}-{ly}",
        "A low ratio means a large share of permitted homes had not been completed within the period, so permissions alone can overstate future supply. "
        "The data do not show why (possible reasons include viability, financing, servicing, or permissions that lapsed or were superseded).",
        "Investigate what share of permitted units has commenced (commencement data) and the barriers on stalled sites before designing any activation measure.",
        ly, [], "derived", "CSO BHA13, NDQ06")


def _commencements(t: Tables) -> Optional[Insight]:
    ann = calc.commencements_annual(t, "national").set_index("year")
    full = ann[~ann["is_partial_year"]]
    ly = calc.latest_full_year(t)
    if ly not in full.index:
        return None
    monthly = t["commencements_monthly"].groupby("period")["units"].sum()
    peak_month = monthly.idxmax()
    peak_year = int(full["units"].idxmax())
    latest_partial = ann[ann["is_partial_year"]].tail(1)
    ytd = ""
    if not latest_partial.empty:
        yr = int(latest_partial.index[0])
        ytd = f" In the {int(latest_partial.iloc[0]['months_reported'])} months reported for {yr}, {_fmt(latest_partial.iloc[0]['units'])} units were notified."
    comp = calc.annual_completions(t, "national").set_index("year")
    avg3 = full.loc[ly - 2:ly, "units"].mean()
    return Insight(
        "commencements", "Supply", "commencements",
        f"Commencements are very lumpy: {_fmt(full.loc[peak_year, 'units'])} units were notified in {peak_year} (including {_fmt(monthly[peak_month])} in {peak_month:%B %Y} alone), "
        f"against {_fmt(full.loc[ly, 'units'])} in {ly}; the {ly - 2}-{ly} average was {_fmt(avg3)} a year, compared with {_fmt(comp.loc[ly, 'completions'])} completions in {ly}.{ytd}",
        "Ireland", f"{ly - 2}-{ly} (series from March 2014)",
        "Single-month spikes distort annual totals, so one year's commencements should not be read as a trend. Commencements lead completions by many months, "
        "so a multi-year average is the better guide to the pipeline.",
        "Look at multi-year averages and investigate what drove the spike months (the data alone do not show the cause) before using commencements to predict completions.",
        ly, [], "published", "CSO HSM13, NDQ06")


def _vacancy(t: Tables) -> Optional[Insight]:
    la = calc.vacancy_by_la(t)
    cty = calc.vacancy_by_county(t)
    year = cty.attrs["year"]
    top = la.head(3)
    nat = cty["vacant_dwellings"].sum() / cty["dwelling_stock"].sum() * 100
    lt = cty["long_term_vacant"].sum()
    detail = "; ".join(f"{r.la_name.replace(' County Council', '').replace(' City & County Council', '').replace(' City and County Council', '')} ({_fmt(r.vacancy_rate_pct, 1)}%)" for r in top.itertuples())
    rents = calc.rent_change(t).set_index("county")["rent_latest"]
    top_counties = list(dict.fromkeys(top["county"]))
    rent_top, rent_all = rents.reindex(top_counties).mean(), rents.mean()
    rent_clause = (f" The highest-vacancy counties have an average RTB rent of EUR {_fmt(rent_top)} against EUR {_fmt(rent_all)} across all counties, "
                   f"so {'they are lower-rent areas' if rent_top < rent_all else 'rents there are not below average'}.")
    return Insight(
        "vacancy_concentration", "Vacancy", "vacancy_rate_esb",
        f"Estimated vacancy in Q4 {year} was highest in {detail}, versus {_fmt(nat, 1)}% nationally. "
        f"About {_fmt(lt)} dwellings ({_fmt(100 * lt / cty['vacant_dwellings'].sum(), 0)}% of vacant stock) had been vacant for six years running.{rent_clause}",
        _names(top["county"]), f"Q4 {year}",
        "Where vacancy is highest is not necessarily where housing pressure is highest, so reusing vacant stock would not automatically relieve the most pressured areas; "
        "and vacant does not mean habitable or available.",
        "Survey the condition and ownership of long-term vacant stock in high-vacancy authorities and test whether reuse is viable (renovation cost vs value).",
        year, list(top["county"]), "published", "CSO VAC14, VAC23")


def _vacancy_reasons(t: Tables) -> Optional[Insight]:
    r = calc.vacancy_reasons(t)
    work = r[r["reason_group"] == "Needs work / probate"]
    total = r["vacant_dwellings"].sum()
    top = r.iloc[0]
    return Insight(
        "vacancy_reasons", "Vacancy", "vacancy_reason_groups",
        f"In Census 2022, {_fmt(work['vacant_dwellings'].sum())} vacant dwellings ({_fmt(100 * work['vacant_dwellings'].sum() / total, 0)}% of {_fmt(total)}) were recorded as vacant "
        f"because of renovation or because the owner had died. The most common single reason was '{top['reason']}' ({_fmt(top['share_pct'], 0)}%).",
        "Ireland", "Census April 2022",
        "Dwellings vacant for renovation or probate are among those where an intervention (grants, probate support, compulsory purchase) has a plausible role - "
        "but Census-night reasons do not show whether a home is habitable or economical to restore.",
        "Match these reasons with long-term vacancy and building condition data, and estimate a range (not a point figure) of homes that could realistically be returned to use.",
        2022, [], "estimate", "CSO F2014")


def _social_need(t: Tables) -> Optional[Insight]:
    sn = calc.social_need(t)
    year = sn.attrs["year"]
    nat = t["social_housing_need_national"].set_index("year")["households_with_children_in_need"]
    top = sn.head(3)
    detail = "; ".join(f"{r.county} ({_fmt(r.need_per_1000_households, 1)})" for r in top.itertuples())
    first_year = 2017 if 2017 in nat.index else int(nat.index.min())
    return Insight(
        "social_need", "Social housing", "social_need_per_1000",
        f"In {year}, the most families with children identified as in need of social housing per 1,000 households were in {detail}. "
        f"Nationally the count fell from {_fmt(nat[first_year])} in {first_year} to {_fmt(nat[year])} in {year}.",
        _names(top["county"]), f"{first_year}-{year}",
        "The fall may reflect changes in eligibility rules, list management and delivery rather than reduced need, and these figures cover families with children only; "
        "need among single adults and older people is not captured.",
        "Review the full social housing waiting-list data by local authority (Summary of Social Housing Assessments, not yet in this project) and delivery rates in these counties.",
        year, list(top["county"]), "derived", "CSO SCA10, F2001")


def _homelessness(t: Tables) -> Optional[Insight]:
    n = calc.homelessness_national(t).set_index("report_month")
    last = n.index.max()
    first = n.index.min()
    reg = calc.homelessness_by_region(t)
    dub = reg[reg["region"] == "Dublin"].iloc[0]
    return Insight(
        "homelessness", "Homelessness", "homelessness",
        f"{_fmt(n.loc[last, 'total_persons'])} people were in emergency accommodation in {last:%B %Y} "
        f"({'up' if n.loc[last, 'yoy_change_pct'] >= 0 else 'down'} {_fmt(abs(n.loc[last, 'yoy_change_pct']), 1)}% on a year earlier, "
        f"versus {_fmt(n.loc[first, 'total_persons'])} in {first:%B %Y}). The Dublin region accounted for {_fmt(dub.share_of_national_pct, 0)}% of the total "
        f"({_fmt(dub.persons_per_10000, 0)} per 10,000 residents).",
        "Ireland; Dublin region", f"{first:%b %Y} - {last:%b %Y}",
        "Homelessness is the most acute outcome of the housing shortage and is heavily concentrated in the Dublin region. The data show where it is concentrated, not why.",
        "Examine exits from homelessness and the supply of social and affordable homes in the Dublin region; track family homelessness separately.",
        int(last.year), ["Dublin"], "published", "Dept. of Housing monthly Homelessness Reports")


def _population(t: Tables) -> Optional[Insight]:
    p = calc.national_population(t).set_index("year")
    ly = int(p.index.max())
    peak_year = int(p.loc[2015:, "net_migration_thousand"].idxmax())
    return Insight(
        "population_migration", "Demand", "population_growth_national",
        f"The CSO estimates the population at {_fmt(p.loc[ly, 'population_thousand'] * 1000)} in April {ly} (+{_fmt(p.loc[ly, 'population_growth_pct'], 1)}% in the year). "
        f"Estimated net migration was {_fmt(p.loc[ly, 'net_migration_thousand'], 1)}k in the latest year, down from {_fmt(p.loc[peak_year, 'net_migration_thousand'], 1)}k in {peak_year}.",
        "Ireland", f"{peak_year}-{ly}",
        "Population growth, driven mainly by net migration, is the main source of new housing demand; a slowdown eases but does not remove pressure from an existing shortfall.",
        "Use updated population and household projections in a supply-demand model rather than assuming recent migration persists.",
        ly, [], "published", "CSO PEA01, PEA15")


def _pressure(t: Tables) -> Optional[Insight]:
    hp = calc.housing_pressure_table(t)
    top = hp[hp["pressure_flags"] == hp["pressure_flags"].max()]
    mx = int(hp["pressure_flags"].max())
    return Insight(
        "pressure_flags", "Pressure", "pressure_flags",
        f"{_names(top['county'], 6)} {'is' if len(top) == 1 else 'are'} in the most-pressured quartile for {mx} of 6 housing indicators (rent level, rent growth, rent-to-income, "
        f"low completions, households outpacing stock, social housing need).",
        _names(top["county"], 6), "Latest available (2019-2025)",
        "A county flagged on several independent indicators is under pressure on more than one dimension at once; the flags are relative to other counties, not absolute thresholds.",
        "Use the County Comparison page to inspect which indicators drive each flag and design targeted supply and affordability measures.",
        2025, list(top["county"]), "derived", "Multiple (see indicator registry)")


_BUILDERS: List[Callable[[Tables], Optional[Insight]]] = [
    _completions, _household_need, _supply_laggards, _households_outpace_stock, _rent_growth, _rent_burden, _prices, _planning,
    _commencements, _vacancy, _vacancy_reasons, _social_need, _homelessness, _population, _pressure,
]


def generate_insights(t: Tables) -> List[Insight]:
    out: List[Insight] = []
    for build in _BUILDERS:
        try:
            ins = build(t)
        except Exception as exc:  # an insight failing must never break the page; report why in the log/UI
            ins = None
            print(f"insight {build.__name__} skipped: {exc}")
        if ins is not None:
            out.append(ins)
    return out


def insights_frame(t: Tables) -> pd.DataFrame:
    return pd.DataFrame([i.as_dict() for i in generate_insights(t)])
