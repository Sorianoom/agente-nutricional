from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app


def _seed_dashboard_data():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM body_metrics WHERE source_pdf_filename = 'test_dashboard.pdf'"
            )
            cur.execute(
                """
                INSERT INTO body_metrics
                    (source_pdf_filename, measured_on, weight_kg, body_fat_pct)
                VALUES ('test_dashboard.pdf', '2026-01-01', 80.0, 20.0)
                """
            )


def test_dashboard_renders_with_data():
    _seed_dashboard_data()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "chart-weight" in response.text
    assert "chart-bodyfat" in response.text
    assert "chart-macros" in response.text
    assert "chart-kcal" in response.text
