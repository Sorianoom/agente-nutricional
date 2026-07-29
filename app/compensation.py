from datetime import date

from app.db import get_connection
from app.diet_generator import MACRO_KEYS, within_tolerance

DAYS_TOTAL = 3


def compute_delta(real_totals: dict, target: dict) -> dict:
    return {
        "kcal_delta": real_totals["kcal"] - target["kcal"],
        "protein_g_delta": real_totals["protein_g"] - target["protein_g"],
        "carbs_g_delta": real_totals["carbs_g"] - target["carbs_g"],
        "fat_g_delta": real_totals["fat_g"] - target["fat_g"],
    }


def get_active_compensation() -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, "
                "days_total, created_at FROM pending_compensation LIMIT 1"
            )
            row = cur.fetchone()
    if row is None:
        return None
    days_elapsed = (date.today() - row[6]).days
    if days_elapsed >= row[5]:
        _delete_compensation(row[0])
        return None
    return {
        "id": row[0],
        "kcal_delta": float(row[1]),
        "protein_g_delta": float(row[2]),
        "carbs_g_delta": float(row[3]),
        "fat_g_delta": float(row[4]),
        "days_total": row[5],
        "created_at": row[6],
        "days_elapsed": days_elapsed,
    }


def _delete_compensation(compensation_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_compensation WHERE id = %s", (compensation_id,))


def _insert_compensation(delta: dict) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_compensation
                    (kcal_delta, protein_g_delta, carbs_g_delta, fat_g_delta, days_total, created_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
                """,
                (
                    delta["kcal_delta"],
                    delta["protein_g_delta"],
                    delta["carbs_g_delta"],
                    delta["fat_g_delta"],
                    DAYS_TOTAL,
                ),
            )


def create_or_merge_compensation(delta: dict) -> None:
    active = get_active_compensation()
    if active is None:
        _insert_compensation(delta)
        return
    remaining_fraction = (active["days_total"] - active["days_elapsed"]) / active["days_total"]
    merged = {
        key: active[key] * remaining_fraction + delta[key]
        for key in ("kcal_delta", "protein_g_delta", "carbs_g_delta", "fat_g_delta")
    }
    _delete_compensation(active["id"])
    _insert_compensation(merged)


def close_day_and_check_compensation(real_totals: dict, target: dict) -> None:
    if within_tolerance(real_totals, target):
        return
    create_or_merge_compensation(compute_delta(real_totals, target))


def replace_or_clear_after_correction(real_totals: dict, target: dict) -> None:
    active = get_active_compensation()
    if active is None:
        close_day_and_check_compensation(real_totals, target)
        return
    if within_tolerance(real_totals, target):
        _delete_compensation(active["id"])
        return
    delta = compute_delta(real_totals, target)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_compensation
                SET kcal_delta = %s, protein_g_delta = %s, carbs_g_delta = %s, fat_g_delta = %s
                WHERE id = %s
                """,
                (
                    delta["kcal_delta"],
                    delta["protein_g_delta"],
                    delta["carbs_g_delta"],
                    delta["fat_g_delta"],
                    active["id"],
                ),
            )


def apply_pending_compensation(target: dict) -> dict:
    active = get_active_compensation()
    if active is None:
        return dict(target)
    days_total = active["days_total"]
    adjusted = dict(target)
    adjusted["kcal"] = target["kcal"] - active["kcal_delta"] / days_total
    adjusted["protein_g"] = target["protein_g"] - active["protein_g_delta"] / days_total
    adjusted["carbs_g"] = target["carbs_g"] - active["carbs_g_delta"] / days_total
    adjusted["fat_g"] = target["fat_g"] - active["fat_g_delta"] / days_total
    return adjusted
