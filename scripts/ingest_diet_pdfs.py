import base64
import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs" / "dietas"

DIET_SCHEMA = {
    "type": "object",
    "properties": {
        "valid_from": {"type": "string", "format": "date"},
        "valid_to": {
            "anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]
        },
        "meals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day_label": {"type": "string"},
                    "meal_name": {"type": "string"},
                    "food_item": {"type": "string"},
                    "quantity_grams": {"type": "number"},
                },
                "required": [
                    "day_label",
                    "meal_name",
                    "food_item",
                    "quantity_grams",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["valid_from", "valid_to", "meals"],
    "additionalProperties": False,
}


def extract_diet(client: anthropic.Anthropic, pdf_path: Path) -> dict:
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8000,
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
                            "Extrae de este PDF de dieta todas las comidas "
                            "con su cantidad en gramos, agrupadas por dia, "
                            "y el rango de fechas de validez de la dieta. "
                            "Si no se indica fecha de fin, deja valid_to "
                            "como null."
                        ),
                    },
                ],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": DIET_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def save_diet(pdf_filename: str, data: dict) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO diet_versions (source_pdf_filename, valid_from, valid_to)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (pdf_filename, data["valid_from"], data["valid_to"]),
            )
            diet_version_id = cur.fetchone()[0]
            for meal in data["meals"]:
                cur.execute(
                    """
                    INSERT INTO diet_meals
                        (diet_version_id, day_label, meal_name, food_item, quantity_grams)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        diet_version_id,
                        meal["day_label"],
                        meal["meal_name"],
                        meal["food_item"],
                        meal["quantity_grams"],
                    ),
                )
    return diet_version_id


if __name__ == "__main__":
    client = anthropic.Anthropic()
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            diet_data = extract_diet(client, pdf_path)
            version_id = save_diet(pdf_path.name, diet_data)
            print(
                f"{pdf_path.name}: version {version_id}, "
                f"{len(diet_data['meals'])} comidas"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR procesando {pdf_path.name}: {exc}")
