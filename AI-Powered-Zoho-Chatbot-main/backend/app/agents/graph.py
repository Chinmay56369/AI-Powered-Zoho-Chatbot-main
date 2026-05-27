from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.agents.action_agent import ActionAgent
from backend.app.agents.query_agent import QueryAgent
from backend.app.agents.router import SupervisorRouter
from backend.app.services.memory_store import MemoryStore


class AssistantState(TypedDict, total=False):
    user_id: int
    session_id: str
    message: str
    context: dict[str, Any]
    long_term_memory: dict[str, Any]
    pending_action: dict[str, Any] | None
    confirmation_result: str | None
    route: str
    route_intent: str
    reply: str
    used_tools: list[str]
    active_project_name: str | None


class ProjectAssistantGraph:
    def __init__(
        self,
        router: SupervisorRouter,
        query_agent: QueryAgent,
        action_agent: ActionAgent,
        memory_store: MemoryStore,
    ) -> None:
        self.router = router
        self.query_agent = query_agent
        self.action_agent = action_agent
        self.memory_store = memory_store
        self.graph = self._build()

    async def run(self, user_id: int, session_id: str, message: str) -> dict[str, Any]:
        return await self.graph.ainvoke(
            {
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
            }
        )

    def _build(self):
        workflow = StateGraph(AssistantState)
        workflow.add_node("load_context", self._load_context)
        workflow.add_node("check_confirmation", self._check_confirmation)
        workflow.add_node("route_message", self._route_message)
        workflow.add_node("query_agent", self._query_agent)
        workflow.add_node("action_agent", self._action_agent)
        workflow.add_node("execute_pending_action", self._execute_pending_action)
        workflow.add_node("cancel_pending_action", self._cancel_pending_action)

        workflow.add_edge(START, "load_context")
        workflow.add_edge("load_context", "check_confirmation")
        workflow.add_conditional_edges(
            "check_confirmation",
            self._next_after_confirmation_check,
            {
                "execute_pending_action": "execute_pending_action",
                "cancel_pending_action": "cancel_pending_action",
                "route_message": "route_message",
            },
        )
        workflow.add_conditional_edges(
            "route_message",
            self._next_after_route,
            {
                "query_agent": "query_agent",
                "action_agent": "action_agent",
            },
        )
        workflow.add_edge("query_agent", END)
        workflow.add_edge("action_agent", END)
        workflow.add_edge("execute_pending_action", END)
        workflow.add_edge("cancel_pending_action", END)
        return workflow.compile()

    async def _load_context(self, state: AssistantState) -> AssistantState:
        await self.memory_store.ensure_session(state["session_id"], state["user_id"])
        context = await self.memory_store.get_session_context(state["session_id"])
        long_term = await self.memory_store.get_long_term_memory(state["user_id"])
        pending_action = await self.memory_store.get_pending_action(state["session_id"], state["user_id"])
        return {
            "context": context,
            "long_term_memory": long_term,
            "pending_action": pending_action,
        }

    async def _check_confirmation(self, state: AssistantState) -> AssistantState:
        pending = state.get("pending_action")
        if not pending:
            return {"confirmation_result": None}
        decision = self.action_agent.interpret_confirmation(state["message"])
        return {"confirmation_result": decision}

    def _next_after_confirmation_check(self, state: AssistantState) -> str:
        if state.get("confirmation_result") == "confirm":
            return "execute_pending_action"
        if state.get("confirmation_result") == "cancel":
            return "cancel_pending_action"
        return "route_message"

    async def _route_message(self, state: AssistantState) -> AssistantState:
        decision = await self.router.route(state["message"])
        return {"route": decision.agent, "route_intent": decision.intent}

    def _next_after_route(self, state: AssistantState) -> str:
        return state["route"]

    async def _query_agent(self, state: AssistantState) -> AssistantState:
        result = await self.query_agent.handle(
            user_id=state["user_id"],
            session_id=state["session_id"],
            message=state["message"],
        )
        return result

    async def _action_agent(self, state: AssistantState) -> AssistantState:
        result = await self.action_agent.handle(
            user_id=state["user_id"],
            session_id=state["session_id"],
            message=state["message"],
        )
        return result

    async def _execute_pending_action(self, state: AssistantState) -> AssistantState:
        pending = state.get("pending_action")
        if not pending:
            return {
                "reply": "There isn't a pending action to confirm right now.",
                "route": "action_agent",
                "used_tools": [],
            }
        return await self.action_agent.execute_pending_action(
            user_id=state["user_id"],
            session_id=state["session_id"],
            pending_action=pending,
        )

    async def _cancel_pending_action(self, state: AssistantState) -> AssistantState:
        pending = state.get("pending_action")
        if pending:
            await self.memory_store.clear_pending_action(pending["id"])
        active_project_name = (state.get("context") or {}).get("active_project_name")
        return {
            "reply": "Okay, I cancelled that action with no changes made in Zoho Projects.",
            "route": "action_agent",
            "active_project_name": active_project_name,
            "used_tools": [],
        }

