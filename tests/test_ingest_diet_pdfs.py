import json
from unittest.mock import MagicMock

from app.db import get_connection
from scripts.ingest_diet_pdfs import extract_diet, save_diet


def test_extract_diet_parses_json_response(tmp_path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake content")

    expected = {
        "valid_from": "2026-01-01",
        "valid_to": None,
        "meals": [
            {
                "day_label": "lunes",
                "meal_name": "desayuno",
                "food_item": "avena",
                "quantity_grams": 60,
            }
        ],
    }
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(expected)
    fake_response = MagicMock()
    fake_response.content = [text_block]

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    result = extract_diet(fake_client, fake_pdf)
    assert result == expected


def test_save_diet_inserts_version_and_meals():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_meals WHERE diet_version_id IN "
                "(SELECT id FROM diet_versions WHERE source_pdf_filename = 'test_dieta.pdf')"
            )
            cur.execute(
                "DELETE FROM diet_versions WHERE source_pdf_filename = 'test_dieta.pdf'"
            )

    data = {
        "valid_from": "2026-01-01",
        "valid_to": "2026-02-01",
        "meals": [
            {
                "day_label": "lunes",
                "meal_name": "desayuno",
                "food_item": "avena",
                "quantity_grams": 60,
            }
        ],
    }

    diet_version_id = save_diet("test_dieta.pdf", data)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM diet_meals WHERE diet_version_id = %s",
                (diet_version_id,),
            )
            count = cur.fetchone()[0]
    assert count == 1
