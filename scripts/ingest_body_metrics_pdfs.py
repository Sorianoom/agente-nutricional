import base64
import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs" / "analiticas"

BODY_METRICS_SCHEMA = {
    "type": "object",
    "properties": {
        "measured_on": {"type": "string", "format": "date"},
        "weight_kg": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "body_fat_pct": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "muscle_mass_kg": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": ["measured_on", "weight_kg", "body_fat_pct", "muscle_mass_kg"],
    "additionalProperties": False,
}


def extract_body_metrics(client: anthropic.Anthropic, pdf_path: Path) -> dict:
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extrae de este analisis corporal la fecha de "
                            "la medicion, el peso en kg, el porcentaje de "
                            "grasa corporal y la masa muscular en kg. Si "
                            "un dato no aparece, usa null."
                        ),
                    },
                ],
            }
        ],
        output_config={
            "format": {"type": "json_schema", "schema": BODY_METRICS_SCHEMA}
        },
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def save_body_metrics(pdf_filename: str, data: dict) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO body_metrics
                    (source_pdf_filename, measured_on, weight_kg, body_fat_pct, muscle_mass_kg)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    pdf_filename,
                    data["measured_on"],
                    data["weight_kg"],
                    data["body_fat_pct"],
                    data["muscle_mass_kg"],
                ),
            )
            body_metrics_id = cur.fetchone()[0]
    return body_metrics_id


if __name__ == "__main__":
    client = anthropic.Anthropic()
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            metrics_data = extract_body_metrics(client, pdf_path)
            metrics_id = save_body_metrics(pdf_path.name, metrics_data)
            print(f"{pdf_path.name}: body_metrics {metrics_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR procesando {pdf_path.name}: {exc}")
