import sys
import tempfile
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_connection  # noqa: E402

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs" / "analiticas"

# cwd fuera del proyecto: evita heredar hooks/skills de Claude Code de este
# repo, que si no multiplican por ~9x los tokens de cada llamada.
AGENT_CWD = Path(tempfile.gettempdir()) / "agentenutricional_pdf_extraction"

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


def extract_body_metrics(pdf_path: Path) -> dict:
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
        output_format={"type": "json_schema", "schema": BODY_METRICS_SCHEMA},
    )
    prompt = (
        f"Lee el PDF en '{pdf_path}' y extrae la fecha de la medicion, el "
        "peso en kg, el porcentaje de grasa corporal y la masa muscular en "
        "kg. Si un dato no aparece, usa null."
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
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        try:
            metrics_data = extract_body_metrics(pdf_path)
            metrics_id = save_body_metrics(pdf_path.name, metrics_data)
            print(f"{pdf_path.name}: body_metrics {metrics_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR procesando {pdf_path.name}: {exc}")
