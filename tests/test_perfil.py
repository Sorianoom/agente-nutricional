from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _clear_profile():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_profile WHERE id = 1")


def test_get_perfil_empty_shows_form():
    _clear_profile()
    response = client.get("/perfil")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_post_perfil_saves_and_get_reflects_it():
    _clear_profile()
    response = client.post(
        "/perfil",
        data={
            "age": "23",
            "sex": "M",
            "height_cm": "178",
            "activity_level": "moderado",
            "current_goal": "maintenance",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT age, sex, activity_level, current_goal FROM user_profile WHERE id = 1"
            )
            row = cur.fetchone()
    assert row == (23, "M", "moderado", "maintenance")
