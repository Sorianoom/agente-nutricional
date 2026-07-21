import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

MERCAAPI_BASE = "https://mercaapi.sgn.space/api/products/"
PAGE_SIZE = 100
MAX_RETRIES = 3


def fetch_all_products() -> list[dict]:
    products: list[dict] = []
    skip = 0
    while True:
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    MERCAAPI_BASE,
                    params={"limit": PAGE_SIZE, "skip": skip},
                    timeout=10,
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        "No se pudo contactar con mercaapi.sgn.space tras "
                        f"{MAX_RETRIES} intentos. Revisa manualmente el dump "
                        "de https://github.com/datania/mercadona-catalog "
                        "como alternativa."
                    )
                time.sleep(2**attempt)
        page = response.json()
        if not page:
            break
        products.extend(page)
        skip += PAGE_SIZE
    return products


def upsert_foods(products: list[dict]) -> int:
    rows = []
    for product in products:
        if not product.get("is_food"):
            continue
        info = product.get("nutritional_information")
        if not info:
            continue
        rows.append(
            (
                product["id"],
                product["name"],
                product["category"]["name"],
                info["calories"],
                info["protein"],
                info["total_carbohydrate"],
                info["total_fat"],
                info["dietary_fiber"],
            )
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO foods (
                    mercadona_product_id, name, category,
                    kcal_100g, protein_100g, carbs_100g, fat_100g, fiber_100g
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (mercadona_product_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    kcal_100g = EXCLUDED.kcal_100g,
                    protein_100g = EXCLUDED.protein_100g,
                    carbs_100g = EXCLUDED.carbs_100g,
                    fat_100g = EXCLUDED.fat_100g,
                    fiber_100g = EXCLUDED.fiber_100g,
                    synced_at = now()
                """,
                rows,
            )
    return len(rows)


if __name__ == "__main__":
    all_products = fetch_all_products()
    inserted = upsert_foods(all_products)
    print(f"Sincronizados {inserted} alimentos.")
