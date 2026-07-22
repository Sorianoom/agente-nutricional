from app.db import get_connection
from scripts.match_foods import match_unlinked_meals


def _make_diet_meal(cur, food_item: str, source_pdf_filename: str) -> int:
    cur.execute(
        "DELETE FROM diet_meals WHERE diet_version_id IN "
        "(SELECT id FROM diet_versions WHERE source_pdf_filename = %s)",
        (source_pdf_filename,),
    )
    cur.execute(
        "DELETE FROM diet_versions WHERE source_pdf_filename = %s",
        (source_pdf_filename,),
    )
    cur.execute(
        """
        INSERT INTO diet_versions (source_pdf_filename, valid_from)
        VALUES (%s, '2026-01-01')
        RETURNING id
        """,
        (source_pdf_filename,),
    )
    diet_version_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO diet_meals
            (diet_version_id, day_label, meal_name, food_item, quantity_grams)
        VALUES (%s, 'lunes', 'desayuno', %s, 50)
        RETURNING id
        """,
        (diet_version_id, food_item),
    )
    return cur.fetchone()[0]


def test_match_unlinked_meals_links_by_similarity_and_strips_parens():
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Una corrida anterior de la suite puede haber dejado un
            # diet_meals enlazado a este food (conftest no limpia despues
            # de cada test, solo antes) - hay que soltar esa referencia
            # antes de poder borrar la fila de foods.
            cur.execute(
                "DELETE FROM diet_meals WHERE matched_food_id = "
                "(SELECT id FROM foods WHERE mercadona_product_id = 'test-avena')"
            )
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-avena'")
            cur.execute(
                """
                INSERT INTO foods
                    (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                VALUES ('test-avena', 'Avena integral', 'Cereales', 350, 13, 60, 7)
                """
            )
            # El parentesis es contexto de receta, no el alimento: debe
            # ignorarse al comparar y aun asi encontrar el match.
            meal_id = _make_diet_meal(
                cur, "avena integral (con leche)", "test_match_similar.pdf"
            )

    matched_count = match_unlinked_meals()
    assert matched_count >= 1

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT matched_food_id FROM diet_meals WHERE id = %s", (meal_id,)
            )
            matched_food_id = cur.fetchone()[0]
    assert matched_food_id is not None


def test_match_unlinked_meals_leaves_low_similarity_unmatched():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE matched_food_id = "
                "(SELECT id FROM foods WHERE mercadona_product_id = 'test-yogur')"
            )
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-yogur'")
            cur.execute(
                """
                INSERT INTO foods
                    (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                VALUES ('test-yogur', 'Yogur sabor coco Danone', 'Yogures', 90, 3, 12, 3)
                """
            )
            # Descripcion generica sin producto equivalente cercano: no
            # debe enlazar solo porque comparte la palabra "Yogur".
            meal_id = _make_diet_meal(
                cur, "Yogur proteico", "test_match_dissimilar.pdf"
            )

    match_unlinked_meals()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT matched_food_id FROM diet_meals WHERE id = %s", (meal_id,)
            )
            matched_food_id = cur.fetchone()[0]
    assert matched_food_id is None
