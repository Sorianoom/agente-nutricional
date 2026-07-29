from datetime import date

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _seed_recent_diet_version():
    today = date.today().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'test_corregir')"
            )
            cur.execute("DELETE FROM diet_versions WHERE source_pdf_filename = 'test_corregir'")
            cur.execute(
                "INSERT INTO diet_versions (source_pdf_filename, valid_from, valid_to) "
                "VALUES ('test_corregir', %s, %s) RETURNING id",
                (today, today),
            )
            diet_version_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO diet_meals (diet_version_id, day_label, meal_name, food_item, quantity_grams) "
                "VALUES (%s, 'dia', 'cena', 'Salmon', 150) RETURNING id",
                (diet_version_id,),
            )
            return cur.fetchone()[0]


def test_get_corregir_shows_most_recent_meals():
    _seed_recent_diet_version()
    response = client.get("/corregir")
    assert response.status_code == 200
    assert "Salmon" in response.text


def test_post_corregir_updates_meal():
    meal_id = _seed_recent_diet_version()
    response = client.post(
        f"/corregir/{meal_id}",
        data={"food_item": "Merluza", "quantity_grams": "180"},
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT food_item, quantity_grams FROM diet_meals WHERE id = %s", (meal_id,))
            row = cur.fetchone()
    assert row[0] == "Merluza"
    assert float(row[1]) == 180.0
