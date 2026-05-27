from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.app.core.config import Settings

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - handled by dependency installation
    ChatOpenAI = None


class RouterDecision(BaseModel):
    agent: Literal["query_agent", "action_agent"]
    intent: str
    confidence: float


class SupervisorRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = None
        if settings.openai_api_key and ChatOpenAI is not None:
            self.llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
            ).with_structured_output(RouterDecision)

    async def route(self, message: str) -> RouterDecision:
        heuristic = self._heuristic_route(message)
        if self.llm is None:
            return heuristic

        try:
            prompt = (
                "You route a Zoho Projects assistant message to exactly one agent.\n"
                "- query_agent handles read-only requests.\n"
                "- action_agent handles create, update, delete, assign, or mutate requests.\n"
                "Return the agent, a short intent label, and confidence.\n\n"
                f"User message: {message}"
            )
            result = await self.llm.ainvoke(prompt)
            return result
        except Exception:
            return heuristic

    def _heuristic_route(self, message: str) -> RouterDecision:
        text = message.lower()
        action_keywords = [
            "create",
            "add",
            "update",
            "change",
            "delete",
            "remove",
            "assign",
            "mark",
            "complete",
            "close",
            "reopen",
        ]
        if any(keyword in text for keyword in action_keywords):
            return RouterDecision(agent="action_agent", intent="write_operation", confidence=0.82)
        return RouterDecision(agent="query_agent", intent="read_operation", confidence=0.74)

