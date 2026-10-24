import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from pydantic import ValidationError

from app.models import ChatContext
from app.services.ollama import ModelPlan, OllamaOrganizer, SYSTEM_PROMPT, build_batch_prompt


LABELS = {"agy": "Antigravity CLI", "codex": "Codex CLI", "opencode": "OpenCode CLI"}


def parse_model_json(value: str) -> ModelPlan:
    value = value.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return ModelPlan.model_validate_json(value)
    except (ValueError, ValidationError) as exc:
        raise RuntimeError("El motor no devolvió una propuesta JSON válida.") from exc


class CliOrganizer(OllamaOrganizer):
    def __init__(self, engine: str, timeout: float = 300.0) -> None:
        if engine not in LABELS:
            raise ValueError("Motor CLI desconocido.")
        super().__init__(base_url="", model=LABELS[engine], timeout=timeout)
        self.engine = engine

    async def is_available(self) -> bool:
        return shutil.which(self.engine) is not None

    async def _organize_batch(
        self,
        chats: list[ChatContext],
        existing_folders: list[str],
        available_folders: list[str],
    ) -> ModelPlan:
        prompt = (
            f"{SYSTEM_PROMPT}\n\nClasifica únicamente los datos proporcionados. "
            "No uses herramientas, archivos ni búsquedas. Devuelve solo JSON.\n\n"
            + build_batch_prompt(chats, existing_folders, available_folders)
        )
        with tempfile.TemporaryDirectory(prefix="slothsort-cli-") as directory:
            workdir = Path(directory)
            schema_path = workdir / "schema.json"
            schema_path.write_text(json.dumps(ModelPlan.model_json_schema()), encoding="utf-8")
            schema_path.chmod(0o600)
            env = {
                key: value for key, value in os.environ.items()
                if not key.startswith("TELEGRAM_") and not key.startswith("SLOTHSORT_")
            }
            if self.engine == "agy":
                command = [
                    "agy", "--input-format", "stream-json", "--output-format", "stream-json",
                    "--json-schema", str(schema_path), "--mode", "plan", "--sandbox",
                    "--disable-slash-commands",
                ]
                input_data = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
            elif self.engine == "codex":
                command = [
                    "codex", "exec", "--sandbox", "read-only", "--ephemeral",
                    "--ignore-user-config", "--skip-git-repo-check", "--output-schema",
                    str(schema_path), "-",
                ]
                input_data = prompt
            else:
                request_path = workdir / "request.txt"
                request_path.write_text(prompt, encoding="utf-8")
                request_path.chmod(0o600)
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps({"permission": "deny"})
                command = [
                    "opencode", "run", "--pure", "--format", "json", "--file",
                    str(request_path), "Devuelve únicamente el JSON solicitado en el archivo adjunto.",
                ]
                input_data = ""

            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=workdir,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(f"{self.model} no está instalado.") from exc
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(input_data.encode("utf-8")), timeout=self.timeout
                )
            except TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise RuntimeError(f"{self.model} agotó el tiempo de espera.") from exc
            if process.returncode != 0:
                raise RuntimeError(
                    f"{self.model} no completó el análisis. Revisa su sesión y autenticación en la terminal."
                )
            output = stdout.decode("utf-8", errors="replace")
            if self.engine == "agy":
                events = [json.loads(line) for line in output.splitlines() if line.strip()]
                results = [event["result"] for event in events if event.get("event") == "result"]
                if not results or results[-1].get("status") != "SUCCESS":
                    raise RuntimeError("Antigravity no devolvió una propuesta completa.")
                payload = results[-1].get("structured_output") or results[-1].get("response", "")
            elif self.engine == "opencode":
                events = [json.loads(line) for line in output.splitlines() if line.strip()]
                payload = "".join(
                    event.get("part", {}).get("text", "")
                    for event in events if event.get("type") == "text"
                )
            else:
                payload = output
            if isinstance(payload, dict):
                try:
                    return ModelPlan.model_validate(payload)
                except ValidationError as exc:
                    raise RuntimeError("El motor no devolvió una propuesta JSON válida.") from exc
            return parse_model_json(str(payload))
