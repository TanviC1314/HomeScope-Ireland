"""Database connection helpers (SQLAlchemy + psycopg2). Configuration comes from ``.env`` / environment."""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.utils.paths import ROOT

load_dotenv(ROOT / ".env")


def database_url() -> str:
    """DATABASE_URL if set, otherwise built from the POSTGRES_* variables (matching docker-compose.yml)."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("POSTGRES_USER", "homescope")
    pwd = os.getenv("POSTGRES_PASSWORD", "homescope")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "homescope")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


def get_engine(url: Optional[str] = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True, future=True)


def can_connect(engine: Optional[Engine] = None, timeout: int = 3) -> bool:
    """True if a PostgreSQL connection can be opened quickly (used for graceful CSV fallback)."""
    try:
        eng = engine or create_engine(database_url(), connect_args={"connect_timeout": timeout}, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
