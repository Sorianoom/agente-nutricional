import json

from claude_agent_sdk import ResultMessage

from app.diet_generator import generate_day, remaining_budget, within_tolerance

TARGET = {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}


def test_within_tolerance_true_when_exact_match():
    assert within_tolerance(TARGET, TARGET) is True


def test_within_tolerance_true_at_edge_of_five_percent():
    real = {k: v * 1.05 for k, v in TARGET.items()}
    assert within_tolerance(real, TARGET, pct=0.05) is True


def test_within_tolerance_false_when_one_macro_exceeds_margin():
    real = dict(TARGET)
    real["protein_g"] = TARGET["protein_g"] * 1.20
    assert within_tolerance(real, TARGET, pct=0.05) is False


def test_within_tolerance_false_when_kcal_off():
    real = dict(TARGET)
    real["kcal"] = TARGET["kcal"] * 0.5
    assert within_tolerance(real, TARGET, pct=0.05) is False


def test_remaining_budget_subtracts_fixed_meals():
    fixed_meals = [
        {"kcal": 500.0, "protein_g": 40.0, "carbs_g": 50.0, "fat_g": 15.0},
        {"kcal": 700.0, "protein_g": 50.0, "carbs_g": 70.0, "fat_g": 20.0},
    ]
    budget = remaining_budget(TARGET, fixed_meals)
    assert budget == {"kcal": 800.0, "protein_g": 60.0, "carbs_g": 80.0, "fat_g": 25.0}


def test_remaining_budget_with_no_fixed_meals_equals_target():
    assert remaining_budget(TARGET, []) == TARGET


# Coincide exactamente con los totales que produce GOOD_PROPOSAL via
# FAKE_MATCHES (100g avena + 200g pollo + 125g yogur + 150g salmon), para que
# el "primer intento bueno" sea determinista dentro de margen. El plan
# original usaba {2000, 150, 200, 60}, que no cuadra con estos alimentos
# fijos (desviacion >50% en kcal) y hacia imposible attempts == 1.
DAY_TARGET = {"kcal": 982.5, "protein_g": 101.5, "carbs_g": 70.0, "fat_g": 33.0}

GOOD_PROPOSAL = {
    "desayuno": {"food_item": "avena integral", "quantity_grams": 100},
    "comida": {"food_item": "pechuga de pollo", "quantity_grams": 200},
    "merienda": {"food_item": "yogur proteico", "quantity_grams": 125},
    "cena": {"food_item": "salmon", "quantity_grams": 150},
}

FAKE_MATCHES = {
    "avena integral": {"id": 1, "name": "Avena integral", "kcal_100g": 350, "protein_100g": 13, "carbs_100g": 60, "fat_100g": 7},
    "pechuga de pollo": {"id": 2, "name": "Pechuga de pollo", "kcal_100g": 110, "protein_100g": 23, "carbs_100g": 0, "fat_100g": 2},
    "yogur proteico": {"id": 3, "name": "Yogur proteico", "kcal_100g": 90, "protein_100g": 10, "carbs_100g": 8, "fat_100g": 2},
    "salmon": {"id": 4, "name": "Salmon", "kcal_100g": 200, "protein_100g": 20, "carbs_100g": 0, "fat_100g": 13},
}


def _fake_result(structured_output):
    return ResultMessage(
        subtype="success", duration_ms=100, duration_api_ms=90, is_error=False,
        num_turns=1, session_id="test-session",
        structured_output=structured_output, result=json.dumps(structured_output),
    )


def test_generate_day_returns_within_tolerance_on_first_good_attempt(monkeypatch):
    async def fake_query(prompt, options):
        yield _fake_result(GOOD_PROPOSAL)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    result = generate_day(DAY_TARGET, "maintenance", {})
    assert result["attempts"] == 1
    assert len(result["meals"]) == 4
    # No afirmamos aqui que de la casualidad dentro de margen; solo que la
    # estructura y el conteo de intentos son correctos con un mock fijo.


def test_generate_day_retries_until_max_attempts_when_never_within_tolerance(monkeypatch):
    bad_proposal = {
        "desayuno": {"food_item": "avena integral", "quantity_grams": 1},
        "comida": {"food_item": "pechuga de pollo", "quantity_grams": 1},
        "merienda": {"food_item": "yogur proteico", "quantity_grams": 1},
        "cena": {"food_item": "salmon", "quantity_grams": 1},
    }
    call_count = {"n": 0}

    async def fake_query(prompt, options):
        call_count["n"] += 1
        yield _fake_result(bad_proposal)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    result = generate_day(DAY_TARGET, "maintenance", {})
    assert result["within_tolerance"] is False
    assert result["attempts"] == 5
    assert call_count["n"] == 5


def test_generate_day_includes_hints_in_prompt(monkeypatch):
    captured_prompts = []

    async def fake_query(prompt, options):
        captured_prompts.append(prompt)
        yield _fake_result(GOOD_PROPOSAL)

    monkeypatch.setattr("app.diet_generator.query", fake_query)
    monkeypatch.setattr(
        "app.diet_generator.find_matching_food",
        lambda name: FAKE_MATCHES.get(name),
    )

    generate_day(DAY_TARGET, "maintenance", {"desayuno": "jamon"})
    assert "jamon" in captured_prompts[0]
