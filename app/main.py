import json

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import get_connection

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

ACTIVITY_LEVELS = ["sedentario", "ligero", "moderado", "intenso"]
GOALS = ["deficit", "maintenance", "surplus"]


def get_user_profile() -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT age, sex, height_cm, activity_level, current_goal "
                "FROM user_profile WHERE id = 1"
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "age": row[0],
        "sex": row[1],
        "height_cm": float(row[2]),
        "activity_level": row[3],
        "current_goal": row[4],
    }


def save_user_profile(
    age: int, sex: str, height_cm: float, activity_level: str, current_goal: str
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_profile (id, age, sex, height_cm, activity_level, current_goal, updated_at)
                VALUES (1, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    age = EXCLUDED.age,
                    sex = EXCLUDED.sex,
                    height_cm = EXCLUDED.height_cm,
                    activity_level = EXCLUDED.activity_level,
                    current_goal = EXCLUDED.current_goal,
                    updated_at = now()
                """,
                (age, sex, height_cm, activity_level, current_goal),
            )


@app.get("/health")
def health():
    return {"status": "ok"}


def get_body_metrics_series() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT measured_on, weight_kg, body_fat_pct "
                "FROM body_metrics ORDER BY measured_on"
            )
            rows = cur.fetchall()
    return [
        {
            "date": row[0].isoformat(),
            "weight_kg": float(row[1]) if row[1] is not None else None,
            "body_fat_pct": float(row[2]) if row[2] is not None else None,
        }
        for row in rows
    ]


def get_diet_macros_series() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dv.valid_from,
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.kcal_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.protein_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.carbs_100g), 0),
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.fat_100g), 0)
                FROM diet_versions dv
                LEFT JOIN diet_meals dm ON dm.diet_version_id = dv.id
                LEFT JOIN foods f ON f.id = dm.matched_food_id
                GROUP BY dv.id, dv.valid_from
                ORDER BY dv.valid_from
                """
            )
            rows = cur.fetchall()
    return [
        {
            "valid_from": row[0].isoformat(),
            "kcal": float(row[1]),
            "protein_g": float(row[2]),
            "carbs_g": float(row[3]),
            "fat_g": float(row[4]),
        }
        for row in rows
    ]


@app.get("/perfil")
def perfil_form(request: Request):
    template = templates.get_template("perfil.html")
    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": get_user_profile(),
                "activity_levels": ACTIVITY_LEVELS,
                "goals": GOALS,
            }
        )
    )


@app.post("/perfil")
def perfil_save(
    age: int = Form(...),
    sex: str = Form(...),
    height_cm: float = Form(...),
    activity_level: str = Form(...),
    current_goal: str = Form(...),
):
    save_user_profile(age, sex, height_cm, activity_level, current_goal)
    return RedirectResponse("/perfil", status_code=303)


def save_manual_body_metric(
    measured_on: str, weight_kg: float, body_fat_pct: float, muscle_mass_kg: float
) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO body_metrics
                    (source_pdf_filename, measured_on, weight_kg, body_fat_pct, muscle_mass_kg)
                VALUES ('manual', %s, %s, %s, %s)
                RETURNING id
                """,
                (measured_on, weight_kg, body_fat_pct, muscle_mass_kg),
            )
            return cur.fetchone()[0]


@app.get("/medidas")
def medidas_form(request: Request):
    template = templates.get_template("medidas.html")
    return HTMLResponse(
        template.render({"request": request, "medidas": get_body_metrics_series()})
    )


@app.post("/medidas")
def medidas_save(
    measured_on: str = Form(...),
    weight_kg: float = Form(...),
    body_fat_pct: float = Form(...),
    muscle_mass_kg: float = Form(...),
):
    save_manual_body_metric(measured_on, weight_kg, body_fat_pct, muscle_mass_kg)
    return RedirectResponse("/medidas", status_code=303)


@app.get("/")
def dashboard(request: Request):
    body_metrics_json = json.dumps(get_body_metrics_series())
    diet_macros_json = json.dumps(get_diet_macros_series())
    context = {
        "request": request,
        "body_metrics_json": body_metrics_json,
        "diet_macros_json": diet_macros_json,
    }
    template = templates.get_template("dashboard.html")
    return HTMLResponse(template.render(context))
