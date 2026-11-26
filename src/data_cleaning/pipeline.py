"""Run every cleaning step: raw files (read-only) -> tidy tables in ``data/processed``."""
from __future__ import annotations

import json
from typing import Dict

import pandas as pd

from src.data_cleaning import cleaners as C
from src.data_cleaning import reference as ref
from src.data_cleaning.quality import QualityReport
from src.utils.geo import itm_to_wgs84
from src.utils.logging_config import get_logger
from src.utils.paths import DOCS_DIR, MANIFEST_PATH, PROCESSED_DIR, RAW_DIR

log = get_logger("cleaning")

# processed table name -> description
PROCESSED_TABLES = [
    "dim_county", "dim_local_authority", "dim_region", "data_sources",
    "completions_quarterly", "commencements_monthly", "planning_permissions", "planning_permissions_national",
    "population_census", "population_county_estimates", "population_national", "households_census", "housing_stock_census", "tenure_census",
    "vacancy_estimates", "long_term_vacancy", "vacancy_reasons_census",
    "rents_rtb", "property_price_index", "household_income_county", "household_income_national", "rent_to_income_la",
    "social_housing_need", "social_housing_need_national", "homelessness_monthly",
]


def _raw(code: str) -> pd.DataFrame:
    return C.read_cso_csv(RAW_DIR / "cso" / f"{code}.csv")


def build_data_sources(manifest: dict, homeless: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, m in sorted(manifest.get("datasets", {}).items()):
        if key == "HOMELESSNESS_MONTHLY":
            files = m.get("files", {})
            pub = max((f.get("metadata_modified", "") for f in files.values()), default="")
            period = f"{homeless['report_month'].min():%Y-%m} to {homeless['report_month'].max():%Y-%m}"
            rows_n = len(homeless)
        else:
            pub, period, rows_n = m.get("publication_updated", ""), m.get("reference_period", ""), m.get("rows")
        rows.append({
            "source_key": key, "title": m.get("title"), "provider": m.get("provider"), "theme": m.get("theme"),
            "landing_url": m.get("landing_url"), "download_url": m.get("download_url"), "licence": m.get("licence"),
            "granularity": m.get("granularity"), "publication_updated": pub, "reference_period": period,
            "retrieved_utc": m.get("retrieved_utc", ""), "raw_rows": rows_n, "status": m.get("status"),
            "use_in_project": m.get("use_in_project"), "notes": m.get("notes", ""),
        })
    return pd.DataFrame(rows)


def simplify_geojson(precision: int = 3) -> None:
    src = RAW_DIR / "geo" / "counties_osi_2019_gen20m.geojson"
    if not src.exists():
        log.warning("county GeoJSON not found - map will fall back to a bar/tile view")
        return
    gj = json.loads(src.read_text(encoding="utf-8"))

    def rnd(coords):
        if isinstance(coords[0], (int, float)):
            x, y = coords[0], coords[1]
            if abs(x) > 1000:  # Irish Transverse Mercator metres -> WGS84 lon/lat
                x, y = (float(v) for v in itm_to_wgs84(x, y))
            return [round(x, precision), round(y, precision)]
        return [rnd(c) for c in coords]

    feats = []
    for f in gj["features"]:
        county = ref.standardise_county(f["properties"]["ENGLISH"])
        geom = dict(f["geometry"])
        geom["coordinates"] = rnd(geom["coordinates"])
        feats.append({"type": "Feature", "id": county, "properties": {"county": county}, "geometry": geom})
    out = {"type": "FeatureCollection", "features": feats}
    (PROCESSED_DIR / "counties.geojson").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log.info("wrote counties.geojson with %s counties", len(feats))


def run(write_docs: bool = True) -> Dict[str, pd.DataFrame]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    report = QualityReport()
    t: Dict[str, pd.DataFrame] = {}

    t["dim_county"] = ref.county_reference_frame()
    t["dim_local_authority"] = ref.local_authority_frame()
    t["dim_region"] = ref.region_frame()

    t["completions_quarterly"] = C.clean_completions(_raw("NDQ06"), report)
    t["commencements_monthly"] = C.clean_commencements(_raw("HSM13"), report)
    t["planning_permissions"] = C.clean_planning(_raw("BHA13"), report)
    t["planning_permissions_national"] = C.clean_planning_national(_raw("BHA13"), report)
    t["population_census"] = C.clean_population_census(_raw("F1003"), report)
    t["population_national"] = C.clean_population_national(_raw("PEA01"), _raw("PEA15"), report)
    t["population_county_estimates"] = C.clean_population_county_estimates(_raw("PEA08"), report)
    t["households_census"] = C.clean_households(_raw("F2001"), report)
    t["housing_stock_census"] = C.clean_housing_stock(_raw("F2020"), report)
    t["tenure_census"] = C.clean_tenure(_raw("F2004"), report)
    t["vacancy_estimates"] = C.clean_vacancy_estimates(_raw("VAC14"), "VAC14", report)
    t["long_term_vacancy"] = C.clean_vacancy_estimates(_raw("VAC23"), "VAC23", report)
    t["vacancy_reasons_census"] = C.clean_vacancy_reasons(_raw("F2014"), report)
    t["rents_rtb"] = C.clean_rents(_raw("RIQ02"), report)
    t["property_price_index"] = C.clean_property_prices(_raw("HPM09"), report)
    t["household_income_county"], t["household_income_national"] = C.clean_income(_raw("RAA02"), report)
    t["rent_to_income_la"] = C.clean_rent_to_income(_raw("TRS38"), report)
    t["social_housing_need"], t["social_housing_need_national"] = C.clean_social_need(_raw("SCA10"), report)
    t["homelessness_monthly"] = C.clean_homelessness(RAW_DIR / "housing_gov" / "homelessness", report)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {"datasets": {}}
    t["data_sources"] = build_data_sources(manifest, t["homelessness_monthly"])

    for name in PROCESSED_TABLES:
        df = t[name]
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False, encoding="utf-8")
        log.info("%-26s %7d rows x %2d cols", name, len(df), df.shape[1])
    simplify_geojson()

    report.save_json(PROCESSED_DIR / "data_quality_report.json")
    if write_docs:
        DOCS_DIR.mkdir(exist_ok=True)
        (DOCS_DIR / "DATA_QUALITY.md").write_text(
            "# Data quality report\n\nGenerated by `python -m src.data_cleaning.pipeline`. Every check and every cleaning decision "
            "applied to the raw files is listed here. Raw files are never modified.\n\n"
            + report.to_markdown(), encoding="utf-8")
    warns = report.warnings()
    log.info("quality checks: %s recorded, %s warnings", len(report.issues), len(warns))
    for w in warns:
        log.warning("%s | %s | %s", w.dataset, w.check, w.detail)
    return t


def main() -> None:
    run()


if __name__ == "__main__":
    main()
