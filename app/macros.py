ACTIVITY_MULTIPLIERS = {
    "sedentario": 1.2,
    "ligero": 1.375,
    "moderado": 1.55,
    "intenso": 1.725,
}

GOAL_KCAL_ADJUSTMENTS = {
    "deficit": 0.8,
    "maintenance": 1.0,
    "surplus": 1.1,
}

FAT_MASS_KCAL_PER_KG = 9300
FAT_KCAL_PER_G = 9
PROTEIN_KCAL_PER_G = 4
CARBS_KCAL_PER_G = 4
FAT_PCT_OF_KCAL = 0.25


def compute_real_tdee(body_metrics: list[dict], diet_daily_kcal: list[dict]) -> float | None:
    if len(body_metrics) < 2:
        return None

    segment_tdees = []
    for m1, m2 in zip(body_metrics, body_metrics[1:]):
        days = (m2["measured_on"] - m1["measured_on"]).days
        if days <= 0:
            continue

        versions_in_range = [
            v
            for v in diet_daily_kcal
            if m1["measured_on"] <= v["valid_from"] < m2["measured_on"]
        ]
        if not versions_in_range:
            continue
        avg_daily_kcal = sum(v["daily_kcal"] for v in versions_in_range) / len(
            versions_in_range
        )

        fat_mass_1 = m1["weight_kg"] * m1["body_fat_pct"] / 100
        fat_mass_2 = m2["weight_kg"] * m2["body_fat_pct"] / 100
        fat_energy_change = (fat_mass_1 - fat_mass_2) * FAT_MASS_KCAL_PER_KG

        segment_tdees.append(avg_daily_kcal + fat_energy_change / days)

    if not segment_tdees:
        return None
    return sum(segment_tdees) / len(segment_tdees)


def mifflin_st_jeor(
    age: int, sex: str, height_cm: float, weight_kg: float, activity_level: str
) -> float:
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    bmr += 5 if sex == "M" else -161
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


def split_macros(tdee: float, goal: str, weight_kg: float) -> dict:
    target_kcal = tdee * GOAL_KCAL_ADJUSTMENTS[goal]
    protein_per_kg = 2.2 if goal == "deficit" else 1.8
    # protein_g y fat_g se redondean primero, y carbs_g se deriva como el
    # resto real de kcal tras ese redondeo. Si en cambio se calculara
    # carbs_g a partir de los valores SIN redondear (como en el borrador
    # original del plan) y luego se redondeara cada macro por separado, la
    # suma de las tres kcal reportadas ya no cuadraria con el kcal objetivo
    # reportado (p.ej. 2000 kcal objetivo -> 704 + 796 + 504 = 2004 kcal,
    # un desfase de 4 kcal que supera la tolerancia del test). Redondear
    # protein_g/fat_g antes de derivar carbs_g garantiza que
    # protein_g*4 + carbs_g*4 + fat_g*9 == kcal exactamente (o con el
    # minimo error de redondeo de carbs_g, < 2 kcal).
    protein_g = round(weight_kg * protein_per_kg)
    fat_g = round((target_kcal * FAT_PCT_OF_KCAL) / FAT_KCAL_PER_G)
    remaining_kcal = target_kcal - protein_g * PROTEIN_KCAL_PER_G - fat_g * FAT_KCAL_PER_G
    carbs_g = round(remaining_kcal / CARBS_KCAL_PER_G)
    return {
        "kcal": round(target_kcal),
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }
