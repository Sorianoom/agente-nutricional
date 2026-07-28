from fastapi.testclient import TestClient

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
