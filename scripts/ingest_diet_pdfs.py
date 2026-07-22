import sys
import tempfile
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs" / "dietas"

# cwd fuera del proyecto: evita heredar hooks/skills de Claude Code de este
# repo, que si no multiplican por ~9x los tokens de cada llamada.
AGENT_CWD = Path(tempfile.gettempdir()) / "agentenutricional_pdf_extraction"

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


def extract_diet(pdf_path: Path) -> dict:
    AGENT_CWD.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=(
            "Eres un extractor de datos. Lee el PDF en la ruta indicada con "
            "la herramienta Read y devuelve solo los datos pedidos segun el "
            "schema."
        ),
        max_turns=5,
        cwd=str(AGENT_CWD),
        setting_sources=[],
        allowed_tools=["Read"],
        output_format={"type": "json_schema", "schema": DIET_SCHEMA},
    )
    prompt = (
        f"Lee el PDF en '{pdf_path}' y extrae todas las comidas con su "
        "cantidad en gramos, agrupadas por dia, y el rango de fechas de "
        "validez de la dieta. Si no se indica fecha de fin, deja valid_to "
        "como null."
    )

    async def _run() -> dict:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.is_error or message.structured_output is None:
                    raise RuntimeError(
                        f"Extraccion fallida para {pdf_path}: {message.result}"
                    )
                return message.structured_output
        raise RuntimeError(f"Sin respuesta del agente para {pdf_path}")

    return anyio.run(_run)


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
            cur.executemany(
                """
                INSERT INTO diet_meals
                    (diet_version_id, day_label, meal_name, food_item, quantity_grams)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        diet_version_id,
                        meal["day_label"],
                        meal["meal_name"],
                        meal["food_item"],
                        meal["quantity_grams"],
                    )
                    for meal in data["meals"]
                ],
            )
    return diet_version_id


if __name__ == "__main__":
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            diet_data = extract_diet(pdf_path)
            version_id = save_diet(pdf_path.name, diet_data)
            print(
                f"{pdf_path.name}: version {version_id}, "
                f"{len(diet_data['meals'])} comidas"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR procesando {pdf_path.name}: {exc}")
