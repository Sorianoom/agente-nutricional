import os
from contextlib import contextmanager

import psycopg


def _dsn() -> str:
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'nutricion')} "
        f"user={os.environ.get('POSTGRES_USER', 'nutricion')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', 'nutricion')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')}"
    )


@contextmanager
def get_connection():
    conn = psycopg.connect(_dsn())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
