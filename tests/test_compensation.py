from datetime import date, timedelta

from app.db import get_connection
from app.compensation import (
    apply_pending_compensation,
    close_day_and_check_compensation,
    compute_delta,
    create_or_merge_compensation,
    get_active_compensation,
    replace_or_clear_after_correction,
)

TARGET = {"kcal": 2000.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}


def _clear_compensation():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation")


def test_compute_delta_subtracts_target_from_real():
    real = {"kcal": 2300.0, "protein_g": 140.0, "carbs_g": 210.0, "fat_g": 70.0}
    delta = compute_delta(real, TARGET)
    assert delta == {
        "kcal_delta": 300.0, "protein_g_delta": -10.0,
        "carbs_g_delta": 10.0, "fat_g_delta": 10.0,
    }


def test_close_day_within_tolerance_creates_nothing():
    _clear_compensation()
    real = {k: v * 1.02 for k, v in TARGET.items()}
    close_day_and_check_compensation(real, TARGET)
    assert get_active_compensation() is None


def test_close_day_out_of_tolerance_creates_compensation():
    _clear_compensation()
    real = {"kcal": 2300.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}
    close_day_and_check_compensation(real, TARGET)
    active = get_active_compensation()
    assert active is not None
    assert active["kcal_delta"] == 300.0
    assert active["days_total"] == 3


def test_apply_pending_compensation_adjusts_target():
    _clear_compensation()
    create_or_merge_compensation({
        "kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    adjusted = apply_pending_compensation(dict(TARGET))
    assert adjusted["kcal"] == 2000.0 - 100.0
    assert adjusted["protein_g"] == 150.0


def test_active_compensation_expires_after_days_total():
    _clear_compensation()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pending_compensation "
                "(kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, days_total, created_at) "
                "VALUES (300, 0, 0, 0, 3, %s)",
                ((date.today() - timedelta(days=3)).isoformat(),),
            )
    assert get_active_compensation() is None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pending_compensation")
            assert cur.fetchone()[0] == 0


def test_create_or_merge_sums_remaining_fraction_of_previous_delta():
    _clear_compensation()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pending_compensation "
                "(kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, days_total, created_at) "
                "VALUES (300, 0, 0, 0, 3, %s)",
                ((date.today() - timedelta(days=1)).isoformat(),),
            )
    # Quedaba 1 dia transcurrido de 3 -> restante = 300 * (3-1)/3 = 200.
    create_or_merge_compensation({
        "kcal_delta": 150.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    active = get_active_compensation()
    assert active["kcal_delta"] == 350.0
    assert active["days_total"] == 3


def test_replace_or_clear_after_correction_deletes_when_now_within_tolerance():
    _clear_compensation()
    create_or_merge_compensation({
        "kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    replace_or_clear_after_correction(dict(TARGET), TARGET)
    assert get_active_compensation() is None


def test_replace_or_clear_after_correction_updates_delta_when_still_off():
    _clear_compensation()
    create_or_merge_compensation({
        "kcal_delta": 300.0, "protein_g_delta": 0.0, "carbs_g_delta": 0.0, "fat_g_delta": 0.0,
    })
    corrected_real = {"kcal": 2150.0, "protein_g": 150.0, "carbs_g": 200.0, "fat_g": 60.0}
    replace_or_clear_after_correction(corrected_real, TARGET)
    active = get_active_compensation()
    assert active["kcal_delta"] == 150.0
