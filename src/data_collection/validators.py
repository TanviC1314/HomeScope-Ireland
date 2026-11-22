"""Load raw files, inspect structure and validate them (Module A)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.data_collection import sources as S
from src.utils.logging_config import get_logger
from src.utils.paths import PROCESSED_DIR, RAW_DIR

log = get_logger("inspect")


def load_csv(path: Path | str, **kwargs) -> pd.DataFrame:
    """Load a CSV robustly (BOM / encoding fallbacks). Raises a helpful error if the file is missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `python -m src.data_collection.downloader` "
                                "or follow the manual instructions in data/raw/MANIFEST.json.")
    last: Exception | None = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError as exc:
            last = exc
    raise ValueError(f"cannot decode {path}: {last}")


def profile_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
    """Structure summary: shape, dtypes, missing values per column, duplicate rows."""
    return {
        "rows": int(len(df)),
        "columns": list(map(str, df.columns)),
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "missing_by_column": {str(c): int(n) for c, n in df.isna().sum().items() if n},
        "duplicate_rows": int(df.duplicated().sum()),
    }


def validate_structure(df: pd.DataFrame, required_columns: List[str]) -> List[str]:
    """Return a list of problems (empty list = structure is valid)."""
    problems: List[str] = []
    if df.empty:
        problems.append("dataset is empty")
    for col in required_columns:
        if col not in df.columns:
            problems.append(f"missing required column '{col}'")
    return problems


def inspect_raw(write_report: bool = True) -> Dict[str, Any]:
    """Profile every raw CSV listed in the source registry."""
    out: Dict[str, Any] = {}
    for src in S.CSO_DATASETS:
        path = RAW_DIR / src.raw_subdir / src.raw_filename
        try:
            df = load_csv(path, dtype=str)
        except FileNotFoundError as exc:
            out[src.key] = {"status": "missing", "message": str(exc)}
            log.warning("%s: missing", src.key)
            continue
        prof = profile_dataframe(df)
        prof["validation_problems"] = validate_structure(df, src.required_columns)
        value_numeric = pd.to_numeric(df["VALUE"], errors="coerce") if "VALUE" in df.columns else pd.Series(dtype=float)
        prof["non_numeric_values"] = int(value_numeric.isna().sum() - df["VALUE"].isna().sum()) if "VALUE" in df.columns else 0
        prof["status"] = "ok" if not prof["validation_problems"] else "invalid"
        out[src.key] = prof
        log.info("%-7s rows=%-6s cols=%-2s blank VALUE=%-6s duplicates=%-3s %s", src.key, prof["rows"], len(prof["columns"]),
                 prof["missing_by_column"].get("VALUE", 0), prof["duplicate_rows"], prof["status"])
    if write_report:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        (PROCESSED_DIR / "raw_data_profile.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> None:
    inspect_raw()


if __name__ == "__main__":
    main()
