from app.models import ChatContext
from app.services.ollama import ModelAssignment, ModelFolder, ModelPlan, OllamaOrganizer


class FakeBatchOrganizer(OllamaOrganizer):
    def __init__(self):
        super().__init__("http://127.0.0.1:11434", "fake")
        self.batch_sizes = []
        self.available = []

    async def _organize_batch(self, chats, existing_folders, available_folders):
        self.batch_sizes.append(len(chats))
        self.available.append(list(available_folders))
        return ModelPlan(
            folders=[ModelFolder(title="Código", reason="Programación")],
            assignments=[
                ModelAssignment(
                    chat_key=chat.key,
                    folder_title="Código",
                    confidence=0.9,
                    reason="Nombre claro",
                )
                for chat in chats
            ],
        )


async def test_large_chat_list_is_batched_and_reuses_folder_titles():
    organizer = FakeBatchOrganizer()
    chats = [ChatContext(key=str(i), title=f"Código {i}", kind="grupo") for i in range(26)]
    result = await organizer.organize_chats(chats, [])
    assert organizer.batch_sizes == [25, 1]
    assert organizer.available == [[], ["Código"]]
    assert len(result["folders"]) == 1
    assert len(result["assignments"]) == 26
