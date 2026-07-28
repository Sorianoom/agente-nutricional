MACRO_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g")
MEAL_NAMES = ("desayuno", "comida", "merienda", "cena")

# Misma lista que se excluyó a mano del histórico en el Subsistema 1.
EXCLUDED_FOODS = ("brocoli", "vinagre", "col lombarda", "calabacin")

MAX_ATTEMPTS = 5


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
