"""Shared pytest fixtures.

* ``tables``   - the processed analytical tables (CSV backend), used by indicator/insight/simulator tests.
* ``raw_csv``  - helper to read a raw CSO file directly (tests skip if the raw file is not present locally).
* ``pg``       - an isolated PostgreSQL schema loaded with the processed data (skipped when PostgreSQL is unreachable).
"""
from __future__ import annotations

import uuid

import pandas as pd
import pytest

from src.data_cleaning.cleaners import read_cso_csv
from src.database import repository
from src.database.connection import can_connect, database_url
from src.utils.paths import PROCESSED_DIR, RAW_DIR


@pytest.fixture(scope="session")
def tables():
    if not (PROCESSED_DIR / "completions_quarterly.csv").exists():
        pytest.skip("processed data missing - run `python -m src.data_cleaning.pipeline`")
    return repository.csv_tables()


@pytest.fixture(scope="session")
def raw_csv():
    def _read(code: str) -> pd.DataFrame:
        path = RAW_DIR / "cso" / f"{code}.csv"
        if not path.exists():
            pytest.skip(f"raw file {path.name} not present locally (run the downloader)")
        return read_cso_csv(path)
    return _read


@pytest.fixture(scope="session")
def pg():
    """Engine bound to a throw-away schema containing a full load of the processed data."""
    from sqlalchemy import create_engine, text
    from src.database import loader

    if not can_connect():
        pytest.skip("PostgreSQL not reachable (start it with `docker compose up -d db`)")
    schema = f"hs_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(database_url(), future=True)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(database_url(), connect_args={"options": f"-csearch_path={schema}"}, future=True)
    try:
        loader.load_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
