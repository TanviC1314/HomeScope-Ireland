"""Central place for project paths so no module hard-codes a location."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"
DATABASE_DIR = ROOT / "database"
DOCS_DIR = ROOT / "docs"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
