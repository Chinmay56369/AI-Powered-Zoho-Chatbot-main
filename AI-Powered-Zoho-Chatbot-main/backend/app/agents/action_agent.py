from __future__ import annotations

import re
from typing import Any

from backend.app.agents.tools import ZohoProjectsToolkit
from backend.app.services.memory_store import MemoryStore
from backend.app.utils.dates import parse_human_date


CONFIRM_WORDS = {"confirm", "yes", "approve", "go ahead", "proceed", "do it"}
CANCEL_WORDS = {"cancel", "no", "stop", "don't", "do not"}


class ActionAgent:
    def __init__(self, toolkit: ZohoProjectsToolkit, memory_store: MemoryStore) -> None:
        self.toolkit = toolkit
        self.memory_store = memory_store

    async def handle(self, user_id: int, session_id: str, message: str) -> dict[str, Any]:
        text = message.lower()
        project = await self.memory_store.resolve_project_reference(user_id, session_id, message)
        if project:
            await self.memory_store.set_active_project(session_id, user_id, project["id"], project["name"])

        if any(keyword in text for keyword in ("delete", "remove")):
            return await self._prepare_delete(user_id, session_id, message, project)

        if "create" in text or "add" in text:
            return await self._prepare_create(user_id, session_id, message, project)

        if any(keyword in text for keyword in ("update", "change", "assign", "mark", "complete", "close", "reopen")):
            return await self._prepare_update(user_id, session_id, message, project)

        return {
            "reply": "I can prepare create, update, assign, or delete actions. Tell me what should change and I’ll pause for confirmation before I do anything.",
            "route": "action_agent",
            "used_tools": [],
        }

    async def execute_pending_action(
        self,
        user_id: int,
        session_id: str,
        pending_action: dict[str, Any],
    ) -> dict[str, Any]:
        action_name = pending_action["action_name"]
        payload = pending_action["payload"]
        used_tools = [action_name]

        if action_name == "create_task":
            created = await self.toolkit.create_task(user_id, payload["project_id"], payload)
            await self.memory_store.clear_pending_action(pending_action["id"])
            await self.memory_store.set_active_project(
                session_id,
                user_id,
                payload["project_id"],
                payload["project_name"],
            )
            return {
                "reply": f"Task created in {payload['project_name']}: {created.get('name', payload['name'])}.",
                "route": "action_agent",
                "active_project_name": payload["project_name"],
                "used_tools": used_tools,
            }

        if action_name == "update_task":
            updated = await self.toolkit.update_task(
                user_id,
                payload["project_id"],
                payload["task_id"],
                payload,
            )
            await self.memory_store.clear_pending_action(pending_action["id"])
            await self.memory_store.set_active_project(
                session_id,
                user_id,
                payload["project_id"],
                payload["project_name"],
            )
            return {
                "reply": f"Task updated in {payload['project_name']}: {updated.get('name', payload['task_name'])}.",
                "route": "action_agent",
                "active_project_name": payload["project_name"],
                "used_tools": used_tools,
            }

        if action_name == "delete_task":
            await self.toolkit.delete_task(user_id, payload["project_id"], payload["task_id"])
            await self.memory_store.clear_pending_action(pending_action["id"])
            await self.memory_store.set_active_project(
                session_id,
                user_id,
                payload["project_id"],
                payload["project_name"],
            )
            return {
                "reply": f"Task deleted from {payload['project_name']}: {payload['task_name']}.",
                "route": "action_agent",
                "active_project_name": payload["project_name"],
                "used_tools": used_tools,
            }

        raise RuntimeError(f"Unsupported pending action: {action_name}")

    @staticmethod
    def interpret_confirmation(message: str) -> str | None:
        cleaned = message.strip().lower()
        if cleaned in CONFIRM_WORDS:
            return "confirm"
        if cleaned in CANCEL_WORDS:
            return "cancel"
        return None

    async def _prepare_create(
        self,
        user_id: int,
        session_id: str,
        message: str,
        project: dict[str, str] | None,
    ) -> dict[str, Any]:
        if not project:
            return {
                "reply": "Tell me which project to create the task in first.",
                "route": "action_agent",
                "used_tools": [],
            }

        task_name = self._extract_task_name(message)
        if not task_name:
            return {
                "reply": "Tell me the task name too. For example: create a task called API Integration in the first project.",
                "route": "action_agent",
                "used_tools": [],
            }

        due_date = self._extract_due_date(message)
        priority = self._extract_priority(message)
        assignee_name = self._extract_assignee_name(message)
        person_responsible = None
        if assignee_name:
            person_responsible = await self.toolkit.resolve_member_id(user_id, project["id"], assignee_name)

        payload: dict[str, Any] = {
            "project_id": project["id"],
            "project_name": project["name"],
            "name": task_name,
            "due_date": due_date,
            "priority": priority,
        }
        if person_responsible:
            payload["person_responsible"] = person_responsible
            payload["assignee_name"] = assignee_name

        summary = f"Create task '{task_name}' in {project['name']}"
        if due_date:
            summary += f" due {due_date}"
        if priority:
            summary += f" with {priority} priority"
        if assignee_name:
            summary += f" assigned to {assignee_name}"

        pending = await self.memory_store.create_pending_action(
            session_id,
            user_id,
            "create_task",
            summary,
            payload,
        )
        return {
            "reply": f"{summary}. Reply `confirm` to proceed or `cancel` to stop.",
            "route": "action_agent",
            "pending_action": pending,
            "active_project_name": project["name"],
            "used_tools": [],
        }

    async def _prepare_update(
        self,
        user_id: int,
        session_id: str,
        message: str,
        project: dict[str, str] | None,
    ) -> dict[str, Any]:
        if not project:
            return {
                "reply": "Tell me which project the task belongs to first.",
                "route": "action_agent",
                "used_tools": [],
            }

        task = await self.memory_store.resolve_task_reference(session_id, message)
        if not task:
            return {
                "reply": "Tell me which task to update. You can refer to a task id or ask for the tasks first and then say something like 'update the first one'.",
                "route": "action_agent",
                "used_tools": [],
            }

        priority = self._extract_priority(message)
        due_date = self._extract_due_date(message)
        status = self._extract_status_change(message)
        assignee_name = self._extract_assignee_name(message)
        person_responsible = None
        if assignee_name:
            person_responsible = await self.toolkit.resolve_member_id(user_id, project["id"], assignee_name)

        if not any([priority, due_date, status, person_responsible]):
            return {
                "reply": "Tell me what should change on the task: status, assignee, due date, or priority.",
                "route": "action_agent",
                "used_tools": [],
            }

        payload: dict[str, Any] = {
            "project_id": project["id"],
            "project_name": project["name"],
            "task_id": task["id"],
            "task_name": task["name"],
        }
        if priority:
            payload["priority"] = priority
        if due_date:
            payload["due_date"] = due_date
        if status:
            payload["status"] = status
        if person_responsible:
            payload["person_responsible"] = person_responsible
            payload["assignee_name"] = assignee_name

        change_bits = []
        if status:
            change_bits.append(f"status -> {status}")
        if priority:
            change_bits.append(f"priority -> {priority}")
        if due_date:
            change_bits.append(f"due date -> {due_date}")
        if assignee_name:
            change_bits.append(f"assignee -> {assignee_name}")
        summary = f"Update task '{task['name']}' in {project['name']}: " + ", ".join(change_bits)

        pending = await self.memory_store.create_pending_action(
            session_id,
            user_id,
            "update_task",
            summary,
            payload,
        )
        return {
            "reply": f"{summary}. Reply `confirm` to proceed or `cancel` to stop.",
            "route": "action_agent",
            "pending_action": pending,
            "active_project_name": project["name"],
            "used_tools": [],
        }

    async def _prepare_delete(
        self,
        user_id: int,
        session_id: str,
        message: str,
        project: dict[str, str] | None,
    ) -> dict[str, Any]:
        if not project:
            return {
                "reply": "Tell me which project the task belongs to before I prepare the delete.",
                "route": "action_agent",
                "used_tools": [],
            }

        task = await self.memory_store.resolve_task_reference(session_id, message)
        if not task:
            return {
                "reply": "Tell me which task to delete. You can refer to a task id or ask for the tasks first and then say 'delete the first one'.",
                "route": "action_agent",
                "used_tools": [],
            }

        payload = {
            "project_id": project["id"],
            "project_name": project["name"],
            "task_id": task["id"],
            "task_name": task["name"],
        }
        summary = f"Delete task '{task['name']}' from {project['name']}"
        pending = await self.memory_store.create_pending_action(
            session_id,
            user_id,
            "delete_task",
            summary,
            payload,
        )
        return {
            "reply": f"{summary}. Reply `confirm` to proceed or `cancel` to stop.",
            "route": "action_agent",
            "pending_action": pending,
            "active_project_name": project["name"],
            "used_tools": [],
        }

    @staticmethod
    def _extract_task_name(message: str) -> str | None:
        quoted = re.search(r'["\']([^"\']+)["\']', message)
        if quoted:
            return quoted.group(1).strip()

        patterns = [
            r"(?:create|add)\s+(?:a\s+)?task\s+(?:called|named)\s+(.+?)(?:\s+in\s+|\s+for\s+|$)",
            r"(?:create|add)\s+(?:a\s+)?task\s+(.+?)(?:\s+in\s+|\s+for\s+|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .")
                if candidate:
                    return candidate
        return None

    @staticmethod
    def _extract_due_date(message: str) -> str | None:
        match = re.search(r"\b(today|tomorrow|\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b", message)
        return parse_human_date(match.group(1)) if match else None

    @staticmethod
    def _extract_priority(message: str) -> str | None:
        lower = message.lower()
        for priority in ("high", "medium", "low", "none"):
            if priority in lower:
                return priority
        return None

    @staticmethod
    def _extract_status_change(message: str) -> str | None:
        lower = message.lower()
        if "reopen" in lower:
            return "open"
        if any(word in lower for word in ("complete", "completed", "done", "closed", "close")):
            return "completed"
        if "open" in lower:
            return "open"
        return None

    @staticmethod
    def _extract_assignee_name(message: str) -> str | None:
        match = re.search(
            r"(?:assign(?: it)? to|to)\s+([A-Za-z][A-Za-z .'-]+?)(?=\s+(?:in|for)\s+|$)",
            message,
        )
        if match:
            return match.group(1).strip(" .")
        return None
