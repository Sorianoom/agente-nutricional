import os

# Must happen before any test module imports app.db, so that get_connection()
# never points at the real "nutricion" database used by the running app.
os.environ["POSTGRES_DB"] = "nutricion_test"

from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402

from app.db import get_connection  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def _admin_dsn() -> str:
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
        f"dbname=nutricion "
        f"user={os.environ.get('POSTGRES_USER', 'nutricion')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', 'nutricion')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')}"
    )


def _create_test_database_if_missing() -> None:
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE DATABASE nutricion_test")
            except psycopg.errors.DuplicateDatabase:
                pass


def _apply_schema() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text())


_create_test_database_if_missing()
_apply_schema()
