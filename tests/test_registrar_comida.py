from datetime import date

from fastapi.testclient import TestClient

from app.compensation import get_active_compensation
from app.db import get_connection
from app.main import app

client = TestClient(app)


def _clear_today_diet_version():
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE valid_from = %s AND valid_to = %s)",
                (today, today),
            )
            cur.execute(
                "DELETE FROM diet_versions WHERE valid_from = %s AND valid_to = %s",
                (today, today),
            )


def _clear_compensation():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")


def test_get_registrar_comida_shows_form():
    response = client.get("/registrar-comida")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_registrar_comida_adds_meal_to_todays_diet_version():
    _clear_today_diet_version()

    response = client.post(
        "/registrar-comida",
        data={"food_item": "Pechuga de pollo", "quantity_grams": "200"},
    )
    assert response.status_code == 200

    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT dm.food_item, dm.quantity_grams FROM diet_meals dm "
                "JOIN diet_versions dv ON dv.id = dm.diet_version_id "
                "WHERE dv.valid_from = %s AND dv.valid_to = %s",
                (today, today),
            )
            rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Pechuga de pollo"


def test_post_registrar_comida_twice_reuses_same_diet_version():
    _clear_today_diet_version()

    client.post("/registrar-comida", data={"food_item": "Avena integral", "quantity_grams": "100"})
    client.post("/registrar-comida", data={"food_item": "Yogur proteico", "quantity_grams": "125"})

    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM diet_versions WHERE valid_from = %s AND valid_to = %s",
                (today, today),
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                "SELECT count(*) FROM diet_meals dm "
                "JOIN diet_versions dv ON dv.id = dm.diet_version_id "
                "WHERE dv.valid_from = %s AND dv.valid_to = %s",
                (today, today),
            )
            assert cur.fetchone()[0] == 2


def test_cerrar_dia_creates_compensation_when_out_of_tolerance(monkeypatch):
    _clear_today_diet_version()
    _clear_compensation()
    add_meal_response = client.post(
        "/registrar-comida",
        data={"food_item": "Pechuga de pollo", "quantity_grams": "2000"},
    )
    assert add_meal_response.status_code == 200

    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0, "method_label": "real"},
    )
    monkeypatch.setattr("app.main.get_user_profile", lambda: {"current_goal": "maintenance"})

    response = client.post("/cerrar-dia")
    assert response.status_code == 200
    assert get_active_compensation() is not None
