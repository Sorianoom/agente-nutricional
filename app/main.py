import json

import anyio
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.agent_macros import compute_agent_macro_target
from app.db import get_connection
from app.diet_generator import (
    MEAL_NAMES,
    _day_totals,
    generate_day,
    generate_single_meal,
    remaining_budget,
    within_tolerance,
)
from app.macros import compute_real_tdee, mifflin_st_jeor, split_macros

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


def get_body_metrics_for_tdee() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT measured_on, weight_kg, body_fat_pct FROM body_metrics "
                "WHERE weight_kg IS NOT NULL AND body_fat_pct IS NOT NULL "
                "ORDER BY measured_on"
            )
            rows = cur.fetchall()
    return [
        {"measured_on": row[0], "weight_kg": float(row[1]), "body_fat_pct": float(row[2])}
        for row in rows
    ]


def get_diet_versions_daily_kcal() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dv.valid_from,
                    dv.valid_to,
                    COALESCE(SUM(dm.quantity_grams / 100.0 * f.kcal_100g), 0)
                        / NULLIF(COUNT(DISTINCT dm.day_label), 0) AS daily_kcal
                FROM diet_versions dv
                LEFT JOIN diet_meals dm ON dm.diet_version_id = dv.id
                LEFT JOIN foods f ON f.id = dm.matched_food_id
                GROUP BY dv.id, dv.valid_from, dv.valid_to
                ORDER BY dv.valid_from
                """
            )
            rows = cur.fetchall()
    return [
        {"valid_from": row[0], "valid_to": row[1], "daily_kcal": float(row[2] or 0)}
        for row in rows
    ]


def get_latest_agent_macro_target() -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT goal, kcal, protein_g, carbs_g, fat_g, explanation, computed_at
                FROM macro_targets WHERE method = 'agent'
                ORDER BY computed_at DESC LIMIT 1
                """
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "goal": row[0],
        "kcal": float(row[1]),
        "protein_g": float(row[2]),
        "carbs_g": float(row[3]),
        "fat_g": float(row[4]),
        "explanation": row[5],
        "computed_at": row[6].isoformat(),
    }


def compute_formula_macro_target(profile: dict) -> dict:
    body_metrics = get_body_metrics_for_tdee()
    latest_weight = body_metrics[-1]["weight_kg"] if body_metrics else None
    if latest_weight is None:
        raise ValueError("No hay medidas corporales para calcular macros objetivo")

    tdee = compute_real_tdee(body_metrics, get_diet_versions_daily_kcal())
    method_label = "real"
    if tdee is None:
        method_label = "mifflin"
        tdee = mifflin_st_jeor(
            age=profile["age"],
            sex=profile["sex"],
            height_cm=profile["height_cm"],
            weight_kg=latest_weight,
            activity_level=profile["activity_level"],
        )
    result = split_macros(tdee, profile["current_goal"], latest_weight)
    result["method_label"] = method_label
    return result


@app.get("/macros")
def macros_page(request: Request):
    profile = get_user_profile()
    template = templates.get_template("macros.html")
    if profile is None:
        return HTMLResponse(
            template.render({"request": request, "profile": None})
        )
    formula_result = compute_formula_macro_target(profile)
    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": profile,
                "formula": formula_result,
                "agent": get_latest_agent_macro_target(),
            }
        )
    )


def save_agent_macro_target(goal: str, result: dict) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO macro_targets (method, goal, kcal, protein_g, carbs_g, fat_g, explanation)
                VALUES ('agent', %s, %s, %s, %s, %s, %s)
                """,
                (
                    goal,
                    result["kcal"],
                    result["protein_g"],
                    result["carbs_g"],
                    result["fat_g"],
                    result["explanation"],
                ),
            )


@app.post("/macros/recalcular-ia")
def macros_recalcular_ia(request: Request):
    profile = get_user_profile()
    body_metrics = get_body_metrics_for_tdee()
    real_tdee = compute_real_tdee(body_metrics, get_diet_versions_daily_kcal())
    summary = {
        "profile": profile,
        "goal": profile["current_goal"],
        "real_tdee": real_tdee,
        "weight_history": [
            {
                "date": m["measured_on"].isoformat(),
                "weight_kg": m["weight_kg"],
                "body_fat_pct": m["body_fat_pct"],
            }
            for m in body_metrics
        ],
    }
    result = compute_agent_macro_target(summary)
    save_agent_macro_target(profile["current_goal"], result)

    template = templates.get_template("_agent_result.html")
    return HTMLResponse(
        template.render({"request": request, "agent": get_latest_agent_macro_target()})
    )


def _current_macro_target(method: str, profile: dict) -> tuple[dict, str] | None:
    if method == "formula":
        try:
            result = compute_formula_macro_target(profile)
        except ValueError:
            return None
        return result, profile["current_goal"]
    agent_result = get_latest_agent_macro_target()
    if agent_result is None:
        return None
    return agent_result, agent_result["goal"]


@app.get("/generar-dieta")
def generar_dieta_form(request: Request):
    profile = get_user_profile()
    template = templates.get_template("generar_dieta.html")
    return HTMLResponse(
        template.render({"request": request, "profile": profile, "meal_names": MEAL_NAMES, "day": None})
    )


@app.post("/generar-dieta")
def generar_dieta_generate(
    request: Request,
    method: str = Form(...),
    hint_desayuno: str = Form(""),
    hint_comida: str = Form(""),
    hint_merienda: str = Form(""),
    hint_cena: str = Form(""),
):
    profile = get_user_profile()
    template = templates.get_template("generar_dieta.html")
    if profile is None:
        return HTMLResponse(
            template.render({"request": request, "profile": None, "meal_names": MEAL_NAMES, "day": None})
        )

    target = _current_macro_target(method, profile)
    if target is None:
        return HTMLResponse(
            template.render(
                {
                    "request": request,
                    "profile": profile,
                    "meal_names": MEAL_NAMES,
                    "day": None,
                    "no_target_available": True,
                    "method": method,
                }
            )
        )

    macro_target, goal = target
    hints = {
        "desayuno": hint_desayuno,
        "comida": hint_comida,
        "merienda": hint_merienda,
        "cena": hint_cena,
    }
    day = generate_day(macro_target, goal, hints)

    return HTMLResponse(
        template.render(
            {
                "request": request,
                "profile": profile,
                "meal_names": MEAL_NAMES,
                "day": day,
                "target": macro_target,
                "goal": goal,
                "method": method,
                "hints": hints,
            }
        )
    )


def _meal_from_form_fields(form: dict, meal_name: str) -> dict:
    return {
        "meal_name": meal_name,
        "food_item": form[f"meal_{meal_name}_food_item"],
        "quantity_grams": float(form[f"meal_{meal_name}_quantity_grams"]),
        "matched_food_id": int(form[f"meal_{meal_name}_matched_food_id"]) if form[f"meal_{meal_name}_matched_food_id"] else None,
        "verified": bool(form[f"meal_{meal_name}_matched_food_id"]),
        "kcal": float(form[f"meal_{meal_name}_kcal"]),
        "protein_g": float(form[f"meal_{meal_name}_protein_g"]),
        "carbs_g": float(form[f"meal_{meal_name}_carbs_g"]),
        "fat_g": float(form[f"meal_{meal_name}_fat_g"]),
    }


@app.post("/generar-dieta/comida")
async def generar_dieta_comida(request: Request):
    form = dict((await request.form()).items())
    meal_name = form["meal_name"]
    target = {
        "kcal": float(form["target_kcal"]),
        "protein_g": float(form["target_protein_g"]),
        "carbs_g": float(form["target_carbs_g"]),
        "fat_g": float(form["target_fat_g"]),
    }
    goal = form["goal"]
    other_meals = [_meal_from_form_fields(form, name) for name in MEAL_NAMES if name != meal_name]
    budget = remaining_budget(target, other_meals)
    hint = form.get(f"hint_{meal_name}_new", "")

    # generate_single_meal() es sincrona y llama internamente a anyio.run()
    # (via _call_agent_for_meal) para invocar el Agent SDK. Esta ruta es
    # `async def` (necesitamos `await request.form()`), por lo que se ejecuta
    # directamente en el event loop principal de uvicorn: llamarla sin mas
    # revienta con "RuntimeError: Already running asyncio in this thread"
    # porque anyio.run() no puede arrancar un loop nuevo dentro de uno que ya
    # esta corriendo. La ruta GET/POST /generar-dieta (sync def) no tiene
    # este problema porque FastAPI ya la ejecuta en un hilo de threadpool
    # (via run_in_threadpool) sin loop propio. Aqui replicamos eso a mano
    # despachando la llamada a un hilo de threadpool con anyio.to_thread.
    # Confirmado reproduciendo el fallo real contra el servidor en marcha
    # (ver task-5-report.md) antes de aplicar este fix.
    new_meal = await anyio.to_thread.run_sync(generate_single_meal, meal_name, budget, goal, hint)
    all_meals = other_meals + [new_meal]
    day = {
        "meals": sorted(all_meals, key=lambda m: MEAL_NAMES.index(m["meal_name"])),
        "totals": _day_totals(all_meals),
        "within_tolerance": within_tolerance(_day_totals(all_meals), target),
        "attempts": new_meal["attempts"],
    }

    meal_card = templates.get_template("_meal_card.html").render({"meal": new_meal})
    guardar_section = templates.get_template("_guardar_section.html").render({"day": day})
    return HTMLResponse(
        meal_card + f'<div id="guardar-section" hx-swap-oob="true">{guardar_section}</div>'
    )


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
