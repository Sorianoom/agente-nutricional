import json
import tempfile
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

AGENT_CWD = Path(tempfile.gettempdir()) / "agentenutricional_macro_agent"

MACRO_SCHEMA = {
    "type": "object",
    "properties": {
        "kcal": {"type": "number"},
        "protein_g": {"type": "number"},
        "carbs_g": {"type": "number"},
        "fat_g": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["kcal", "protein_g", "carbs_g", "fat_g", "explanation"],
    "additionalProperties": False,
}


def compute_agent_macro_target(summary: dict) -> dict:
    AGENT_CWD.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        system_prompt=(
            "Eres un asistente de nutricion. Con el resumen de perfil e "
            "historico que te doy, recomienda kcal y macros (proteina, "
            "carbohidratos, grasa en gramos) objetivo para el objetivo "
            "indicado, con una explicacion breve."
        ),
        max_turns=3,
        cwd=str(AGENT_CWD),
        setting_sources=[],
        allowed_tools=[],
        output_format={"type": "json_schema", "schema": MACRO_SCHEMA},
    )
    prompt = (
        "Resumen del usuario (JSON):\n"
        f"{json.dumps(summary, ensure_ascii=False)}\n\n"
        "Recomienda kcal y macros objetivo."
    )

    async def _run() -> dict:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.is_error or message.structured_output is None:
                    raise RuntimeError(f"Recomendacion IA fallida: {message.result}")
                return message.structured_output
        raise RuntimeError("Sin respuesta del agente")

    return anyio.run(_run)
