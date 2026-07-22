import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

# Por debajo de esto, el nombre generico del PDF ("Yogur proteico") tiende a
# enlazar con productos equivocados (ej. "Yogur sabor coco") solo por
# parecido superficial de caracteres. Mejor dejarlo sin enlazar que enlazarlo
# mal, ya que un match erroneo contamina en silencio las macros del dashboard.
SIMILARITY_THRESHOLD = 0.3


def _normalize(food_item: str) -> str:
    # Quita anotaciones entre parentesis (contexto de receta, no el
    # alimento en si, ej. "Pan blanco (bocadillo jamon y guacamole)").
    return re.sub(r"\s*\([^)]*\)", "", food_item).strip()


def match_unlinked_meals() -> int:
    matched = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, food_item FROM diet_meals WHERE matched_food_id IS NULL"
            )
            unmatched = cur.fetchall()

            for meal_id, food_item in unmatched:
                search_term = _normalize(food_item)
                cur.execute(
                    """
                    SELECT id FROM foods
                    WHERE similarity(name, %s) > %s
                    ORDER BY similarity(name, %s) DESC
                    LIMIT 1
                    """,
                    (search_term, SIMILARITY_THRESHOLD, search_term),
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
