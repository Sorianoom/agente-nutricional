from app.db import get_connection
from scripts.match_foods import match_unlinked_meals


def test_match_unlinked_meals_links_by_substring():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'test_match.pdf')"
            )
            cur.execute(
                "DELETE FROM diet_versions WHERE source_pdf_filename = 'test_match.pdf'"
            )
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-avena'")

            cur.execute(
                """
                INSERT INTO foods
                    (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                VALUES ('test-avena', 'Avena integral', 'Cereales', 350, 13, 60, 7)
                """
            )
            cur.execute(
                """
                INSERT INTO diet_versions (source_pdf_filename, valid_from)
                VALUES ('test_match.pdf', '2026-01-01')
                RETURNING id
                """
            )
            diet_version_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO diet_meals
                    (diet_version_id, day_label, meal_name, food_item, quantity_grams)
                VALUES (%s, 'lunes', 'desayuno', 'avena integral', 50)
                RETURNING id
                """,
                (diet_version_id,),
            )
            meal_id = cur.fetchone()[0]

    matched_count = match_unlinked_meals()
    assert matched_count >= 1

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT matched_food_id FROM diet_meals WHERE id = %s", (meal_id,)
            )
            matched_food_id = cur.fetchone()[0]
    assert matched_food_id is not None
