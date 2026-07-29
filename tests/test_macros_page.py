from fastapi.testclient import TestClient

from app.compensation import create_or_merge_compensation
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


def test_macros_page_falls_back_to_mifflin_without_enough_body_metrics():
    _seed_profile()
    response = client.get("/macros")
    assert response.status_code == 200
    assert "mifflin" in response.text.lower() or "formula" in response.text.lower()


def test_macros_page_requires_profile():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_profile WHERE id = 1")
    response = client.get("/macros")
    assert response.status_code == 200
    assert "perfil" in response.text.lower()


def test_recalcular_ia_saves_and_returns_partial(monkeypatch):
    _seed_profile()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM macro_targets WHERE method = 'agent' "
                "AND explanation = 'Recomendacion de prueba.'"
            )

    def fake_compute_sync(summary):
        return {
            "kcal": 2400,
            "protein_g": 180,
            "carbs_g": 250,
            "fat_g": 67,
            "explanation": "Recomendacion de prueba.",
        }

    monkeypatch.setattr("app.main.compute_agent_macro_target", fake_compute_sync)

    response = client.post("/macros/recalcular-ia")
    assert response.status_code == 200
    assert "Recomendacion de prueba" in response.text

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM macro_targets WHERE method = 'agent' "
                "AND explanation = 'Recomendacion de prueba.'"
            )
            count = cur.fetchone()[0]
    assert count == 1


def test_macros_page_shows_compensation_adjusted_target(monkeypatch):
    _seed_profile()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")

    monkeypatch.setattr(
        "app.main.compute_formula_macro_target",
        lambda profile: {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0, "method_label": "real"},
    )
    create_or_merge_compensation(
        {"kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0}
    )

    response = client.get("/macros")
    assert response.status_code == 200
    assert "1900" in response.text
