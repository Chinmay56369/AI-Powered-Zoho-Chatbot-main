from __future__ import annotations

import re
from typing import Any

from backend.app.agents.tools import ZohoProjectsToolkit
from backend.app.services.memory_store import MemoryStore


class QueryAgent:
    def __init__(self, toolkit: ZohoProjectsToolkit, memory_store: MemoryStore) -> None:
        self.toolkit = toolkit
        self.memory_store = memory_store

    async def handle(self, user_id: int, session_id: str, message: str) -> dict[str, Any]:
        text = message.lower()
        used_tools: list[str] = []

        if "project" in text and "task" not in text and any(
            cue in text for cue in ("what", "which", "list", "show", "have")
        ):
            projects = await self.toolkit.list_projects(user_id, session_id)
            used_tools.append("list_projects")
            if not projects:
                return {
                    "reply": "I couldn't find any Zoho Projects projects for this account yet.",
                    "route": "query_agent",
                    "used_tools": used_tools,
                }

            lines = ["Here are your projects:"]
            for index, project in enumerate(projects, start=1):
                lines.append(
                    f"{index}. {project['name']} (id: {project['id']}, open tasks: {project['open_tasks']})"
                )
            return {
                "reply": "\n".join(lines),
                "route": "query_agent",
                "used_tools": used_tools,
            }

        project = await self.memory_store.resolve_project_reference(user_id, session_id, message)
        if project:
            await self.memory_store.set_active_project(session_id, user_id, project["id"], project["name"])

        if any(keyword in text for keyword in ("utilisation", "utilization", "workload", "most tasks", "task load")):
            if not project:
                return {
                    "reply": "Tell me which project to analyse first, or ask me to list your projects.",
                    "route": "query_agent",
                    "used_tools": used_tools,
                }
            utilisation = await self.toolkit.get_task_utilisation(user_id, project["id"])
            used_tools.append("get_task_utilisation")
            if not utilisation:
                return {
                    "reply": f"I couldn't find any tasks in {project['name']} yet.",
                    "route": "query_agent",
                    "active_project_name": project["name"],
                    "used_tools": used_tools,
                }
            lines = [f"Task load for {project['name']}:"]
            for member in utilisation[:8]:
                lines.append(
                    f"- {member['member']}: {member['total_tasks']} tasks {member['status_breakdown']}"
                )
            return {
                "reply": "\n".join(lines),
                "route": "query_agent",
                "active_project_name": project["name"],
                "used_tools": used_tools,
            }

        if any(keyword in text for keyword in ("member", "members", "team", "who is on")):
            if not project:
                return {
                    "reply": "Tell me which project you want members for, or ask me to list your projects first.",
                    "route": "query_agent",
                    "used_tools": used_tools,
                }
            members = await self.toolkit.list_project_members(user_id, project["id"])
            used_tools.append("list_project_members")
            if not members:
                return {
                    "reply": f"I couldn't find any members for {project['name']}.",
                    "route": "query_agent",
                    "active_project_name": project["name"],
                    "used_tools": used_tools,
                }
            lines = [f"Project members for {project['name']}:"]
            for member in members:
                lines.append(
                    f"- {member['name']} ({member['role'] or 'role unknown'})"
                    f"{' - inactive' if not member['active'] else ''}"
                )
            return {
                "reply": "\n".join(lines),
                "route": "query_agent",
                "active_project_name": project["name"],
                "used_tools": used_tools,
            }

        task_reference = await self.memory_store.resolve_task_reference(session_id, message)
        if task_reference and any(keyword in text for keyword in ("detail", "details", "about", "show task")):
            if not project:
                return {
                    "reply": "I know which task you mean, but I still need the project context. Ask me for the tasks in a project first or mention the project by name.",
                    "route": "query_agent",
                    "used_tools": used_tools,
                }
            details = await self.toolkit.get_task_details(user_id, project["id"], task_reference["id"])
            used_tools.append("get_task_details")
            owner_text = ", ".join(owner["name"] for owner in details.get("owners", [])) or "Unassigned"
            reply = (
                f"Task details for {details['name']}:\n"
                f"- id: {details['id']}\n"
                f"- owners: {owner_text}\n"
                f"- status: {(details.get('status') or {}).get('name', 'Unknown')}\n"
                f"- priority: {details.get('priority') or 'None'}\n"
                f"- due: {details.get('end_date') or 'Not set'}\n"
                f"- progress: {details.get('percent_complete') or '0'}%"
            )
            return {
                "reply": reply,
                "route": "query_agent",
                "active_project_name": project["name"],
                "used_tools": used_tools,
            }

        if "task" in text or "tasks" in text:
            if not project:
                return {
                    "reply": "Tell me which project you want tasks for, or ask me to list your projects first.",
                    "route": "query_agent",
                    "used_tools": used_tools,
                }
            task_status = self._extract_status_filter(text)
            due_date = self._extract_due_date(text)
            assignee = await self._extract_assignee_id(user_id, project["id"], message)
            tasks = await self.toolkit.list_tasks(
                user_id=user_id,
                session_id=session_id,
                project_id=project["id"],
                status=task_status,
                assignee=assignee,
                due_date=due_date,
            )
            used_tools.append("list_tasks")
            if not tasks:
                return {
                    "reply": f"I couldn't find matching tasks in {project['name']}.",
                    "route": "query_agent",
                    "active_project_name": project["name"],
                    "used_tools": used_tools,
                }
            lines = [f"Tasks for {project['name']}:"]
            for index, task in enumerate(tasks[:12], start=1):
                owner_text = ", ".join(owner["name"] for owner in task.get("owners", [])) or "Unassigned"
                status_name = (task.get("status") or {}).get("name", "Unknown")
                lines.append(
                    f"{index}. {task['name']} (id: {task['id']}, status: {status_name}, owner: {owner_text}, due: {task.get('end_date') or 'not set'})"
                )
            return {
                "reply": "\n".join(lines),
                "route": "query_agent",
                "active_project_name": project["name"],
                "used_tools": used_tools,
            }

        return {
            "reply": "I can list projects, show tasks, fetch task details, list project members, or summarise workload. Try asking something like 'What projects do I have?' or 'Show tasks for the first one.'",
            "route": "query_agent",
            "used_tools": used_tools,
        }

    @staticmethod
    def _extract_status_filter(text: str) -> str | None:
        if any(word in text for word in ("completed", "closed", "done")):
            return "completed"
        if any(word in text for word in ("open", "pending", "not completed", "notcompleted")):
            return "notcompleted"
        return None

    @staticmethod
    def _extract_due_date(text: str) -> str | None:
        date_match = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|today|tomorrow)\b", text)
        return date_match.group(1) if date_match else None

    async def _extract_assignee_id(self, user_id: int, project_id: str, message: str) -> str | None:
        match = re.search(r"(?:assigned to|for)\s+([a-zA-Z][a-zA-Z .'-]+)", message)
        if not match:
            return None
        return await self.toolkit.resolve_member_id(user_id, project_id, match.group(1).strip())

