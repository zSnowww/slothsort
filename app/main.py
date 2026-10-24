import os
import math
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from telethon.errors import RPCError

from app.models import (
    ApplyRequest,
    ApplyResponse,
    ChatContext,
    ChatDecision,
    ChatSummary,
    FolderChoice,
    FolderSuggestion,
    PlanRequest,
    PlanResponse,
    UndoRequest,
    UndoResponse,
)
from app.services.ollama import OllamaOrganizer
from app.services.cli import CliOrganizer, LABELS
from app.services.telegram import CreatedFolder, TelegramService


BASE_DIR = Path(__file__).parent


@dataclass
class StoredPlan:
    folders: list[FolderSuggestion]
    decisions: list[ChatDecision]
    peers: dict[str, Any]


@dataclass
class UndoRecord:
    id: str
    folders: list[CreatedFolder]


@dataclass
class PlanJob:
    status: Literal["running", "completed", "failed"] = "running"
    stage: str = "Preparando el análisis…"
    result: PlanResponse | None = None
    error: str | None = None


def normalize_plan(
    raw: dict[str, object], chats: list[ChatContext], existing: list[str]
) -> tuple[list[FolderSuggestion], list[ChatDecision]]:
    chat_by_key = {chat.key: chat for chat in chats}
    existing_folded = {title.casefold() for title in existing}
    folder_by_title: dict[str, int] = {}
    folders: list[FolderSuggestion] = []
    for item in raw.get("folders", []):
        if not isinstance(item, dict):
            continue
        title = " ".join(str(item.get("title", "")).split())[:12]
        if not title or title.casefold() in existing_folded | folder_by_title.keys():
            continue
        folder_by_title[title.casefold()] = len(folders)
        folders.append(FolderSuggestion(title=title, reason=str(item.get("reason", ""))[:220]))

    assignments: dict[str, dict] = {}
    for item in raw.get("assignments", []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("chat_key", ""))
        if key not in chat_by_key or key in assignments:
            continue
        assignments[key] = item

    decisions: list[ChatDecision] = []
    for chat in chats:
        item = assignments.get(chat.key, {})
        folder_title = item.get("folder_title")
        folder_index = folder_by_title.get(str(folder_title).casefold()) if folder_title else None
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        if not math.isfinite(confidence):
            confidence = 0
        confidence = max(0.0, min(1.0, confidence))
        if folder_index is None or confidence < 0.5:
            folder_index = None
            status = "unclassified"
        elif confidence < 0.8:
            status = "review"
        else:
            status = "suggested"
        decisions.append(
            ChatDecision(
                chat=ChatSummary.model_validate(chat.model_dump()),
                proposed_folder=folder_index,
                confidence=confidence,
                reason=str(item.get("reason", "Sin evidencia suficiente."))[:220],
                review_status=status,
            )
        )
    return folders, decisions


def create_app(
    organizer: OllamaOrganizer | None = None, telegram: TelegramService | None = None
) -> FastAPI:
    load_dotenv(BASE_DIR.parent / ".env", override=False)
    telegram_service = telegram or TelegramService()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await telegram_service.disconnect()

    app = FastAPI(title="SlothSort for Telegram", version="0.2.0", lifespan=lifespan)
    app.state.organizer = organizer or OllamaOrganizer(
        os.getenv("SLOTHSORT_OLLAMA_URL", "http://127.0.0.1:11434"),
        os.getenv("SLOTHSORT_MODEL", "gemma3:4b"),
    )
    app.state.organizers = {"ollama": app.state.organizer}
    app.state.organizers.update({engine: CliOrganizer(engine) for engine in LABELS})
    app.state.telegram = telegram_service
    app.state.plans: dict[str, StoredPlan] = {}
    app.state.last_change: UndoRecord | None = None
    app.state.mutation_lock = asyncio.Lock()
    app.state.plan_jobs: dict[str, PlanJob] = {}
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(BASE_DIR / "static" / "index.html")

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        try:
            authorized = await app.state.telegram.is_authorized()
        except (OSError, RPCError):
            authorized = False
        engines = [
            {"id": key, "label": value.model, "available": await value.is_available(),
             "remote": key != "ollama"}
            for key, value in app.state.organizers.items()
        ]
        return {
            "ok": True,
            "demo_mode": bool(getattr(app.state.telegram, "demo_mode", False)),
            "model": app.state.organizer.model,
            "max_chats": int(os.getenv("SLOTHSORT_MAX_CHATS", "200")),
            "ollama_ready": await app.state.organizer.is_available(),
            "engines": engines,
            "telegram_configured": app.state.telegram.configured,
            "telegram_authorized": authorized,
            "undo_id": app.state.last_change.id if app.state.last_change else None,
        }

    async def build_plan(
        request: PlanRequest, progress: Callable[[str], None] | None = None
    ) -> PlanResponse:
        report = progress or (lambda _: None)
        if request.engine != "ollama" and not request.remote_consent:
            raise HTTPException(
                status_code=400,
                detail="Confirma el envío de los datos al motor CLI seleccionado antes de analizar.",
            )
        selected_organizer = app.state.organizers[request.engine]
        if not await selected_organizer.is_available():
            raise HTTPException(status_code=503, detail=f"{selected_organizer.model} no está disponible.")
        try:
            limit = int(os.getenv("SLOTHSORT_MAX_CHATS", "200"))
            report("Leyendo chats de Telegram…")
            snapshot = await app.state.telegram.list_chats(
                limit, request.mode, request.message_limit
            )
            report("Comprobando carpetas existentes…")
            _, existing = await app.state.telegram.existing_folders()
            if not snapshot.chats:
                raise ValueError("No se encontraron chats para organizar.")
            report(f"Clasificando {len(snapshot.chats)} chats con {selected_organizer.model}…")
            raw = await selected_organizer.organize_chats(snapshot.chats, existing)
            report("Preparando la revisión chat por chat…")
            folders, decisions = normalize_plan(raw, snapshot.chats, existing)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="No se pudo consultar Ollama.") from exc
        except RPCError as exc:
            raise HTTPException(status_code=502, detail=f"Telegram respondió con un error: {exc}") from exc

        plan_id = uuid4().hex
        app.state.plans[plan_id] = StoredPlan(folders=folders, decisions=decisions, peers=snapshot.peers)
        return PlanResponse(
            plan_id=plan_id,
            analyzed_chats=len(snapshot.chats),
            existing_folders=existing,
            folders=folders,
            decisions=decisions,
        )

    @app.post("/api/plan", response_model=PlanResponse)
    async def create_plan(request: PlanRequest) -> PlanResponse:
        return await build_plan(request)

    @app.post("/api/plan-jobs")
    async def start_plan_job(request: PlanRequest) -> dict[str, str]:
        if any(job.status == "running" for job in app.state.plan_jobs.values()):
            raise HTTPException(status_code=409, detail="Ya hay un análisis en curso.")
        completed_ids = [
            key for key, job in app.state.plan_jobs.items() if job.status != "running"
        ]
        for key in completed_ids[:-10]:
            app.state.plan_jobs.pop(key, None)
        job_id = uuid4().hex
        job = PlanJob()
        app.state.plan_jobs[job_id] = job

        async def run() -> None:
            try:
                job.result = await build_plan(request, lambda stage: setattr(job, "stage", stage))
                job.status = "completed"
                job.stage = "Propuesta lista para revisar."
            except HTTPException as exc:
                job.status = "failed"
                job.error = str(exc.detail)
            except Exception:
                job.status = "failed"
                job.error = "El análisis falló inesperadamente. Consulta el servidor."

        asyncio.create_task(run())
        return {"job_id": job_id}

    @app.get("/api/plan-jobs/{job_id}")
    async def plan_job_status(job_id: str) -> dict[str, object]:
        job = app.state.plan_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="El análisis ya no está disponible.")
        return {
            "status": job.status,
            "stage": job.stage,
            "result": job.result.model_dump() if job.result else None,
            "error": job.error,
        }

    @app.post("/api/plans/{plan_id}/apply", response_model=ApplyResponse)
    async def apply_plan(plan_id: str, request: ApplyRequest) -> ApplyResponse:
        plan = app.state.plans.get(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="El plan ya no existe.")
        seen_folders: set[int] = set()
        seen_chats: set[str] = set()
        choices: list[FolderChoice] = []
        for choice in request.folders:
            if choice.index < 0 or choice.index >= len(plan.folders) or choice.index in seen_folders:
                raise HTTPException(status_code=400, detail="Carpeta seleccionada inválida o duplicada.")
            title = " ".join(choice.title.split())
            if not title or len(title) > 12:
                raise HTTPException(status_code=400, detail="El nombre de carpeta debe tener entre 1 y 12 caracteres.")
            if not choice.chat_keys:
                continue
            if len(set(choice.chat_keys)) != len(choice.chat_keys) or any(
                key not in plan.peers or key in seen_chats for key in choice.chat_keys
            ):
                raise HTTPException(status_code=400, detail="La selección contiene chats inválidos o duplicados.")
            seen_folders.add(choice.index)
            seen_chats.update(choice.chat_keys)
            choices.append(FolderChoice(index=choice.index, title=title, chat_keys=choice.chat_keys))
        if len({choice.title.casefold() for choice in choices}) != len(choices):
            raise HTTPException(status_code=400, detail="Hay nombres de carpeta duplicados.")
        try:
            async with app.state.mutation_lock:
                created, skipped, undoable = await app.state.telegram.create_folders(choices, plan.peers)
                undo_id = uuid4().hex if undoable else None
                if undo_id:
                    app.state.last_change = UndoRecord(id=undo_id, folders=undoable)
        except RPCError as exc:
            raise HTTPException(status_code=502, detail=f"Telegram respondió con un error: {exc}") from exc
        app.state.plans.pop(plan_id, None)
        return ApplyResponse(created=created, skipped=skipped, undo_id=undo_id)

    @app.post("/api/undo", response_model=UndoResponse)
    async def undo_last_change(request: UndoRequest) -> UndoResponse:
        async with app.state.mutation_lock:
            record = app.state.last_change
            if record is None or record.id != request.undo_id:
                raise HTTPException(status_code=404, detail="No hay un cambio reciente que se pueda revertir.")
            try:
                deleted, skipped = await app.state.telegram.undo_created_folders(record.folders)
            except RPCError as exc:
                raise HTTPException(status_code=502, detail=f"Telegram respondió con un error: {exc}") from exc
            app.state.last_change = None
        return UndoResponse(deleted=deleted, skipped=skipped)

    return app


app = create_app()
