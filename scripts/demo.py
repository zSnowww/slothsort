"""Run SlothSort with invented chats and the real local Ollama model.

This demo never connects to Telegram and never changes a real chat folder.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv

from app.main import create_app
from app.models import AnalysisMode, ChatContext, FolderChoice
from app.services.ollama import OllamaOrganizer
from app.services.telegram import CreatedFolder, TelegramSnapshot


SAMPLE_CHATS = [
    ChatContext(
        key="demo-python", title="Python Perú", kind="grupo",
        description="Comunidad para aprender Python, resolver dudas y compartir código.",
        recent_messages=["¿Cómo pruebo esta función con pytest?", "Compartí un tutorial de FastAPI."],
    ),
    ChatContext(
        key="demo-web", title="Frontend Dev", kind="canal",
        description="Noticias y recursos de desarrollo web, CSS y JavaScript.",
        recent_messages=["Nueva guía de accesibilidad web.", "Hoy comparamos React y Vue."],
    ),
    ChatContext(
        key="demo-trekking", title="Senderismo Lima", kind="grupo",
        description="Salidas de trekking y caminatas cerca de Lima.",
        recent_messages=["Ruta del sábado: Lomas de Lachay.", "Lleven agua y bloqueador."],
    ),
    ChatContext(
        key="demo-rutas", title="Rutas de Montaña", kind="canal",
        description="Rutas, mapas y consejos para excursiones de montaña.",
        recent_messages=["Nuevo mapa de senderos para principiantes.", "Consejos para botas de trekking."],
    ),
    ChatContext(
        key="demo-cocina", title="Cocina en Casa", kind="grupo",
        description="Ideas para cocinar comidas sencillas en casa.",
        recent_messages=["¿Qué preparo con garbanzos?", "Hoy hacemos pan casero."],
    ),
    ChatContext(
        key="demo-recetas", title="Recetas Fáciles", kind="canal",
        description="Recetas rápidas y consejos de cocina.",
        recent_messages=["Pasta en 20 minutos.", "Tres ideas para desayunos saludables."],
    ),
]


@dataclass
class DemoFolder:
    id: int
    title: str
    chat_keys: list[str]

    def snapshot(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "chat_keys": self.chat_keys.copy()}


class DemoTelegram:
    configured = True
    demo_mode = True

    def __init__(self) -> None:
        self.folders: dict[int, DemoFolder] = {}

    async def is_authorized(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def list_chats(
        self, limit: int, mode: AnalysisMode, message_limit: int = 10
    ) -> TelegramSnapshot:
        chats: list[ChatContext] = []
        for item in SAMPLE_CHATS[:limit]:
            chats.append(item.model_copy(update={
                "description": item.description if mode != "metadata" else None,
                "recent_messages": item.recent_messages[:message_limit]
                if mode.startswith("messages_") else [],
            }))
        return TelegramSnapshot(chats=chats, peers={chat.key: chat.key for chat in chats})

    async def existing_folders(self) -> tuple[list[int], list[str]]:
        return list(self.folders), [folder.title for folder in self.folders.values()]

    async def create_folders(
        self, choices: list[FolderChoice], peers: dict[str, Any]
    ) -> tuple[list[str], list[str], list[CreatedFolder]]:
        created: list[str] = []
        skipped: list[str] = []
        undoable: list[CreatedFolder] = []
        for choice in choices:
            if choice.title.casefold() in {folder.title.casefold() for folder in self.folders.values()}:
                skipped.append(f"La carpeta ya existe: {choice.title}")
                continue
            folder_id = next(value for value in range(2, 256) if value not in self.folders)
            folder = DemoFolder(folder_id, choice.title, choice.chat_keys)
            self.folders[folder_id] = folder
            created.append(choice.title)
            undoable.append(CreatedFolder(folder_id, choice.title, folder.snapshot()))
        return created, skipped, undoable

    async def undo_created_folders(
        self, folders: list[CreatedFolder]
    ) -> tuple[list[str], list[str]]:
        deleted: list[str] = []
        skipped: list[str] = []
        for record in reversed(folders):
            folder = self.folders.get(record.id)
            if folder and folder.snapshot() == record.snapshot:
                self.folders.pop(record.id)
                deleted.append(record.title)
            else:
                skipped.append(f"La carpeta {record.title} cambió; no se borró.")
        return deleted, skipped


def demo_app():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    os.environ["SLOTHSORT_MAX_CHATS"] = str(len(SAMPLE_CHATS))
    organizer = OllamaOrganizer(
        os.getenv("SLOTHSORT_OLLAMA_URL", "http://127.0.0.1:11434"),
        os.getenv("SLOTHSORT_MODEL", "gemma3:4b"),
    )
    return create_app(organizer=organizer, telegram=DemoTelegram())


if __name__ == "__main__":
    uvicorn.run(demo_app(), host="127.0.0.1", port=8001)
