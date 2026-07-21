import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402


def match_unlinked_meals() -> int:
    matched = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, food_item FROM diet_meals WHERE matched_food_id IS NULL"
            )
            unmatched = cur.fetchall()

            for meal_id, food_item in unmatched:
                cur.execute(
                    """
                    SELECT id FROM foods
                    WHERE name ILIKE %s
                    ORDER BY length(name) ASC
                    LIMIT 1
                    """,
                    (f"%{food_item}%",),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                cur.execute(
                    "UPDATE diet_meals SET matched_food_id = %s WHERE id = %s",
                    (row[0], meal_id),
                )
                matched += 1
    return matched


if __name__ == "__main__":
    linked = match_unlinked_meals()
    print(f"Enlazados {linked} alimentos.")
