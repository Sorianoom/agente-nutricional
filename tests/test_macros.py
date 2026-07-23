from datetime import date

import pytest

from app.macros import compute_real_tdee, mifflin_st_jeor, split_macros


def test_compute_real_tdee_with_single_segment():
    # Peso constante (80kg), pero el % de grasa baja de 20% a 18.75%:
    # masa grasa 16kg -> 15kg, exactamente 1kg perdido en 10 dias comiendo
    # 2000 kcal/dia de media.
    # 1kg * 9300 kcal/kg = 9300 kcal de deficit acumulado -> 930 kcal/dia.
    # TDEE = 2000 (comido) + 930 (deficit cubierto por la grasa perdida) = 2930.
    body_metrics = [
        {"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0},
        {"measured_on": date(2026, 1, 11), "weight_kg": 80.0, "body_fat_pct": 18.75},
    ]
    diet_daily_kcal = [
        {"valid_from": date(2026, 1, 1), "valid_to": None, "daily_kcal": 2000.0},
    ]
    tdee = compute_real_tdee(body_metrics, diet_daily_kcal)
    assert tdee == pytest.approx(2930.0, abs=1.0)


def test_compute_real_tdee_averages_multiple_segments():
    body_metrics = [
        {"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0},
        {"measured_on": date(2026, 1, 11), "weight_kg": 80.0, "body_fat_pct": 18.75},
        {"measured_on": date(2026, 1, 21), "weight_kg": 80.0, "body_fat_pct": 18.75},
    ]
    diet_daily_kcal = [
        {"valid_from": date(2026, 1, 1), "valid_to": None, "daily_kcal": 2000.0},
        {"valid_from": date(2026, 1, 12), "valid_to": None, "daily_kcal": 2930.0},
    ]
    tdee = compute_real_tdee(body_metrics, diet_daily_kcal)
    # Primer tramo: ~2930 (deficit). Segundo tramo: 2930 (mantenimiento, sin cambio de grasa).
    assert tdee == pytest.approx(2930.0, abs=1.0)


def test_compute_real_tdee_returns_none_with_fewer_than_two_measurements():
    assert compute_real_tdee([{"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0}], []) is None


def test_compute_real_tdee_skips_segments_without_diet_data():
    body_metrics = [
        {"measured_on": date(2026, 1, 1), "weight_kg": 80.0, "body_fat_pct": 20.0},
        {"measured_on": date(2026, 1, 11), "weight_kg": 79.0, "body_fat_pct": 18.86},
    ]
    assert compute_real_tdee(body_metrics, []) is None


def test_mifflin_st_jeor_male():
    tdee = mifflin_st_jeor(age=23, sex="M", height_cm=178, weight_kg=75, activity_level="moderado")
    bmr = 10 * 75 + 6.25 * 178 - 5 * 23 + 5
    assert tdee == pytest.approx(bmr * 1.55)


def test_mifflin_st_jeor_female():
    tdee = mifflin_st_jeor(age=30, sex="F", height_cm=165, weight_kg=60, activity_level="sedentario")
    bmr = 10 * 60 + 6.25 * 165 - 5 * 30 - 161
    assert tdee == pytest.approx(bmr * 1.2)


def test_split_macros_deficit():
    result = split_macros(tdee=2500, goal="deficit", weight_kg=80)
    assert result["kcal"] == pytest.approx(2000, abs=1)
    assert result["protein_g"] == pytest.approx(176, abs=1)  # 2.2 g/kg
    assert result["fat_g"] == pytest.approx(2000 * 0.25 / 9, abs=1)
    assert result["kcal"] == pytest.approx(
        result["protein_g"] * 4 + result["carbs_g"] * 4 + result["fat_g"] * 9, abs=2
    )


def test_split_macros_maintenance_and_surplus_use_lower_protein_ratio():
    maintenance = split_macros(tdee=2500, goal="maintenance", weight_kg=80)
    surplus = split_macros(tdee=2500, goal="surplus", weight_kg=80)
    assert maintenance["kcal"] == pytest.approx(2500, abs=1)
    assert surplus["kcal"] == pytest.approx(2750, abs=1)
    assert maintenance["protein_g"] == pytest.approx(144, abs=1)  # 1.8 g/kg
    assert surplus["protein_g"] == pytest.approx(144, abs=1)
