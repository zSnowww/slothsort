import asyncio
from typing import Any

import httpx

from app.main import create_app, normalize_plan
from app.models import ChatContext
from app.services.telegram import CreatedFolder, TelegramSnapshot


CHATS = [
    ChatContext(key="1", title="Ana", kind="privado", recent_messages=["mensaje privado"]),
    ChatContext(key="2", title="Equipo Hackathon", kind="grupo", description="Proyecto de código"),
    ChatContext(key="3", title="Noticias", kind="canal"),
]


class FakeOrganizer:
    model = "fake-open-model"

    async def is_available(self) -> bool:
        return True

    async def organize_chats(self, chats, existing_folders):
        assert existing_folders == ["Trabajo"]
        return {
            "folders": [
                {"title": "Personal", "reason": "Contactos cercanos"},
                {"title": "Proyectos", "reason": "Actividades del equipo"},
            ],
            "assignments": [
                {"chat_key": "1", "folder_title": "Personal", "confidence": 0.66, "reason": "Nombre ambiguo"},
                {"chat_key": "2", "folder_title": "Proyectos", "confidence": 0.92, "reason": "Descripción clara"},
                {"chat_key": "3", "folder_title": "Proyectos", "confidence": 0.2, "reason": "Sin contexto"},
            ],
        }


class FakeTelegram:
    configured = True

    def __init__(self) -> None:
        self.mode = None
        self.message_limit = None
        self.applied = None
        self.undone = None

    async def is_authorized(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def list_chats(self, limit: int, mode: str, message_limit: int) -> TelegramSnapshot:
        self.mode = mode
        self.message_limit = message_limit
        selected = CHATS[:limit]
        return TelegramSnapshot(chats=selected, peers={chat.key: object() for chat in selected})

    async def existing_folders(self) -> tuple[list[int], list[str]]:
        return [2], ["Trabajo"]

    async def create_folders(self, choices, peers: dict[str, Any]):
        self.applied = choices
        return (
            [choice.title for choice in choices],
            [],
            [CreatedFolder(id=10 + index, title=choice.title, snapshot={"title": choice.title})
             for index, choice in enumerate(choices)],
        )

    async def undo_created_folders(self, folders):
        self.undone = folders
        return [folder.title for folder in folders], []


def make_client(telegram: FakeTelegram | None = None) -> httpx.AsyncClient:
    app = create_app(FakeOrganizer(), telegram or FakeTelegram())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_status_reports_both_integrations_ready():
    async with make_client() as client:
        response = await client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["telegram_authorized"] is True
    assert response.json()["ollama_ready"] is True


async def test_plan_exposes_uncertainty_without_exposing_messages():
    telegram = FakeTelegram()
    async with make_client(telegram) as client:
        response = await client.post(
            "/api/plan", json={"mode": "messages_all", "message_limit": 20}
        )
    assert response.status_code == 200
    plan = response.json()
    assert telegram.mode == "messages_all"
    assert telegram.message_limit == 20
    assert plan["existing_folders"] == ["Trabajo"]
    assert [item["review_status"] for item in plan["decisions"]] == [
        "review", "suggested", "unclassified"
    ]
    assert plan["decisions"][2]["proposed_folder"] is None
    assert "mensaje privado" not in response.text
    assert "Proyecto de código" not in response.text


async def test_plan_job_reports_stage_and_result():
    async with make_client() as client:
        started = await client.post("/api/plan-jobs", json={"mode": "messages_all"})
        assert started.status_code == 200
        for _ in range(10):
            await asyncio.sleep(0)
            progress = (await client.get(f"/api/plan-jobs/{started.json()['job_id']}")).json()
            if progress["status"] == "completed":
                break
    assert progress["status"] == "completed"
    assert progress["result"]["analyzed_chats"] == 3
    assert "mensaje privado" not in str(progress)


async def test_plan_rejects_unsupported_message_limit_before_reading_telegram():
    telegram = FakeTelegram()
    async with make_client(telegram) as client:
        response = await client.post(
            "/api/plan", json={"mode": "messages_all", "message_limit": 1000}
        )
    assert response.status_code == 422
    assert telegram.mode is None


async def test_cli_engine_requires_explicit_remote_consent_before_reading_chats():
    telegram = FakeTelegram()
    async with make_client(telegram) as client:
        response = await client.post(
            "/api/plan", json={"mode": "messages_all", "engine": "agy"}
        )
    assert response.status_code == 400
    assert telegram.mode is None


async def test_apply_accepts_manual_move_and_consumes_plan():
    telegram = FakeTelegram()
    async with make_client(telegram) as client:
        plan = (await client.post("/api/plan", json={"mode": "descriptions"})).json()
        payload = {"folders": [{"index": 1, "title": "Código", "chat_keys": ["1", "2"]}]}
        first = await client.post(f"/api/plans/{plan['plan_id']}/apply", json=payload)
        second = await client.post(f"/api/plans/{plan['plan_id']}/apply", json=payload)
    assert first.json()["created"] == ["Código"]
    assert telegram.applied[0].chat_keys == ["1", "2"]
    assert second.status_code == 404


async def test_undo_only_accepts_the_latest_change_token():
    telegram = FakeTelegram()
    async with make_client(telegram) as client:
        plan = (await client.post("/api/plan", json={"mode": "descriptions"})).json()
        applied = await client.post(
            f"/api/plans/{plan['plan_id']}/apply",
            json={"folders": [{"index": 1, "title": "Código", "chat_keys": ["2"]}]},
        )
        undo_id = applied.json()["undo_id"]
        invalid = await client.post("/api/undo", json={"undo_id": "wrong"})
        status = await client.get("/api/status")
        undone = await client.post("/api/undo", json={"undo_id": undo_id})
        again = await client.post("/api/undo", json={"undo_id": undo_id})
    assert invalid.status_code == 404
    assert status.json()["undo_id"] == undo_id
    assert undone.json()["deleted"] == ["Código"]
    assert telegram.undone[0].title == "Código"
    assert again.status_code == 404


async def test_apply_rejects_duplicate_chat_before_any_telegram_write():
    telegram = FakeTelegram()
    async with make_client(telegram) as client:
        plan = (await client.post("/api/plan", json={"mode": "metadata"})).json()
        response = await client.post(
            f"/api/plans/{plan['plan_id']}/apply",
            json={"folders": [
                {"index": 0, "title": "Personal", "chat_keys": ["1"]},
                {"index": 1, "title": "Proyectos", "chat_keys": ["1"]},
            ]},
        )
    assert response.status_code == 400
    assert telegram.applied is None


def test_normalization_rejects_unknowns_and_weak_assignments():
    raw = {
        "folders": [
            {"title": "Trabajo", "reason": "Duplicada"},
            {"title": "Personal", "reason": "Contactos"},
        ],
        "assignments": [
            {"chat_key": "1", "folder_title": "Personal", "confidence": 0.4},
            {"chat_key": "2", "folder_title": "Personal", "confidence": 0.85},
            {"chat_key": "999", "folder_title": "Personal", "confidence": 1},
        ],
    }
    folders, decisions = normalize_plan(raw, CHATS, ["Trabajo"])
    assert [folder.title for folder in folders] == ["Personal"]
    assert [decision.review_status for decision in decisions] == [
        "unclassified", "suggested", "unclassified"
    ]
