from app.db import get_connection


def test_expected_tables_exist():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            tables = {row[0] for row in cur.fetchall()}
    assert {"foods", "diet_versions", "diet_meals", "body_metrics"} <= tables
