from types import SimpleNamespace

from telethon import types

from app.services.telegram import TelegramService


class FakeClient:
    def __init__(self) -> None:
        self.user = types.User(id=1, first_name="Ana")
        self.channel = types.Channel(
            id=2, title="Python", photo=types.ChatPhotoEmpty(), date=None, broadcast=True
        )
        self.dialogs = [
            SimpleNamespace(entity=self.user, name="Ana", unread_count=0, folder_id=0),
            SimpleNamespace(entity=self.channel, name="Python", unread_count=3, folder_id=0),
        ]
        self.full_calls = []
        self.message_calls = []

    async def is_user_authorized(self):
        return True

    async def iter_dialogs(self, limit):
        for dialog in self.dialogs[:limit]:
            yield dialog

    async def get_input_entity(self, entity):
        return f"peer:{entity.id}"

    async def __call__(self, request):
        self.full_calls.append(request)
        return SimpleNamespace(full_chat=SimpleNamespace(about="Canal de tutoriales Python"))

    async def get_messages(self, entity, limit):
        self.message_calls.append((entity.id, limit))
        return [SimpleNamespace(raw_text="Un ejemplo de mensaje")]


def service_with_client(client: FakeClient) -> TelegramService:
    service = TelegramService()

    async def get_client():
        return client

    service.client = get_client
    return service


async def test_metadata_mode_reads_no_descriptions_or_messages():
    client = FakeClient()
    snapshot = await service_with_client(client).list_chats(10, "metadata")
    assert len(snapshot.chats) == 2
    assert client.full_calls == []
    assert client.message_calls == []
    assert all(chat.description is None and not chat.recent_messages for chat in snapshot.chats)


async def test_public_message_mode_skips_private_history():
    client = FakeClient()
    snapshot = await service_with_client(client).list_chats(10, "messages_public")
    assert client.message_calls == [(2, 10)]
    assert snapshot.chats[0].recent_messages == []
    assert snapshot.chats[1].description == "Canal de tutoriales Python"
    assert snapshot.chats[1].recent_messages == ["Un ejemplo de mensaje"]


async def test_all_message_mode_explicitly_reads_private_history():
    client = FakeClient()
    await service_with_client(client).list_chats(10, "messages_all", 20)
    assert client.message_calls == [(1, 20), (2, 20)]
