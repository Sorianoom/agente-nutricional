from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _seed_profile():
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


def test_get_antojo_shows_form():
    response = client.get("/antojo")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_antojo_fits_craving_and_generates_rest(monkeypatch):
    _seed_profile()
    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0, "method_label": "real"},
    )

    fake_rest_of_day = {
        "meals": [
            {"meal_name": "desayuno", "food_item": "Avena integral", "quantity_grams": 100, "matched_food_id": 1, "verified": True, "kcal": 350.0, "protein_g": 13.0, "carbs_g": 60.0, "fat_g": 7.0},
            {"meal_name": "comida", "food_item": "Pechuga de pollo", "quantity_grams": 200, "matched_food_id": 2, "verified": True, "kcal": 220.0, "protein_g": 46.0, "carbs_g": 0.0, "fat_g": 4.0},
            {"meal_name": "cena", "food_item": "Salmon", "quantity_grams": 100, "matched_food_id": 4, "verified": True, "kcal": 200.0, "protein_g": 20.0, "carbs_g": 0.0, "fat_g": 13.0},
        ],
        "totals": {"kcal": 770.0, "protein_g": 79.0, "carbs_g": 60.0, "fat_g": 24.0},
        "within_tolerance": True,
        "attempts": 1,
    }
    monkeypatch.setattr(
        "app.main.generate_day",
        lambda target, goal, hints, meal_names: fake_rest_of_day,
    )

    response = client.post(
        "/antojo",
        data={
            "method": "formula",
            "craving_meal_name": "merienda",
            "craving_food_item": "Chocolate negro",
            "craving_quantity_grams": "30",
        },
    )
    assert response.status_code == 200
    assert "Chocolate negro" in response.text
    assert "Salmon" in response.text


def test_post_antojo_rejects_craving_that_exceeds_target_without_calling_agent(monkeypatch):
    _seed_profile()
    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 100.0, "protein_g": 10.0, "carbs_g": 10.0, "fat_g": 5.0, "method_label": "real"},
    )
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: {"id": 1, "name": name, "kcal_100g": 500.0, "protein_100g": 5.0, "carbs_100g": 60.0, "fat_100g": 25.0},
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("generate_day no debe llamarse cuando el antojo ya excede el objetivo")

    monkeypatch.setattr("app.main.generate_day", _fail_if_called)

    response = client.post(
        "/antojo",
        data={
            "method": "formula",
            "craving_meal_name": "merienda",
            "craving_food_item": "Tarta de chocolate entera",
            "craving_quantity_grams": "500",
        },
    )
    assert response.status_code == 200
    assert "No cabe" in response.text
