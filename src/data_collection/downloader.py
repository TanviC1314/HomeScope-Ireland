"""Download official datasets and record provenance in ``data/raw/MANIFEST.json``.

Design notes
------------
* Only documented open-data APIs are used (CSO PxStat REST API, the CKAN API on
  data.gov.ie, and Tailte Eireann's open ArcGIS Hub download).  No HTML scraping.
* Raw files are written exactly as served and are never modified afterwards.
* Failures are handled gracefully: an unavailable dataset is logged, flagged in
  the manifest with manual download instructions, and the pipeline continues.
* The manifest records dataset name, publisher, URLs, licence, publication
  (last-updated) date, reference period, checksum and retrieval timestamp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from src.data_collection import sources as S
from src.utils.logging_config import get_logger
from src.utils.paths import MANIFEST_PATH, RAW_DIR, ROOT

log = get_logger("download")
HEADERS = {"User-Agent": "HomeScope-Ireland/0.1 (open-data analytics project; polite client)"}
TIMEOUT = 180


def _get(url: str, retries: int = 3, **kw) -> requests.Response:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # network / HTTP errors
            last = exc
            log.warning("attempt %s/%s failed for %s: %s", attempt, retries, url, exc)
            time.sleep(2 * attempt)
    raise RuntimeError(f"giving up on {url}: {last}")


def _post_subset(src: S.DatasetSource) -> bytes:
    """Request a subset of one dimension of a CSO table as CSV (JSON-RPC ReadDataset)."""
    meta = _get(f"{S.CSO_API}.ReadMetadata/{src.code}/JSON-stat/2.0/en").json()
    labels = meta["dimension"][src.subset_dimension]["category"]["label"]
    wanted = set(src.subset_labels)
    codes = [code for code, label in labels.items() if label in wanted]
    missing = wanted - {labels[c] for c in codes}
    if missing:
        log.warning("%s: subset labels not found in table: %s", src.key, sorted(missing))
    payload = {"jsonrpc": "2.0", "method": "PxStat.Data.Cube_API.ReadDataset", "params": {
        "class": "query", "id": [src.subset_dimension],
        "dimension": {src.subset_dimension: {"category": {"index": codes}}},
        "extension": {"pivot": None, "codes": False, "language": {"code": "en"},
                      "format": {"type": "CSV", "version": "1.0"}, "matrix": src.code},
        "version": "2.0"}}
    resp = requests.post("https://ws.cso.ie/public/api.jsonrpc", json=payload, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if "result" not in body or not isinstance(body["result"], str):
        raise RuntimeError(f"unexpected PxStat response: {str(body)[:200]}")
    return body["result"].encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"generated_by": "src.data_collection.downloader", "datasets": {}}


def save_manifest(manifest: Dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest["last_run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def cso_metadata(code: str) -> Dict[str, Any]:
    """Return last-updated date and reference period for a CSO table (JSON-stat metadata)."""
    url = f"{S.CSO_API}.ReadMetadata/{code}/JSON-stat/2.0/en"
    meta = _get(url).json()
    period: Optional[str] = None
    for dim_id in meta.get("id", []):
        if dim_id.upper().startswith("TLIST"):
            labels = list(meta["dimension"][dim_id]["category"]["label"].values())
            period = f"{labels[0]} to {labels[-1]}" if len(labels) > 1 else labels[0]
    return {"publication_updated": (meta.get("updated") or "")[:10], "reference_period": period,
            "official_label": meta.get("label")}


def _count_rows(content: bytes) -> int:
    return max(content.count(b"\n") - 1, 0)


def download_static(src: S.DatasetSource, force: bool = False) -> Dict[str, Any]:
    dest: Path = RAW_DIR / src.raw_subdir / src.raw_filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    entry: Dict[str, Any] = {
        "key": src.key, "title": src.title, "provider": src.provider, "theme": src.theme,
        "landing_url": src.landing_url, "download_url": src.download_url, "licence": src.licence,
        "granularity": src.granularity, "use_in_project": src.use_in_project, "notes": src.notes,
        "local_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
    }
    if dest.exists() and not force:
        log.info("%-8s already present - skipping (use --force to refresh)", src.key)
        entry["status"] = "cached"
        content = dest.read_bytes()
    else:
        try:
            content = _post_subset(src) if src.subset_dimension else _get(src.download_url).content
            if src.subset_dimension:
                entry["subset"] = {"dimension": src.subset_dimension, "labels": list(src.subset_labels)}
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(content)
            tmp.replace(dest)
            entry["status"] = "downloaded"
            entry["retrieved_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            log.info("%-8s downloaded %.1f KB", src.key, len(content) / 1024)
        except Exception as exc:  # graceful degradation
            log.error("%-8s UNAVAILABLE: %s", src.key, exc)
            entry["status"] = "unavailable"
            entry["error"] = str(exc)
            entry["manual_instructions"] = (
                f"Open {src.landing_url}, choose Download > CSV (unformatted) and save the file as {entry['local_path']}."
            )
            return entry
    entry["sha256"] = sha256_bytes(content)
    entry["size_bytes"] = len(content)
    if src.raw_filename.endswith(".csv"):
        entry["rows"] = _count_rows(content)
    if src.code:
        try:
            entry.update(cso_metadata(src.code))
        except Exception as exc:
            log.warning("%-8s could not read metadata: %s", src.key, exc)
    return entry


def download_homelessness(force: bool = False, limit: Optional[int] = None) -> Dict[str, Any]:
    """Monthly homelessness reports (Dept. of Housing) discovered via the data.gov.ie CKAN API."""
    out_dir = RAW_DIR / "housing_gov" / "homelessness"
    out_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Any] = {}
    try:
        rows, start, names = 1000, 0, []
        while True:
            r = _get(f"{S.HOMELESSNESS_CKAN}/package_search", params={
                "q": "homelessness report",
                "fq": "organization:department-of-housing-local-government-and-heritage",
                "rows": rows, "start": start}).json()["result"]
            names += [p for p in r["results"] if p["name"].startswith("homelessness-report-")]
            start += rows
            if start >= r["count"]:
                break
    except Exception as exc:
        log.error("homelessness: catalogue unavailable: %s", exc)
        return {"status": "unavailable", "error": str(exc),
                "manual_instructions": "Download monthly CSVs from https://data.gov.ie (search 'Homelessness Report') "
                                       "into data/raw/housing_gov/homelessness/"}
    names.sort(key=lambda p: p["name"])
    if limit:
        names = names[:limit]
    for pkg in names:
        csvs = [x for x in pkg.get("resources", []) if (x.get("format") or "").upper() == "CSV"]
        if not csvs:
            continue
        fname = f"{pkg['name']}.csv"
        dest = out_dir / fname
        info = {"package": pkg["name"], "title": pkg["title"], "url": csvs[0]["url"],
                "metadata_modified": pkg.get("metadata_modified", "")[:10]}
        if not dest.exists() or force:
            try:
                content = _get(csvs[0]["url"]).content
                dest.write_bytes(content)
                info["status"] = "downloaded"
            except Exception as exc:
                log.warning("homelessness %s failed: %s", pkg["name"], exc)
                info["status"] = "unavailable"
                info["error"] = str(exc)
                files[fname] = info
                continue
            time.sleep(0.3)  # be polite
        else:
            info["status"] = "cached"
        info["sha256"] = sha256_bytes(dest.read_bytes())
        files[fname] = info
    ok = sum(1 for f in files.values() if f["status"] != "unavailable")
    log.info("homelessness: %s/%s monthly reports available", ok, len(files))
    return {
        "key": "HOMELESSNESS_MONTHLY", "provider": S.HOMELESSNESS_PUBLISHER,
        "title": "Homelessness Report (monthly, by region)", "theme": "social",
        "landing_url": S.HOMELESSNESS_LANDING, "download_url": f"{S.HOMELESSNESS_CKAN}/package_search (CKAN API)",
        "licence": S.HOMELESSNESS_LICENCE, "granularity": "Dept. homeless region x month",
        "use_in_project": "Homelessness trends",
        "notes": "One CSV per month; column sets changed over time so they are harmonised in data_cleaning.",
        "status": "downloaded" if ok else "unavailable", "files": files, "n_files": len(files),
        "local_path": "data/raw/housing_gov/homelessness",
    }


def run(only: Optional[list[str]] = None, force: bool = False, skip_homelessness: bool = False) -> Dict[str, Any]:
    manifest = load_manifest()
    for src in S.ALL_STATIC:
        if only and src.key not in only:
            continue
        manifest["datasets"][src.key] = download_static(src, force=force)
    if not skip_homelessness and (not only or "HOMELESSNESS_MONTHLY" in only):
        manifest["datasets"]["HOMELESSNESS_MONTHLY"] = download_homelessness(force=force)
    save_manifest(manifest)
    bad = [k for k, v in manifest["datasets"].items() if v.get("status") == "unavailable"]
    if bad:
        log.warning("Unavailable datasets: %s (see manual_instructions in MANIFEST.json)", bad)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Download HomeScope Ireland source datasets")
    ap.add_argument("--only", nargs="*", help="dataset keys, e.g. NDQ06 RIQ02 HOMELESSNESS_MONTHLY")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--skip-homelessness", action="store_true")
    a = ap.parse_args()
    run(a.only, a.force, a.skip_homelessness)


if __name__ == "__main__":
    main()
