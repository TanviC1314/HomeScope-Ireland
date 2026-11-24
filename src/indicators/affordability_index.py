"""HomeScope Housing Affordability Pressure Index (county level).

A transparent composite that ranks the 26 counties from *least* to *most* affordable by combining
rental cost, rent growth, property-price growth and income.  It is deliberately simple so that every
number can be reproduced by hand:

1. Compute four component indicators per county (see ``COMPONENTS``).
2. Standardise each component across the 26 counties to a 0-100 scale
   (0 = lowest pressure county, 100 = highest pressure county; default method ``minmax``).
3. Index = weighted average of the standardised components (weights sum to 1, ``DEFAULT_WEIGHTS``).

Higher index = less affordable *relative to the other counties*.  It is a relative ranking, not an
absolute affordability threshold, and it is **not a forecast**.

Why growth for prices?  The CSO publishes property prices only as an index (2015 = 100) for regions,
not as euro levels for counties, so a county price-to-income ratio cannot be built honestly.  The
price component therefore measures regional house-price *growth* since the same base period as rents.

All functions are pure (they take the dictionary of processed tables) and are unit-tested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

import numpy as np
import pandas as pd

from src.indicators import calculations as calc

Tables = Dict[str, pd.DataFrame]


@dataclass(frozen=True)
class Component:
    column: str
    label: str
    lens: str          # which part of the affordability question it answers
    source: str
    direction: str     # "high" = higher raw value means more pressure
    rationale: str


COMPONENTS = [
    Component("rent_burden_pct", "Rent burden (median rent as % of tenant disposable income)", "Rent vs income (measured)",
              "CSO TRS38 (RTB tenancies), 2024; local-authority medians weighted by dwelling stock", "high",
              "Directly measured share of income that tenants spend on rent."),
    Component("rent_vs_income_pct", "Annual rent as % of disposable income per person", "Rent level vs income (relative)",
              "RTB average rent (CSO RIQ02), latest quarter / CSO RAA02 income per person", "high",
              "Uses the whole-county rent level and income, so it complements the tenant-based measure; per-person income "
              "overstates the burden, so it is only meaningful relative to other counties."),
    Component("rent_rise_pct_income", "Rent rise since base period, as % of annual income per person", "Rent dynamics vs income",
              "CSO RIQ02 (RTB) change in average monthly rent x 12 / CSO RAA02 income per person", "high",
              "How much extra a year of rent costs, relative to income, compared with the base quarter. Euro rise (not % growth) is used because "
              "% growth is mechanically larger where rents started low (a base effect that would cancel out the level measures)."),
    Component("price_growth_pct", "Regional house-price growth since base period", "Property prices",
              "CSO HPM09 residential property price index (houses), NUTS3 region of the county", "high",
              "Price momentum for buyers. Regional (not county) because the CSO publishes no county price series; "
              "counties in the same region share a value."),
]
COLUMNS = [c.column for c in COMPONENTS]
BY_COLUMN = {c.column: c for c in COMPONENTS}

DEFAULT_WEIGHTS: Dict[str, float] = {
    "rent_burden_pct": 0.35,       # the only directly measured rent-to-income share: highest weight
    "rent_vs_income_pct": 0.25,
    "rent_rise_pct_income": 0.20,
    "price_growth_pct": 0.20,
}

WEIGHT_SCENARIOS: Dict[str, Dict[str, float]] = {
    "Baseline": DEFAULT_WEIGHTS,
    "Equal weights": {c: 0.25 for c in COLUMNS},
    "Income lens (rent vs income 70%)": {"rent_burden_pct": 0.40, "rent_vs_income_pct": 0.30, "rent_rise_pct_income": 0.15, "price_growth_pct": 0.15},
    "Rent-only (no prices)": {"rent_burden_pct": 0.40, "rent_vs_income_pct": 0.30, "rent_rise_pct_income": 0.30, "price_growth_pct": 0.0},
    "Momentum lens (change 70%)": {"rent_burden_pct": 0.15, "rent_vs_income_pct": 0.15, "rent_rise_pct_income": 0.35, "price_growth_pct": 0.35},
    "Prices emphasised": {"rent_burden_pct": 0.25, "rent_vs_income_pct": 0.15, "rent_rise_pct_income": 0.15, "price_growth_pct": 0.45},
}

# CSO RPPI region names that differ from the project's NUTS3 region names
RPPI_REGION_ALIASES = {"Midlands": "Midland"}
TIERS = ["Lowest pressure", "Lower-middle", "Upper-middle", "Highest pressure"]


# ------------------------------------------------------------------------------------ inputs
def regional_price_growth(t: Tables, base: pd.Timestamp = pd.Timestamp("2019-12-01"), dwelling_type: str = "houses") -> pd.DataFrame:
    """% change in the CSO house-price index between ``base`` and the latest month, per county.

    Each county takes the value of its NUTS3 region (Dublin uses the Dublin series).
    """
    p = t["property_price_index"]
    p = p[p["dwelling_type"] == dwelling_type]
    latest = p["period"].max()
    rows = []
    for _, r in t["dim_county"].iterrows():
        geo = RPPI_REGION_ALIASES.get(r["nuts3_region"], r["nuts3_region"])
        s = p[p["geography"] == geo].set_index("period")["rppi_index"]
        if base not in s.index or latest not in s.index:
            raise ValueError(f"No {dwelling_type} price index for region '{geo}' at {base:%Y-%m} / {latest:%Y-%m}")
        rows.append({"county": r["county"], "price_region": geo, "price_growth_pct": 100 * (s[latest] / s[base] - 1)})
    out = pd.DataFrame(rows)
    out.attrs.update(base=base, latest=latest)
    return out


def build_components(t: Tables, base: tuple = (2019, 4)) -> pd.DataFrame:
    """Raw (unstandardised) component values, one row per county."""
    rent = calc.rent_change(t, base=base)[["county", "rent_latest", "change_since_base_eur", "change_since_base_pct"]].rename(
        columns={"change_since_base_pct": "rent_growth_pct"})
    burden = calc.rent_to_income_county(t)[["county", "median_rent_pct_income"]].rename(columns={"median_rent_pct_income": "rent_burden_pct"})
    rvi = calc.rent_vs_income_per_person(t)[["county", "disposable_income_per_person", "annual_rent_pct_of_income_per_person"]].rename(
        columns={"annual_rent_pct_of_income_per_person": "rent_vs_income_pct"})
    price = regional_price_growth(t, base=pd.Timestamp(year=base[0], month=3 * base[1], day=1))
    df = rent.merge(burden, on="county").merge(rvi, on="county").merge(price, on="county")
    df["rent_rise_pct_income"] = 100 * 12 * df["change_since_base_eur"] / df["disposable_income_per_person"]
    df = df.merge(t["dim_county"][["county", "province", "nuts3_region"]], on="county")
    if df[COLUMNS].isna().any().any():
        raise ValueError("Missing component values: " + str(df.loc[df[COLUMNS].isna().any(axis=1), "county"].tolist()))
    return df.sort_values("county").reset_index(drop=True)


# ------------------------------------------------------------------------------------ method
def validate_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    """Return weights normalised to sum to 1; unknown/negative/all-zero weights are rejected."""
    unknown = set(weights) - set(COLUMNS)
    if unknown:
        raise ValueError(f"Unknown components: {sorted(unknown)}")
    w = pd.Series({c: float(weights.get(c, 0.0)) for c in COLUMNS})
    if (w < 0).any():
        raise ValueError("Weights must be non-negative")
    if w.sum() <= 0:
        raise ValueError("At least one weight must be positive")
    return (w / w.sum()).to_dict()


def standardise(df: pd.DataFrame, method: str = "minmax") -> pd.DataFrame:
    """Standardise each component across counties so that higher always means more pressure.

    minmax - 0..100 between the lowest and highest county (default; keeps relative distances)
    zscore - (x - mean) / sd across counties (population sd)
    rank   - percentile rank 0..100 (ignores distances, robust to outliers)
    """
    x = df[COLUMNS].astype(float)
    if method == "minmax":
        rng = (x.max() - x.min()).replace(0, np.nan)
        out = 100 * (x - x.min()) / rng
    elif method == "zscore":
        out = (x - x.mean()) / x.std(ddof=0).replace(0, np.nan)
    elif method == "rank":
        out = 100 * (x.rank(method="average") - 1) / (len(x) - 1)
    else:
        raise ValueError(f"Unknown standardisation method '{method}'")
    return out.fillna(0.0)


def compute_index(components: pd.DataFrame, weights: Optional[Mapping[str, float]] = None, method: str = "minmax") -> pd.DataFrame:
    """Affordability pressure index per county (higher = less affordable relative to other counties)."""
    w = validate_weights(weights or DEFAULT_WEIGHTS)
    z = standardise(components, method)
    out = components[["county", "province", "nuts3_region"]].copy()
    for c in COLUMNS:
        out[f"score_{c}"] = z[c].to_numpy()
        out[f"contrib_{c}"] = z[c].to_numpy() * w[c]
    out["index"] = sum(out[f"contrib_{c}"] for c in COLUMNS)
    out["rank"] = out["index"].rank(ascending=False, method="min").astype(int)   # 1 = highest pressure
    q = pd.qcut(out["index"].rank(method="first"), 4, labels=TIERS)
    out["tier"] = q.astype(str)
    return out.sort_values("rank").reset_index(drop=True)


def ranked_table(t: Tables, weights: Optional[Mapping[str, float]] = None, method: str = "minmax") -> pd.DataFrame:
    """Index joined with the raw component values: the table shown on the dashboard."""
    comp = build_components(t)
    idx = compute_index(comp, weights, method)
    return idx.merge(comp[["county", *COLUMNS, "rent_latest", "rent_growth_pct", "price_region"]], on="county").sort_values("rank").reset_index(drop=True)


# ------------------------------------------------------------------------------------ sensitivity
def scenario_ranks(components: pd.DataFrame, scenarios: Optional[Mapping[str, Mapping[str, float]]] = None, method: str = "minmax") -> pd.DataFrame:
    """County ranks (1 = highest pressure) under each named weighting scenario."""
    scenarios = scenarios or WEIGHT_SCENARIOS
    out = pd.DataFrame({"county": components["county"]})
    for name, w in scenarios.items():
        idx = compute_index(components, w, method).set_index("county")["rank"]
        out[name] = out["county"].map(idx)
    return out.set_index("county")


def leave_one_out_ranks(components: pd.DataFrame, weights: Optional[Mapping[str, float]] = None, method: str = "minmax") -> pd.DataFrame:
    """Ranks when each component is dropped in turn (remaining weights renormalised)."""
    base = validate_weights(weights or DEFAULT_WEIGHTS)
    out = pd.DataFrame({"county": components["county"]})
    for c in COLUMNS:
        w = {k: v for k, v in base.items() if k != c}
        idx = compute_index(components, w, method).set_index("county")["rank"]
        out[f"without {BY_COLUMN[c].column}"] = out["county"].map(idx)
    return out.set_index("county")


def method_ranks(components: pd.DataFrame, weights: Optional[Mapping[str, float]] = None) -> pd.DataFrame:
    """Ranks under the three standardisation methods (same weights)."""
    out = pd.DataFrame({"county": components["county"]})
    for m in ("minmax", "zscore", "rank"):
        out[m] = out["county"].map(compute_index(components, weights, m).set_index("county")["rank"])
    return out.set_index("county")


def monte_carlo_ranks(components: pd.DataFrame, n: int = 5000, seed: int = 42, method: str = "minmax", top_n: int = 5,
                      concentration: Optional[float] = None) -> pd.DataFrame:
    """Rank uncertainty from random weights.

    ``concentration=None``: weights drawn from a flat Dirichlet distribution (every weighting of the
    four components is equally likely, including extreme ones such as 90% on a single component).
    ``concentration=c``: weights drawn around the baseline weights (Dirichlet with alpha = c x baseline);
    larger c = weights stay closer to the baseline (c=50 is roughly +/-6 percentage points on a 35% weight).
    For each county: baseline rank, median rank, 5th-95th percentile rank range and the share of draws
    in which it is among the ``top_n`` highest-pressure counties.
    """
    rng = np.random.default_rng(seed)
    alpha = np.ones(len(COLUMNS)) if concentration is None else concentration * np.array([DEFAULT_WEIGHTS[c] for c in COLUMNS])
    w = rng.dirichlet(alpha, size=n)                                          # n x k
    scores = standardise(components, method).to_numpy()                       # counties x k
    idx = w @ scores.T                                                        # n x counties
    ranks = (-idx).argsort(axis=1).argsort(axis=1) + 1                        # 1 = highest pressure
    base = compute_index(components, None, method).set_index("county")["rank"]
    out = pd.DataFrame({
        "county": components["county"],
        "baseline_rank": components["county"].map(base).to_numpy(),
        "median_rank": np.median(ranks, axis=0),
        "rank_p05": np.percentile(ranks, 5, axis=0),
        "rank_p95": np.percentile(ranks, 95, axis=0),
        f"pct_draws_top_{top_n}": 100 * (ranks <= top_n).mean(axis=0),
    })
    out["rank_range_width"] = out["rank_p95"] - out["rank_p05"]
    return out.sort_values("baseline_rank").reset_index(drop=True)


def rank_agreement(ranks: pd.DataFrame, baseline: str) -> pd.Series:
    """Spearman rank correlation of every scenario with the baseline column."""
    return pd.Series({c: ranks[baseline].corr(ranks[c], method="spearman") for c in ranks.columns if c != baseline})


def stability_summary(t: Tables) -> Dict[str, object]:
    """Headline sensitivity facts used by the dashboard and docs."""
    comp = build_components(t)
    scen = scenario_ranks(comp)
    loo = leave_one_out_ranks(comp)
    meth = method_ranks(comp)
    mc_flat = monte_carlo_ranks(comp)
    mc_local = monte_carlo_ranks(comp, concentration=50)
    base = scen["Baseline"]
    top5 = set(base.nsmallest(5).index)
    return {
        "min_spearman_scenarios": float(rank_agreement(scen, "Baseline").min()),
        "min_spearman_leave_one_out": float(pd.Series({c: base.corr(loo[c], method="spearman") for c in loo.columns}).min()),
        "min_spearman_methods": float(pd.Series({c: base.corr(meth[c], method="spearman") for c in meth.columns}).min()),
        "top5_baseline": sorted(top5),
        "top5_in_every_scenario": sorted(c for c in top5 if (scen.loc[c] <= 8).all()),
        "max_rank_shift_scenarios": int((scen.sub(base, axis=0)).abs().max().max()),
        "monte_carlo_draws": 5000,
        "median_rank_interval_width_flat": float(mc_flat["rank_range_width"].median()),
        "median_rank_interval_width_local": float(mc_local["rank_range_width"].median()),
        "top5_share_local": {r.county: float(r["pct_draws_top_5"]) for _, r in mc_local.head(6).iterrows()},
    }
