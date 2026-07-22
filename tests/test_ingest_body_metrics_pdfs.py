import json

from claude_agent_sdk import ResultMessage

from app.db import get_connection
from scripts.ingest_body_metrics_pdfs import extract_body_metrics, save_body_metrics


def test_extract_body_metrics_parses_structured_output(tmp_path, monkeypatch):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake content")

    expected = {
        "measured_on": "2026-01-01",
        "weight_kg": 80.5,
        "body_fat_pct": 18.2,
        "muscle_mass_kg": 35.0,
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

    monkeypatch.setattr("scripts.ingest_body_metrics_pdfs.query", fake_query)

    result = extract_body_metrics(fake_pdf)
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
