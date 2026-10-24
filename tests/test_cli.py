import json

import pytest

from app.models import ChatContext
from app.services.cli import CliOrganizer


PLAN = {
    "folders": [{"title": "Trabajo", "reason": "Tema"}],
    "assignments": [
        {"chat_key": "1", "folder_title": "Trabajo", "confidence": 0.9, "reason": "Contexto"}
    ],
}


@pytest.mark.parametrize("engine", ["agy", "codex", "opencode"])
async def test_cli_adapters_pass_chat_data_without_putting_it_in_arguments(
    monkeypatch, engine
):
    captured = {}

    class Process:
        returncode = 0

        async def communicate(self, input_data):
            captured["input"] = input_data.decode()
            if engine == "agy":
                output = json.dumps({"event": "result", "result": {
                    "status": "SUCCESS", "structured_output": PLAN
                }})
            elif engine == "opencode":
                output = json.dumps({"type": "text", "part": {"text": json.dumps(PLAN)}})
                captured["attached"] = open(captured["args"][captured["args"].index("--file") + 1]).read()
            else:
                output = json.dumps(PLAN)
            return output.encode(), b""

    async def launch(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return Process()

    monkeypatch.setattr("app.services.cli.asyncio.create_subprocess_exec", launch)
    monkeypatch.setenv("TELEGRAM_API_HASH", "private-test-value")
    organizer = CliOrganizer(engine)
    result = await organizer._organize_batch(
        [ChatContext(key="1", title="Nombre de prueba", kind="grupo")], [], []
    )
    assert result.folders[0].title == "Trabajo"
    assert "Nombre de prueba" not in " ".join(captured["args"])
    assert "TELEGRAM_API_HASH" not in captured["env"]
    assert "Nombre de prueba" in (captured["attached"] if engine == "opencode" else captured["input"])
    if engine == "opencode":
        assert json.loads(captured["env"]["OPENCODE_CONFIG_CONTENT"])["permission"] == "deny"
