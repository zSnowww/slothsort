import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient, functions, types, utils
from telethon.errors import FloodWaitError, RPCError

from app.models import AnalysisMode, ChatContext, FolderChoice


@dataclass
class TelegramSnapshot:
    chats: list[ChatContext]
    peers: dict[str, Any]


@dataclass
class CreatedFolder:
    id: int
    title: str
    snapshot: dict[str, Any]


class TelegramService:
    def __init__(self) -> None:
        api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        self.api_id = int(api_id) if api_id.isdigit() else None
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        self.session_path = Path(os.getenv("TELEGRAM_SESSION", ".data/slothsort"))
        self._client: TelegramClient | None = None
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return self.api_id is not None and bool(self.api_hash)

    async def client(self) -> TelegramClient:
        if not self.configured:
            raise RuntimeError("Faltan TELEGRAM_API_ID y TELEGRAM_API_HASH en .env.")
        async with self._lock:
            if self._client is None:
                self.session_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._client = TelegramClient(
                    str(self.session_path), self.api_id, self.api_hash, flood_sleep_threshold=30
                )
            if not self._client.is_connected():
                await self._client.connect()
        return self._client

    async def is_authorized(self) -> bool:
        if not self.configured:
            return False
        return await (await self.client()).is_user_authorized()

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected():
            await self._client.disconnect()

    async def list_chats(
        self, limit: int, mode: AnalysisMode, message_limit: int = 10
    ) -> TelegramSnapshot:
        client = await self.client()
        if not await client.is_user_authorized():
            raise RuntimeError("La sesión de Telegram no está autorizada. Ejecuta scripts/login.py.")

        chats: list[ChatContext] = []
        peers: dict[str, Any] = {}
        async for dialog in client.iter_dialogs(limit=limit):
            entity = dialog.entity
            key = str(utils.get_peer_id(entity))
            if isinstance(entity, types.User):
                kind = "bot" if entity.bot else "privado"
            elif isinstance(entity, types.Channel):
                kind = "canal" if entity.broadcast else "grupo"
            else:
                kind = "grupo"
            description = None
            if mode != "metadata" and isinstance(entity, (types.Channel, types.Chat)):
                try:
                    if isinstance(entity, types.Channel):
                        full = await client(functions.channels.GetFullChannelRequest(entity))
                    else:
                        full = await client(functions.messages.GetFullChatRequest(entity.id))
                    description = (getattr(full.full_chat, "about", None) or "")[:500] or None
                except FloodWaitError:
                    raise
                except RPCError:
                    pass

            recent_messages: list[str] = []
            sample_public = mode == "messages_public" and kind in {"grupo", "canal"}
            sample_all = mode == "messages_all"
            if sample_public or sample_all:
                try:
                    messages = await client.get_messages(entity, limit=message_limit)
                    recent_messages = [
                        text[:300]
                        for message in messages
                        if (text := (message.raw_text or "").strip())
                    ]
                except FloodWaitError:
                    raise
                except RPCError:
                    pass

            chats.append(
                ChatContext(
                    key=key,
                    title=dialog.name or "Sin nombre",
                    kind=kind,
                    username=getattr(entity, "username", None),
                    unread_count=max(0, dialog.unread_count or 0),
                    archived=dialog.folder_id == 1,
                    description=description,
                    recent_messages=recent_messages,
                )
            )
            peers[key] = await client.get_input_entity(entity)
        return TelegramSnapshot(chats=chats, peers=peers)

    async def existing_folders(self) -> tuple[list[int], list[str]]:
        filters = await self._dialog_filters()
        ids: list[int] = []
        titles: list[str] = []
        for item in filters:
            if isinstance(item, (types.DialogFilter, types.DialogFilterChatlist)):
                ids.append(item.id)
                title = item.title.text if hasattr(item.title, "text") else str(item.title)
                titles.append(title)
        return ids, titles

    async def _dialog_filters(self) -> list[Any]:
        result = await (await self.client())(functions.messages.GetDialogFiltersRequest())
        return result.filters if hasattr(result, "filters") else result

    async def create_folders(
        self,
        choices: list[FolderChoice],
        peers: dict[str, Any],
    ) -> tuple[list[str], list[str], list[CreatedFolder]]:
        client = await self.client()
        used_ids, existing_titles = await self.existing_folders()
        created: list[str] = []
        undoable: list[CreatedFolder] = []
        skipped: list[str] = []

        for choice in choices:
            title = choice.title
            if title.casefold() in {value.casefold() for value in existing_titles + created}:
                skipped.append(f"La carpeta ya existe: {title}")
                continue
            include_peers = [peers[key] for key in choice.chat_keys if key in peers]
            if not include_peers:
                skipped.append(f"La carpeta {title} no contiene chats disponibles.")
                continue
            folder_id = next((value for value in range(2, 256) if value not in used_ids), None)
            if folder_id is None:
                skipped.append("No quedan identificadores de carpeta disponibles.")
                break
            dialog_filter = types.DialogFilter(
                id=folder_id,
                title=types.TextWithEntities(text=title, entities=[]),
                pinned_peers=[],
                include_peers=include_peers,
                exclude_peers=[],
            )
            try:
                result = await client(
                    functions.messages.UpdateDialogFilterRequest(id=folder_id, filter=dialog_filter)
                )
            except FloodWaitError:
                skipped.append("Telegram pidió esperar antes de crear más carpetas.")
                break
            except RPCError as exc:
                skipped.append(f"Telegram rechazó la carpeta {title}: {exc}")
                continue
            if not result:
                skipped.append(f"Telegram rechazó la carpeta: {title}")
                continue
            used_ids.append(folder_id)
            created.append(title)
            undoable.append(CreatedFolder(id=folder_id, title=title, snapshot=dialog_filter.to_dict()))

        if undoable:
            try:
                current = {item.id: item for item in await self._dialog_filters() if hasattr(item, "id")}
                for record in undoable:
                    if record.id in current:
                        record.snapshot = current[record.id].to_dict()
            except (RPCError, OSError):
                skipped.append("No se pudo verificar el estado final de las carpetas para deshacer.")
        return created, skipped, undoable

    async def undo_created_folders(
        self, folders: list[CreatedFolder]
    ) -> tuple[list[str], list[str]]:
        client = await self.client()
        current = {item.id: item for item in await self._dialog_filters() if hasattr(item, "id")}
        deleted: list[str] = []
        skipped: list[str] = []
        for folder in reversed(folders):
            item = current.get(folder.id)
            if item is None:
                skipped.append(f"La carpeta {folder.title} ya no existe.")
            elif item.to_dict() != folder.snapshot:
                skipped.append(f"La carpeta {folder.title} cambió en Telegram; no se borró.")
            else:
                result = await client(
                    functions.messages.UpdateDialogFilterRequest(id=folder.id, filter=None)
                )
                if result:
                    deleted.append(folder.title)
                else:
                    skipped.append(f"Telegram no confirmó el borrado de {folder.title}.")
        return deleted, skipped
