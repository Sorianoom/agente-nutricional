SIMILARITY_THRESHOLD = 0.3


def find_matching_food_with_cursor(cur, name: str) -> dict | None:
    cur.execute(
        """
        SELECT id, name, kcal_100g, protein_100g, carbs_100g, fat_100g
        FROM foods
        WHERE similarity(name, %s) > %s
        ORDER BY similarity(name, %s) DESC
        LIMIT 1
        """,
        (name, SIMILARITY_THRESHOLD, name),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "kcal_100g": float(row[2] or 0),
        "protein_100g": float(row[3] or 0),
        "carbs_100g": float(row[4] or 0),
        "fat_100g": float(row[5] or 0),
    }


def find_matching_food(name: str) -> dict | None:
    from app.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            return find_matching_food_with_cursor(cur, name)
