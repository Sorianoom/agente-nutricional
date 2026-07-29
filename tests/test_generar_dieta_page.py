from fastapi.testclient import TestClient

from app.compensation import get_active_compensation
from app.db import get_connection
from app.main import app

client = TestClient(app)


def _seed_profile_and_metrics():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_profile (id, age, sex, height_cm, activity_level, current_goal)
                VALUES (1, 23, 'M', 178, 'moderado', 'maintenance')
                ON CONFLICT (id) DO UPDATE SET
                    age = EXCLUDED.age, sex = EXCLUDED.sex, height_cm = EXCLUDED.height_cm,
                    activity_level = EXCLUDED.activity_level, current_goal = EXCLUDED.current_goal
                """
            )
            cur.execute(
                "DELETE FROM body_metrics WHERE source_pdf_filename = 'test_generar_dieta.pdf'"
            )
            cur.execute(
                """
                INSERT INTO body_metrics (source_pdf_filename, measured_on, weight_kg, body_fat_pct)
                VALUES ('test_generar_dieta.pdf', '2026-01-01', 80.0, 20.0)
                """
            )


def test_get_generar_dieta_shows_form():
    _seed_profile_and_metrics()
    response = client.get("/generar-dieta")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_generar_dieta_shows_generated_meals(monkeypatch):
    _seed_profile_and_metrics()

    fake_day = {
        "meals": [
            {"meal_name": "desayuno", "food_item": "Avena integral", "quantity_grams": 100, "matched_food_id": 1, "verified": True, "kcal": 350.0, "protein_g": 13.0, "carbs_g": 60.0, "fat_g": 7.0},
            {"meal_name": "comida", "food_item": "Pechuga de pollo", "quantity_grams": 200, "matched_food_id": 2, "verified": True, "kcal": 220.0, "protein_g": 46.0, "carbs_g": 0.0, "fat_g": 4.0},
            {"meal_name": "merienda", "food_item": "Yogur proteico", "quantity_grams": 125, "matched_food_id": 3, "verified": True, "kcal": 112.5, "protein_g": 12.5, "carbs_g": 10.0, "fat_g": 2.5},
            {"meal_name": "cena", "food_item": "Salmon", "quantity_grams": 150, "matched_food_id": 4, "verified": True, "kcal": 300.0, "protein_g": 30.0, "carbs_g": 0.0, "fat_g": 19.5},
        ],
        "totals": {"kcal": 982.5, "protein_g": 101.5, "carbs_g": 70.0, "fat_g": 33.0},
        "within_tolerance": True,
        "attempts": 1,
    }
    monkeypatch.setattr("app.main.generate_day", lambda target, goal, hints: fake_day)

    response = client.post(
        "/generar-dieta",
        data={"method": "formula", "hint_desayuno": "jamon", "hint_comida": "", "hint_merienda": "", "hint_cena": "salmon"},
    )
    assert response.status_code == 200
    assert "Avena integral" in response.text
    assert "Salmon" in response.text


def test_generar_dieta_comida_regenerates_one_meal_and_updates_guardar_section(monkeypatch):
    fake_new_meal = {
        "meal_name": "cena", "food_item": "Salmon", "quantity_grams": 150,
        "matched_food_id": 4, "verified": True,
        "kcal": 300.0, "protein_g": 30.0, "carbs_g": 0.0, "fat_g": 19.5,
        "within_tolerance": True, "attempts": 1,
    }
    monkeypatch.setattr(
        "app.main.generate_single_meal",
        lambda meal_name, budget, goal, hint: fake_new_meal,
    )

    response = client.post(
        "/generar-dieta/comida",
        data={
            "meal_name": "cena",
            "target_kcal": "1000", "target_protein_g": "100",
            "target_carbs_g": "70", "target_fat_g": "33",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "100",
            "meal_desayuno_matched_food_id": "1", "meal_desayuno_kcal": "350",
            "meal_desayuno_protein_g": "13", "meal_desayuno_carbs_g": "60", "meal_desayuno_fat_g": "7",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "200",
            "meal_comida_matched_food_id": "2", "meal_comida_kcal": "220",
            "meal_comida_protein_g": "46", "meal_comida_carbs_g": "0", "meal_comida_fat_g": "4",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "125",
            "meal_merienda_matched_food_id": "3", "meal_merienda_kcal": "112.5",
            "meal_merienda_protein_g": "12.5", "meal_merienda_carbs_g": "10", "meal_merienda_fat_g": "2.5",
            "meal_cena_food_item": "Salmon (anterior)", "meal_cena_quantity_grams": "100",
            "meal_cena_matched_food_id": "4", "meal_cena_kcal": "200",
            "meal_cena_protein_g": "20", "meal_cena_carbs_g": "0", "meal_cena_fat_g": "13",
            "hint_cena_new": "salmon",
        },
    )
    assert response.status_code == 200
    assert "Salmon" in response.text
    assert 'id="guardar-section"' in response.text


def _seed_test_foods_for_guardar() -> dict:
    # La base de datos de test es persistente entre ejecuciones (no se recrea
    # desde cero), asi que los ids de `foods` no son necesariamente 1-4 como
    # asume el literal del plan (aqui ya hay filas de ejecuciones anteriores
    # de otros subsistemas). Sembramos filas propias marcadas con un
    # mercadona_product_id de test y usamos sus ids reales devueltos, en vez
    # de hardcodear 1/2/3/4, para no violar la FK matched_food_id -> foods(id).
    product_ids = {
        "desayuno": "test-guardar-desayuno",
        "comida": "test-guardar-comida",
        "merienda": "test-guardar-merienda",
        "cena": "test-guardar-cena",
    }
    ids = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            for meal_name, product_id in product_ids.items():
                cur.execute("DELETE FROM foods WHERE mercadona_product_id = %s", (product_id,))
                cur.execute(
                    """
                    INSERT INTO foods
                        (mercadona_product_id, name, category, kcal_100g, protein_100g, carbs_100g, fat_100g)
                    VALUES (%s, 'Alimento de prueba', 'Test', 100, 10, 10, 10)
                    RETURNING id
                    """,
                    (product_id,),
                )
                ids[meal_name] = cur.fetchone()[0]
    return ids


def test_guardar_dia_creates_diet_version_when_within_tolerance():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'generado')"
            )
            cur.execute("DELETE FROM diet_versions WHERE source_pdf_filename = 'generado'")

    food_ids = _seed_test_foods_for_guardar()

    response = client.post(
        "/generar-dieta/guardar",
        data={
            "target_kcal": "982.5", "target_protein_g": "101.5",
            "target_carbs_g": "70", "target_fat_g": "33",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "100",
            "meal_desayuno_matched_food_id": str(food_ids["desayuno"]), "meal_desayuno_kcal": "350",
            "meal_desayuno_protein_g": "13", "meal_desayuno_carbs_g": "60", "meal_desayuno_fat_g": "7",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "200",
            "meal_comida_matched_food_id": str(food_ids["comida"]), "meal_comida_kcal": "220",
            "meal_comida_protein_g": "46", "meal_comida_carbs_g": "0", "meal_comida_fat_g": "4",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "125",
            "meal_merienda_matched_food_id": str(food_ids["merienda"]), "meal_merienda_kcal": "112.5",
            "meal_merienda_protein_g": "12.5", "meal_merienda_carbs_g": "10", "meal_merienda_fat_g": "2.5",
            "meal_cena_food_item": "Salmon", "meal_cena_quantity_grams": "150",
            "meal_cena_matched_food_id": str(food_ids["cena"]), "meal_cena_kcal": "300",
            "meal_cena_protein_g": "30", "meal_cena_carbs_g": "0", "meal_cena_fat_g": "19.5",
        },
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM diet_meals dm "
                "JOIN diet_versions dv ON dv.id = dm.diet_version_id "
                "WHERE dv.source_pdf_filename = 'generado'"
            )
            count = cur.fetchone()[0]
    assert count == 4


def test_guardar_dia_within_tolerance_does_not_create_compensation():
    # `generar_dieta_guardar` solo guarda si `within_tolerance(totals, target)` es
    # cierto (ver `test_guardar_dia_rejects_out_of_tolerance_data`), y ahora llama
    # a `close_day_and_check_compensation(totals, target)` con esos mismos valores
    # justo despues de guardar (Tarea 4 del Subsistema 4). Como el guard previo ya
    # garantiza que esos totals estan dentro de margen, esa llamada es un no-op:
    # no debe crearse ninguna compensacion pendiente por guardar un dia valido.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'generado')"
            )
            cur.execute("DELETE FROM diet_versions WHERE source_pdf_filename = 'generado'")

    food_ids = _seed_test_foods_for_guardar()

    response = client.post(
        "/generar-dieta/guardar",
        data={
            "target_kcal": "982.5", "target_protein_g": "101.5",
            "target_carbs_g": "70", "target_fat_g": "33",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "100",
            "meal_desayuno_matched_food_id": str(food_ids["desayuno"]), "meal_desayuno_kcal": "350",
            "meal_desayuno_protein_g": "13", "meal_desayuno_carbs_g": "60", "meal_desayuno_fat_g": "7",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "200",
            "meal_comida_matched_food_id": str(food_ids["comida"]), "meal_comida_kcal": "220",
            "meal_comida_protein_g": "46", "meal_comida_carbs_g": "0", "meal_comida_fat_g": "4",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "125",
            "meal_merienda_matched_food_id": str(food_ids["merienda"]), "meal_merienda_kcal": "112.5",
            "meal_merienda_protein_g": "12.5", "meal_merienda_carbs_g": "10", "meal_merienda_fat_g": "2.5",
            "meal_cena_food_item": "Salmon", "meal_cena_quantity_grams": "150",
            "meal_cena_matched_food_id": str(food_ids["cena"]), "meal_cena_kcal": "300",
            "meal_cena_protein_g": "30", "meal_cena_carbs_g": "0", "meal_cena_fat_g": "19.5",
        },
    )
    assert response.status_code == 200
    assert get_active_compensation() is None


def test_guardar_dia_rejects_out_of_tolerance_data():
    response = client.post(
        "/generar-dieta/guardar",
        data={
            "target_kcal": "2000", "target_protein_g": "150",
            "target_carbs_g": "200", "target_fat_g": "60",
            "goal": "maintenance",
            "meal_desayuno_food_item": "Avena integral", "meal_desayuno_quantity_grams": "1",
            "meal_desayuno_matched_food_id": "1", "meal_desayuno_kcal": "1",
            "meal_desayuno_protein_g": "1", "meal_desayuno_carbs_g": "1", "meal_desayuno_fat_g": "1",
            "meal_comida_food_item": "Pechuga de pollo", "meal_comida_quantity_grams": "1",
            "meal_comida_matched_food_id": "2", "meal_comida_kcal": "1",
            "meal_comida_protein_g": "1", "meal_comida_carbs_g": "1", "meal_comida_fat_g": "1",
            "meal_merienda_food_item": "Yogur proteico", "meal_merienda_quantity_grams": "1",
            "meal_merienda_matched_food_id": "3", "meal_merienda_kcal": "1",
            "meal_merienda_protein_g": "1", "meal_merienda_carbs_g": "1", "meal_merienda_fat_g": "1",
            "meal_cena_food_item": "Salmon", "meal_cena_quantity_grams": "1",
            "meal_cena_matched_food_id": "4", "meal_cena_kcal": "1",
            "meal_cena_protein_g": "1", "meal_cena_carbs_g": "1", "meal_cena_fat_g": "1",
        },
    )
    assert response.status_code == 400
