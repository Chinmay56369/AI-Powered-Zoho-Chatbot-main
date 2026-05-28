import asyncio

from backend.app.agents.action_agent import ActionAgent
from backend.app.agents.graph import ProjectAssistantGraph
from backend.app.agents.router import RouterDecision
from backend.app.agents.router import SupervisorRouter
from backend.app.core.config import Settings


class DummyToolkit:
    pass


class DummyMemoryStore:
    pass


class FakeRouter:
    def __init__(self, agent: str, intent: str) -> None:
        self.decision = RouterDecision(agent=agent, intent=intent, confidence=1.0)

    async def route(self, message: str) -> RouterDecision:
        return self.decision


class FakeGraphMemoryStore:
    def __init__(self, pending_action: dict | None = None) -> None:
        self.pending_action = pending_action
        self.cleared_action_id: str | None = None

    async def ensure_session(self, session_id: str, user_id: int) -> None:
        return None

    async def get_session_context(self, session_id: str) -> dict:
        return {}

    async def get_long_term_memory(self, user_id: int) -> dict:
        return {}

    async def get_pending_action(self, session_id: str, user_id: int):
        return self.pending_action

    async def clear_pending_action(self, action_id: str) -> None:
        self.cleared_action_id = action_id
        return None


class RecordingQueryAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def handle(self, user_id: int, session_id: str, message: str) -> dict:
        self.calls += 1
        return {"reply": "query", "route": "query_agent", "used_tools": ["list_projects"]}


class RecordingActionAgent:
    def __init__(self, confirmation_result: str | None = None) -> None:
        self.calls = 0
        self.execute_calls = 0
        self.confirmation_result = confirmation_result

    async def handle(self, user_id: int, session_id: str, message: str) -> dict:
        self.calls += 1
        return {"reply": "action", "route": "action_agent", "used_tools": []}

    async def execute_pending_action(self, user_id: int, session_id: str, pending_action: dict) -> dict:
        self.execute_calls += 1
        return {"reply": "executed", "route": "action_agent", "used_tools": ["create_task"]}

    def interpret_confirmation(self, message: str) -> str | None:
        return self.confirmation_result


class FakeActionToolkit:
    async def create_task(self, user_id: int, project_id: str, payload: dict) -> dict:
        raise AssertionError("Write execution should not happen during preparation.")

    async def resolve_member_id(self, user_id: int, project_id: str, member_name: str) -> str | None:
        return "member-1"


class FakeActionMemoryStore:
    def __init__(self) -> None:
        self.pending_action_payload: dict | None = None

    async def resolve_project_reference(self, user_id: int, session_id: str, message: str) -> dict:
        return {"id": "portal-1", "name": "Website Redesign"}

    async def set_active_project(self, session_id: str, user_id: int, project_id: str, project_name: str) -> None:
        return None

    async def resolve_task_reference(self, session_id: str, message: str):
        return None

    async def create_pending_action(
        self,
        session_id: str,
        user_id: int,
        action_name: str,
        summary: str,
        payload: dict,
    ) -> dict:
        self.pending_action_payload = {
            "id": "pending-1",
            "action_name": action_name,
            "summary": summary,
            "payload": payload,
        }
        return self.pending_action_payload


def build_settings() -> Settings:
    return Settings(
        SECRET_KEY="test-secret",
        ZOHO_CLIENT_ID="client",
        ZOHO_CLIENT_SECRET="secret",
    )


def test_router_sends_write_requests_to_action_agent():
    router = SupervisorRouter(build_settings())
    result = router._heuristic_route("Create a task called API integration")
    assert result.agent == "action_agent"


def test_router_sends_read_requests_to_query_agent():
    router = SupervisorRouter(build_settings())
    result = router._heuristic_route("What projects do I have?")
    assert result.agent == "query_agent"


def test_confirmation_interpretation():
    agent = ActionAgent(DummyToolkit(), DummyMemoryStore())  # type: ignore[arg-type]
    assert agent.interpret_confirmation("confirm") == "confirm"
    assert agent.interpret_confirmation("cancel") == "cancel"
    assert agent.interpret_confirmation("show my tasks") is None


def test_graph_routes_reads_only_to_query_agent():
    memory_store = FakeGraphMemoryStore()
    query_agent = RecordingQueryAgent()
    action_agent = RecordingActionAgent()
    graph = ProjectAssistantGraph(
        FakeRouter("query_agent", "read_operation"),
        query_agent,  # type: ignore[arg-type]
        action_agent,  # type: ignore[arg-type]
        memory_store,  # type: ignore[arg-type]
    )

    result = asyncio.run(graph.run(user_id=1, session_id="session-1", message="What projects do I have?"))

    assert result["route"] == "query_agent"
    assert query_agent.calls == 1
    assert action_agent.calls == 0


def test_graph_routes_writes_only_to_action_agent():
    memory_store = FakeGraphMemoryStore()
    query_agent = RecordingQueryAgent()
    action_agent = RecordingActionAgent()
    graph = ProjectAssistantGraph(
        FakeRouter("action_agent", "write_operation"),
        query_agent,  # type: ignore[arg-type]
        action_agent,  # type: ignore[arg-type]
        memory_store,  # type: ignore[arg-type]
    )

    result = asyncio.run(
        graph.run(user_id=1, session_id="session-1", message="Create a task called API integration")
    )

    assert result["route"] == "action_agent"
    assert query_agent.calls == 0
    assert action_agent.calls == 1


def test_action_agent_stages_write_requests_for_confirmation():
    memory_store = FakeActionMemoryStore()
    agent = ActionAgent(FakeActionToolkit(), memory_store)  # type: ignore[arg-type]

    result = asyncio.run(
        agent.handle(
            user_id=1,
            session_id="session-1",
            message="Create a task called API integration in Website Redesign",
        )
    )

    assert result["route"] == "action_agent"
    assert result["pending_action"]["action_name"] == "create_task"
    assert result["pending_action"]["payload"]["name"] == "API integration"
    assert "confirm" in result["reply"].lower()


def test_action_agent_stages_assign_requests_for_confirmation():
    memory_store = FakeActionMemoryStore()

    async def resolve_task_reference(session_id: str, message: str):
        return {"id": "task-1", "name": "API integration"}

    memory_store.resolve_task_reference = resolve_task_reference  # type: ignore[assignment]
    agent = ActionAgent(FakeActionToolkit(), memory_store)  # type: ignore[arg-type]

    result = asyncio.run(
        agent.handle(
            user_id=1,
            session_id="session-1",
            message="assign task API integration to Rajib in Website Redesign",
        )
    )

    assert result["route"] == "action_agent"
    assert result["pending_action"]["action_name"] == "update_task"
    assert result["pending_action"]["payload"]["person_responsible"] == "member-1"
    assert result["pending_action"]["payload"]["assignee_name"] == "Rajib"
    assert "assignee -> Rajib" in result["pending_action"]["summary"]


def test_graph_executes_pending_action_only_after_explicit_confirmation():
    pending_action = {
        "id": "pending-1",
        "action_name": "create_task",
        "summary": "Create task 'API integration' in Website Redesign",
        "payload": {"project_id": "portal-1", "project_name": "Website Redesign", "name": "API integration"},
    }
    memory_store = FakeGraphMemoryStore(pending_action=pending_action)
    query_agent = RecordingQueryAgent()
    action_agent = RecordingActionAgent(confirmation_result="confirm")
    graph = ProjectAssistantGraph(
        FakeRouter("query_agent", "read_operation"),
        query_agent,  # type: ignore[arg-type]
        action_agent,  # type: ignore[arg-type]
        memory_store,  # type: ignore[arg-type]
    )

    result = asyncio.run(graph.run(user_id=1, session_id="session-1", message="confirm"))

    assert result["route"] == "action_agent"
    assert result["reply"] == "executed"
    assert action_agent.execute_calls == 1
    assert query_agent.calls == 0


def test_graph_cancels_pending_action_without_side_effects():
    pending_action = {
        "id": "pending-1",
        "action_name": "delete_task",
        "summary": "Delete task 'API integration' from Website Redesign",
        "payload": {"project_id": "portal-1", "project_name": "Website Redesign", "task_id": "task-1"},
    }
    memory_store = FakeGraphMemoryStore(pending_action=pending_action)
    query_agent = RecordingQueryAgent()
    action_agent = RecordingActionAgent(confirmation_result="cancel")
    graph = ProjectAssistantGraph(
        FakeRouter("action_agent", "write_operation"),
        query_agent,  # type: ignore[arg-type]
        action_agent,  # type: ignore[arg-type]
        memory_store,  # type: ignore[arg-type]
    )

    result = asyncio.run(graph.run(user_id=1, session_id="session-1", message="cancel"))

    assert result["route"] == "action_agent"
    assert "cancelled" in result["reply"].lower()
    assert memory_store.cleared_action_id == "pending-1"
    assert action_agent.execute_calls == 0
    assert query_agent.calls == 0
