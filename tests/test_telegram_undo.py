from telethon import functions, types

from app.services.telegram import CreatedFolder, TelegramService


def folder(title: str) -> types.DialogFilter:
    return types.DialogFilter(
        id=9,
        title=types.TextWithEntities(text=title, entities=[]),
        pinned_peers=[],
        include_peers=[types.InputPeerUser(user_id=42, access_hash=7)],
        exclude_peers=[],
    )


class FakeClient:
    def __init__(self) -> None:
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        return True


async def test_undo_deletes_only_an_unchanged_created_folder(monkeypatch):
    service = TelegramService()
    client = FakeClient()
    original = folder("Prueba")

    async def get_client():
        return client

    async def get_filters():
        return [original]

    monkeypatch.setattr(service, "client", get_client)
    monkeypatch.setattr(service, "_dialog_filters", get_filters)
    record = CreatedFolder(id=9, title="Prueba", snapshot=original.to_dict())
    deleted, skipped = await service.undo_created_folders([record])
    assert deleted == ["Prueba"]
    assert skipped == []
    assert isinstance(client.requests[0], functions.messages.UpdateDialogFilterRequest)
    assert client.requests[0].id == 9
    assert client.requests[0].filter is None


async def test_undo_preserves_a_folder_modified_outside_the_app(monkeypatch):
    service = TelegramService()
    client = FakeClient()
    original = folder("Prueba")

    async def get_client():
        return client

    async def get_filters():
        return [folder("Cambiada")]

    monkeypatch.setattr(service, "client", get_client)
    monkeypatch.setattr(service, "_dialog_filters", get_filters)
    record = CreatedFolder(id=9, title="Prueba", snapshot=original.to_dict())
    deleted, skipped = await service.undo_created_folders([record])
    assert deleted == []
    assert "cambió" in skipped[0]
    assert client.requests == []
