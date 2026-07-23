from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def test_post_medidas_inserts_manual_row():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM body_metrics WHERE measured_on = '2026-07-20' "
                "AND source_pdf_filename = 'manual'"
            )

    response = client.post(
        "/medidas",
        data={
            "measured_on": "2026-07-20",
            "weight_kg": "78.5",
            "body_fat_pct": "15.2",
            "muscle_mass_kg": "36.0",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT weight_kg, body_fat_pct, muscle_mass_kg, source_pdf_filename "
                "FROM body_metrics WHERE measured_on = '2026-07-20' AND source_pdf_filename = 'manual'"
            )
            row = cur.fetchone()
    assert row is not None
    assert float(row[0]) == 78.5
    assert float(row[1]) == 15.2
    assert float(row[2]) == 36.0
    assert row[3] == "manual"


def test_get_medidas_shows_form():
    response = client.get("/medidas")
    assert response.status_code == 200
    assert "form" in response.text.lower()
