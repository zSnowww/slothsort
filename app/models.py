from typing import Literal

from pydantic import BaseModel, Field


AnalysisMode = Literal["metadata", "descriptions", "messages_public", "messages_all"]
AnalysisEngine = Literal["ollama", "agy", "codex", "opencode"]


class PlanRequest(BaseModel):
    mode: AnalysisMode = "descriptions"
    message_limit: Literal[5, 10, 20] = 10
    engine: AnalysisEngine = "ollama"
    remote_consent: bool = False


class ChatSummary(BaseModel):
    key: str
    title: str
    kind: str
    username: str | None = None
    unread_count: int = Field(default=0, ge=0)
    archived: bool = False


class ChatContext(ChatSummary):
    description: str | None = None
    recent_messages: list[str] = Field(default_factory=list)


class FolderSuggestion(BaseModel):
    title: str
    reason: str


class ChatDecision(BaseModel):
    chat: ChatSummary
    proposed_folder: int | None
    confidence: float = Field(ge=0, le=1)
    reason: str
    review_status: Literal["suggested", "review", "unclassified"]


class PlanResponse(BaseModel):
    plan_id: str
    analyzed_chats: int
    existing_folders: list[str]
    folders: list[FolderSuggestion]
    decisions: list[ChatDecision]


class FolderChoice(BaseModel):
    index: int
    title: str
    chat_keys: list[str]


class ApplyRequest(BaseModel):
    folders: list[FolderChoice]


class ApplyResponse(BaseModel):
    created: list[str]
    skipped: list[str]
    undo_id: str | None = None


class UndoRequest(BaseModel):
    undo_id: str


class UndoResponse(BaseModel):
    deleted: list[str]
    skipped: list[str]
