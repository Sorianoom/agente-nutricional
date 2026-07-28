from app.db import get_connection
from app.food_matching import find_matching_food


def test_find_matching_food_returns_nutritional_data_above_threshold():
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Limpia primero los diet_meals que referencian este alimento
            cur.execute(
                "DELETE FROM diet_meals WHERE matched_food_id = "
                "(SELECT id FROM foods WHERE mercadona_product_id = 'test-avena-fm')"
            )
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-avena-fm'")
            cur.execute(
                """
                INSERT INTO foods
                    (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                VALUES ('test-avena-fm', 'Avena integral', 'Cereales', 350, 13, 60, 7)
                """
            )

    match = find_matching_food("avena integral")
    assert match is not None
    assert match["kcal_100g"] == 350.0
    assert match["protein_100g"] == 13.0


def test_find_matching_food_returns_none_below_threshold():
    match = find_matching_food("xyzxyzxyz alimento inexistente 12345")
    assert match is None
