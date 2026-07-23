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
