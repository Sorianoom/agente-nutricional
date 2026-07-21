from unittest.mock import MagicMock, patch

from app.db import get_connection
from scripts.sync_foods import fetch_all_products, upsert_foods

FAKE_PRODUCT = {
    "id": "test-99999",
    "name": "Producto de prueba",
    "is_food": True,
    "category": {"name": "Categoria de prueba"},
    "nutritional_information": {
        "calories": 100.0,
        "protein": 10.0,
        "total_carbohydrate": 20.0,
        "total_fat": 5.0,
        "dietary_fiber": 2.0,
    },
}


def _fake_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("scripts.sync_foods.requests.get")
def test_fetch_all_products_paginates_until_empty(mock_get):
    mock_get.side_effect = [
        _fake_response([FAKE_PRODUCT]),
        _fake_response([]),
    ]
    products = fetch_all_products()
    assert products == [FAKE_PRODUCT]
    assert mock_get.call_count == 2


def test_upsert_foods_inserts_and_updates_row():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM foods WHERE mercadona_product_id = 'test-99999'")

    count = upsert_foods([FAKE_PRODUCT])
    assert count == 1

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, kcal_100g FROM foods WHERE mercadona_product_id = 'test-99999'"
            )
            row = cur.fetchone()
    assert row[0] == "Producto de prueba"
    assert float(row[1]) == 100.0
