"""Data-quality bookkeeping: every check and every cleaning decision is recorded.

The resulting report is saved to ``data/processed/data_quality_report.json`` and rendered into
``docs/DATA_QUALITY.md`` so that cleaning is transparent and reproducible.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd


@dataclass
class QualityIssue:
    dataset: str
    check: str
    status: str        # "pass" | "info" | "fixed" | "warning"
    affected: int
    detail: str
    action: str = ""


class QualityReport:
    def __init__(self) -> None:
        self.issues: List[QualityIssue] = []

    # ------------------------------------------------------------------ recording
    def add(self, dataset: str, check: str, status: str, affected: int = 0, detail: str = "", action: str = "") -> None:
        self.issues.append(QualityIssue(dataset, check, status, int(affected), detail, action))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(i) for i in self.issues])

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(i) for i in self.issues], indent=2, ensure_ascii=False), encoding="utf-8")

    def to_markdown(self) -> str:
        df = self.to_frame()
        if df.empty:
            return "No checks recorded.\n"
        lines = ["| Dataset | Check | Status | Rows affected | Detail | Action |", "|---|---|---|---:|---|---|"]
        for r in df.itertuples():
            lines.append(f"| {r.dataset} | {r.check} | {r.status} | {r.affected:,} | {r.detail} | {r.action} |")
        return "\n".join(lines) + "\n"

    def warnings(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.status == "warning"]


# ---------------------------------------------------------------------- reusable checks
def check_duplicates(df: pd.DataFrame, keys: Sequence[str], dataset: str, report: Optional[QualityReport] = None) -> pd.DataFrame:
    """Drop exact-key duplicates (keeping the first record) and report how many were found."""
    dup_mask = df.duplicated(subset=list(keys), keep="first")
    n = int(dup_mask.sum())
    if report is not None:
        if n:
            report.add(dataset, "duplicate keys", "fixed", n, f"duplicate records on key {list(keys)}",
                       "kept first occurrence, dropped the rest")
        else:
            report.add(dataset, "duplicate keys", "pass", 0, f"no duplicate records on key {list(keys)}")
    return df.loc[~dup_mask].copy()


def check_missing(df: pd.DataFrame, cols: Iterable[str], dataset: str, report: Optional[QualityReport] = None,
                  note: str = "") -> int:
    """Report missing values. Official statistics are NEVER imputed; missing stays missing."""
    total = 0
    for col in cols:
        n = int(df[col].isna().sum())
        total += n
        if report is not None and n:
            report.add(dataset, f"missing values in '{col}'", "info", n,
                       note or "blank/suppressed in the source (not published)", "left as missing (no imputation)")
    if report is not None and total == 0:
        report.add(dataset, "missing values", "pass", 0, f"no missing values in {list(cols)}")
    return total


def check_range(df: pd.DataFrame, col: str, lo: Optional[float], hi: Optional[float], dataset: str,
                report: Optional[QualityReport] = None, drop: bool = False) -> pd.DataFrame:
    s = df[col]
    bad = pd.Series(False, index=df.index)
    if lo is not None:
        bad |= s < lo
    if hi is not None:
        bad |= s > hi
    n = int(bad.sum())
    if report is not None:
        if n:
            report.add(dataset, f"range check '{col}' [{lo}, {hi}]", "warning", n,
                       f"values outside the plausible range; examples: {s[bad].head(3).tolist()}",
                       "dropped" if drop else "flagged only")
        else:
            report.add(dataset, f"range check '{col}' [{lo}, {hi}]", "pass", 0, "all values within plausible range")
    return df.loc[~bad].copy() if drop else df


def reconcile(report: Optional[QualityReport], dataset: str, check: str, actual: float, expected: float,
              tolerance: float = 0.0, rel_tolerance: float = 0.0, fail_status: str = "warning", note: str = "") -> bool:
    """Compare a recomputed total with the published one (absolute and/or relative tolerance)."""
    diff = abs(actual - expected)
    ok = bool(diff <= tolerance or (expected and diff / abs(expected) <= rel_tolerance))
    if report is not None:
        detail = f"computed {actual:,.2f} vs published {expected:,.2f} (difference {actual - expected:+,.2f})"
        if not ok and note:
            detail += f". {note}"
        report.add(dataset, check, "pass" if ok else fail_status, 0 if ok else 1, detail)
    return ok
