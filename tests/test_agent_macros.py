import json

from claude_agent_sdk import ResultMessage

from app.agent_macros import compute_agent_macro_target


def test_compute_agent_macro_target_parses_structured_output(monkeypatch):
    expected = {
        "kcal": 2400,
        "protein_g": 180,
        "carbs_g": 250,
        "fat_g": 67,
        "explanation": "Mantenimiento basado en tu TDEE real reciente.",
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

    monkeypatch.setattr("app.agent_macros.query", fake_query)

    result = compute_agent_macro_target(
        {
            "profile": {"age": 23, "sex": "M", "height_cm": 178, "activity_level": "moderado"},
            "goal": "maintenance",
            "real_tdee": 2500,
            "weight_history": [{"date": "2026-01-01", "weight_kg": 80.0, "body_fat_pct": 20.0}],
        }
    )
    assert result == expected
