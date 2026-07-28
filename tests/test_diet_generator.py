from app.diet_generator import remaining_budget, within_tolerance

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
