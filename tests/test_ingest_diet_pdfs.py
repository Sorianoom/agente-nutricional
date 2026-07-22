import json

from claude_agent_sdk import ResultMessage

from app.db import get_connection
from scripts.ingest_diet_pdfs import extract_diet, save_diet


def test_extract_diet_parses_structured_output(tmp_path, monkeypatch):
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
    fake_result = ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=90,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        structured_output=expected,
        result=json.dumps(expected),
    )

    async def fake_query(prompt, options):
        yield fake_result

    monkeypatch.setattr("scripts.ingest_diet_pdfs.query", fake_query)

    result = extract_diet(fake_pdf)
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
