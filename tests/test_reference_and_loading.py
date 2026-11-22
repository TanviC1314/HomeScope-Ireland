"""Reference data, name standardisation, data loading, structure validation and download provenance."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.data_cleaning import reference as ref
from src.data_cleaning.cleaners import read_cso_csv
from src.data_collection import downloader, sources
from src.data_collection.validators import load_csv, profile_dataframe, validate_structure
from src.database.seed import build_seed_sql
from src.utils.paths import DATABASE_DIR, MANIFEST_PATH, RAW_DIR, ROOT


# ----------------------------------------------------------------------------- reference data
def test_reference_sizes():
    assert len(ref.COUNTY_NAMES) == 26 and len(set(ref.COUNTY_NAMES)) == 26
    assert len(ref.LOCAL_AUTHORITIES) == 31
    assert {c for _, c, _ in ref.LOCAL_AUTHORITIES} == set(ref.COUNTY_NAMES)
    assert len(ref.NUTS3_REGIONS) == 8 and len(ref.HOMELESS_REGIONS) == 9


@pytest.mark.parametrize("raw,expected", [
    ("Co. Clare", "Clare"), ("Clare", "Clare"), ("Dublin City Council", "Dublin"),
    ("Dún Laoghaire Rathdown County Council", "Dublin"), ("Dun Laoghaire-Rathdown", "Dublin"),
    ("Cork City and Cork County", "Cork"), ("Limerick City & County Council", "Limerick"),
    ("Waterford City and County", "Waterford"), ("Galway County", "Galway"), ("Mayo  County Council", "Mayo"),
])
def test_standardise_county(raw, expected):
    assert ref.standardise_county(raw) == expected


@pytest.mark.parametrize("raw", ["Ireland", "State", "All Counties", "Atlantis"])
def test_standardise_county_national_and_unknown_are_none(raw):
    assert ref.standardise_county(raw) is None


def test_standardise_la_handles_spelling_variants():
    variants = ["Dún Laoghaire Rathdown County Council", "Dun Laoghaire-Rathdown County Council", "Limerick City & County Council",
                "Limerick City and County Council", "Waterford City & County Council", "Mayo  County Council"]
    assert all(ref.standardise_la(v) for v in variants)
    assert ref.standardise_la("Ireland") is None


def test_nuts3_membership_matches_cso_grouping():
    d = dict(zip([c[0] for c in ref.COUNTIES], [c[2] for c in ref.COUNTIES]))
    assert d["Louth"] == "Mid-East" and d["Tipperary"] == "Mid-West" and d["Cavan"] == "Border"
    assert d["Dublin"] == "Dublin" and d["Kerry"] == "South-West"


def test_seed_sql_matches_reference_module():
    committed = (DATABASE_DIR / "seed_data.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == build_seed_sql()


# ----------------------------------------------------------------------------- loading
def test_load_missing_file_gives_helpful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="downloader"):
        load_csv(tmp_path / "nope.csv")
    with pytest.raises(FileNotFoundError, match="download"):
        read_cso_csv(tmp_path / "nope.csv")


def test_load_csv_handles_bom_and_cp1252(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_bytes("﻿A,B\nDún,1\n".encode("utf-8"))
    assert list(load_csv(p).columns) == ["A", "B"]
    q = tmp_path / "cp1252.csv"
    q.write_bytes("A,B\nD\xfan,1\n".encode("cp1252"))
    assert load_csv(q).iloc[0, 0] == "Dún"


def test_profile_and_validate_structure():
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", "x", "y"]})
    prof = profile_dataframe(df)
    assert prof["rows"] == 3 and prof["missing_by_column"] == {"a": 1}
    assert profile_dataframe(pd.concat([df, df.iloc[[0]]]))["duplicate_rows"] == 1
    assert validate_structure(df, ["a", "b"]) == []
    assert "missing required column 'VALUE'" in validate_structure(df, ["VALUE"])
    assert validate_structure(pd.DataFrame(), []) == ["dataset is empty"]


def test_raw_cso_files_have_expected_structure(raw_csv):
    for src in sources.CSO_DATASETS:
        if src.key in ("F2004", "RIQ02") and not (RAW_DIR / "cso" / f"{src.key}.csv").exists():
            continue
        df = raw_csv(src.key)
        assert validate_structure(df, src.required_columns) == [], src.key
        assert len(df) > 20, src.key


# ----------------------------------------------------------------------------- provenance & robustness
def test_manifest_records_provenance_for_every_dataset():
    assert MANIFEST_PATH.exists(), "run the downloader"
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["datasets"]
    for src in sources.ALL_STATIC:
        e = m[src.key]
        assert e["status"] in ("downloaded", "cached"), src.key
        for field in ("title", "provider", "licence", "landing_url", "download_url", "sha256"):
            assert e.get(field), f"{src.key} missing {field}"
        if src.code:
            assert e.get("publication_updated") and e.get("reference_period"), src.key
    assert m["HOMELESSNESS_MONTHLY"]["n_files"] >= 80


def test_committed_raw_files_match_manifest_checksums():
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["datasets"]
    checked = 0
    for key, e in m.items():
        if "files" in e or not e.get("local_path"):
            continue
        p = ROOT / e["local_path"]
        if p.exists():
            assert downloader.sha256_bytes(p.read_bytes()) == e["sha256"], f"{key} raw file was modified"
            checked += 1
    assert checked >= 10


def test_unavailable_dataset_is_handled_gracefully(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(downloader, "_get", boom)
    monkeypatch.setattr(downloader, "RAW_DIR", tmp_path)
    src = sources.BY_KEY["F1003"]
    entry = downloader.download_static(src, force=True)
    assert entry["status"] == "unavailable"
    assert "network down" in entry["error"]
    assert src.landing_url in entry["manual_instructions"]
    assert not list(tmp_path.rglob("*.csv"))
