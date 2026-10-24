from app.main import create_app
from app.models import FolderChoice
from scripts.demo import DemoTelegram, SAMPLE_CHATS


async def test_demo_uses_synthetic_chats_and_never_needs_telegram_credentials():
    telegram = DemoTelegram()
    assert telegram.configured is True
    assert telegram.demo_mode is True
    snapshot = await telegram.list_chats(2, "messages_public", 5)
    assert [chat.key for chat in snapshot.chats] == [chat.key for chat in SAMPLE_CHATS[:2]]
    assert snapshot.chats[0].recent_messages == SAMPLE_CHATS[0].recent_messages
    assert snapshot.peers == {chat.key: chat.key for chat in SAMPLE_CHATS[:2]}


async def test_demo_folder_create_and_undo_stays_in_memory():
    telegram = DemoTelegram()
    choice = FolderChoice(index=0, title="Código", chat_keys=["demo-python"])
    created, skipped, undoable = await telegram.create_folders([choice], {})
    assert created == ["Código"]
    assert skipped == []
    assert (await telegram.existing_folders())[1] == ["Código"]
    deleted, skipped = await telegram.undo_created_folders(undoable)
    assert deleted == ["Código"]
    assert skipped == []
    assert (await telegram.existing_folders())[1] == []


def test_demo_app_marks_itself_as_demo():
    app = create_app(telegram=DemoTelegram())
    assert app.state.telegram.demo_mode is True
