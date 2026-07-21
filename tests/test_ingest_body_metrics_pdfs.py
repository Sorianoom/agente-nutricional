import json
from unittest.mock import MagicMock

from app.db import get_connection
from scripts.ingest_body_metrics_pdfs import extract_body_metrics, save_body_metrics


def test_extract_body_metrics_parses_json_response(tmp_path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake content")

    expected = {
        "measured_on": "2026-01-01",
        "weight_kg": 80.5,
        "body_fat_pct": 18.2,
        "muscle_mass_kg": 35.0,
    }
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(expected)
    fake_response = MagicMock()
    fake_response.content = [text_block]

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    result = extract_body_metrics(fake_client, fake_pdf)
    assert result == expected


def test_save_body_metrics_inserts_row():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM body_metrics WHERE source_pdf_filename = 'test_analitica.pdf'"
            )

    data = {
        "measured_on": "2026-01-01",
        "weight_kg": 80.5,
        "body_fat_pct": 18.2,
        "muscle_mass_kg": 35.0,
    }

    body_metrics_id = save_body_metrics("test_analitica.pdf", data)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT weight_kg FROM body_metrics WHERE id = %s", (body_metrics_id,)
            )
            row = cur.fetchone()
    assert float(row[0]) == 80.5
