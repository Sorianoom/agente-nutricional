import json
import tempfile
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from app.food_matching import find_matching_food

MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g")
MEAL_NAMES = ("desayuno", "comida", "merienda", "cena")

# Misma lista que se excluyó a mano del histórico en el Subsistema 1.
EXCLUDED_FOODS = ("brocoli", "vinagre", "col lombarda", "calabacin")

MAX_ATTEMPTS = 5

# cwd fuera del proyecto: evita heredar hooks/skills de Claude Code de este
# repo, que si no multiplican por ~9x los tokens de cada llamada.
AGENT_CWD = Path(tempfile.gettempdir()) / "agentenutricional_diet_generator"

MEAL_PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "food_item": {"type": "string"},
        "quantity_grams": {"type": "number"},
    },
    "required": ["food_item", "quantity_grams"],
    "additionalProperties": False,
}

DAY_SCHEMA = {
    "type": "object",
    "properties": {name: MEAL_PROPOSAL_SCHEMA for name in MEAL_NAMES},
    "required": list(MEAL_NAMES),
    "additionalProperties": False,
}


def within_tolerance(real: dict, target: dict, pct: float = 0.05) -> bool:
    for key in MACRO_KEYS:
        target_value = target[key]
        if target_value == 0:
            if real[key] != 0:
                return False
            continue
        deviation = abs(real[key] - target_value) / target_value
        if deviation > pct:
            return False
    return True


def remaining_budget(target: dict, fixed_meals: list) -> dict:
    consumed = {key: sum(meal[key] for meal in fixed_meals) for key in MACRO_KEYS}
    return {key: target[key] - consumed[key] for key in MACRO_KEYS}


def _resolve_meal(meal_name: str, proposal: dict) -> dict:
    food_item = proposal["food_item"]
    quantity_grams = proposal["quantity_grams"]
    match = find_matching_food(food_item)
    if match is None:
        return {
            "meal_name": meal_name,
            "food_item": food_item,
            "quantity_grams": quantity_grams,
            "matched_food_id": None,
            "verified": False,
            "kcal": 0.0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
        }
    factor = quantity_grams / 100.0
    return {
        "meal_name": meal_name,
        "food_item": food_item,
        "quantity_grams": quantity_grams,
        "matched_food_id": match["id"],
        "verified": True,
        "kcal": match["kcal_100g"] * factor,
        "protein_g": match["protein_100g"] * factor,
        "carbs_g": match["carbs_100g"] * factor,
        "fat_g": match["fat_100g"] * factor,
    }


def _day_totals(meals: list) -> dict:
    return {key: sum(meal[key] for meal in meals) for key in MACRO_KEYS}


def _call_agent_for_day(target: dict, goal: str, hints: dict, previous_attempt_note: str) -> dict:
    AGENT_CWD.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=(
            "Eres un asistente de nutricion que compone dietas variadas y "
            "realistas con productos de supermercado espanol. Ajusta las "
            "cantidades en gramos para acercarte lo maximo posible a las "
            "kcal y macros objetivo indicadas."
        ),
        max_turns=3,
        cwd=str(AGENT_CWD),
        setting_sources=[],
        allowed_tools=[],
        output_format={"type": "json_schema", "schema": DAY_SCHEMA},
    )
    hints_lines = [f"- {meal}: {hint}" for meal, hint in hints.items() if hint]
    hints_text = ("Directrices por comida (orientacion suave, no exacta):\n" + "\n".join(hints_lines) + "\n") if hints_lines else ""
    prompt = (
        f"Objetivo del dia: {json.dumps(target, ensure_ascii=False)}\n"
        f"Objetivo del usuario: {goal}\n"
        f"Alimentos a evitar: {', '.join(EXCLUDED_FOODS)}\n"
        f"{hints_text}"
        f"{previous_attempt_note}"
        "Propon desayuno, comida, merienda y cena con food_item (nombre de "
        "producto de supermercado espanol) y quantity_grams."
    )

    async def _run() -> dict:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.is_error or message.structured_output is None:
                    raise RuntimeError(f"Generacion de dieta fallida: {message.result}")
                return message.structured_output
        raise RuntimeError("Sin respuesta del agente")

    return anyio.run(_run)


def generate_day(target: dict, goal: str, hints: dict) -> dict:
    note = ""
    meals: list = []
    totals: dict = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proposal = _call_agent_for_day(target, goal, hints, note)
        meals = [_resolve_meal(name, proposal[name]) for name in MEAL_NAMES]
        totals = _day_totals(meals)
        if within_tolerance(totals, target):
            return {"meals": meals, "totals": totals, "within_tolerance": True, "attempts": attempt}
        note = (
            f"Tu propuesta anterior dio como resultado real {json.dumps(totals, ensure_ascii=False)}, "
            f"que no cuadra con el objetivo dentro de un 5%. Ajusta las cantidades para acercarte mas.\n"
        )
    return {"meals": meals, "totals": totals, "within_tolerance": False, "attempts": MAX_ATTEMPTS}
