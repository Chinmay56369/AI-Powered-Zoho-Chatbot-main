from __future__ import annotations

from pydantic import BaseModel, Field


class PendingActionPreview(BaseModel):
    id: str
    action_name: str
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    route: str
    pending_action: PendingActionPreview | None = None
    active_project_name: str | None = None
    used_tools: list[str] = Field(default_factory=list)


class MeResponse(BaseModel):
    authenticated: bool
    login_url: str | None = None
    user: dict[str, object] | None = None

