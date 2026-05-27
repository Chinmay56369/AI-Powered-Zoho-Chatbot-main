from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from backend.app.services.memory_store import MemoryStore
from backend.app.services.zoho_client import ZohoClient
from backend.app.utils.dates import parse_human_date


class ZohoProjectsToolkit:
    def __init__(self, zoho_client: ZohoClient, memory_store: MemoryStore) -> None:
        self.zoho_client = zoho_client
        self.memory_store = memory_store

    async def list_projects(self, user_id: int, session_id: str) -> list[dict[str, Any]]:
        response = await self.zoho_client.list_projects(user_id)
        projects = [
            {
                "id": str(project.get("id") or project.get("id_string")),
                "name": project["name"],
                "status": project.get("status"),
                "owner_id": project.get("owner_id"),
                "open_tasks": (project.get("task_count") or {}).get("open", 0),
            }
            for project in response.get("projects", [])
        ]
        await self.memory_store.remember_projects(session_id, user_id, projects)
        return projects

    async def list_tasks(
        self,
        user_id: int,
        session_id: str,
        project_id: str,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"all_tasks": "true"}
        if status:
            params["status"] = status
        if assignee:
            params["owner"] = assignee

        response = await self.zoho_client.list_tasks(user_id, project_id, params=params)
        tasks = [self._normalise_task(task) for task in response.get("tasks", [])]

        formatted_due_date = parse_human_date(due_date)
        if formatted_due_date:
            tasks = [task for task in tasks if task.get("end_date") == formatted_due_date]

        await self.memory_store.remember_tasks(session_id, tasks)
        return tasks

    async def get_task_details(self, user_id: int, project_id: str, task_id: str) -> dict[str, Any]:
        response = await self.zoho_client.get_task_details(user_id, project_id, task_id)
        tasks = response.get("tasks", [])
        if not tasks:
            raise RuntimeError(f"Task {task_id} was not found in project {project_id}.")
        return self._normalise_task(tasks[0], include_raw=True)

    async def create_task(self, user_id: int, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        outbound = {
            "name": payload["name"],
            "description": payload.get("description", ""),
        }
        if payload.get("due_date"):
            outbound["start_date"] = parse_human_date(payload.get("start_date")) or parse_human_date(
                payload["due_date"]
            )
            outbound["end_date"] = parse_human_date(payload["due_date"])
        if payload.get("priority"):
            outbound["priority"] = payload["priority"].title()
        if payload.get("person_responsible"):
            outbound["person_responsible"] = payload["person_responsible"]

        response = await self.zoho_client.create_task(user_id, project_id, outbound)
        tasks = response.get("tasks", [])
        if not tasks:
            return {"message": "Task created, but Zoho did not return the created task payload."}
        return self._normalise_task(tasks[0], include_raw=True)

    async def update_task(self, user_id: int, project_id: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        outbound: dict[str, Any] = {}
        if payload.get("priority"):
            outbound["priority"] = payload["priority"].title()
        if payload.get("due_date"):
            parsed_due_date = parse_human_date(payload["due_date"])
            if parsed_due_date:
                current_task = await self.get_task_details(user_id, project_id, task_id)
                outbound["start_date"] = current_task.get("start_date") or parsed_due_date
                outbound["end_date"] = parsed_due_date
        if payload.get("person_responsible"):
            outbound["person_responsible"] = payload["person_responsible"]

        requested_status = payload.get("status")
        if requested_status:
            status_fields = await self.resolve_status_update_fields(user_id, project_id, requested_status)
            outbound.update(status_fields)

        response = await self.zoho_client.update_task(user_id, project_id, task_id, outbound)
        tasks = response.get("tasks", [])
        if not tasks:
            return {"message": "Task updated, but Zoho did not return the updated task payload."}
        return self._normalise_task(tasks[0], include_raw=True)

    async def delete_task(self, user_id: int, project_id: str, task_id: str) -> dict[str, Any]:
        await self.zoho_client.delete_task(user_id, project_id, task_id)
        return {"deleted": True, "task_id": task_id}

    async def list_project_members(self, user_id: int, project_id: str) -> list[dict[str, Any]]:
        response = await self.zoho_client.list_project_members(user_id, project_id)
        return [
            {
                "id": str(member["id"]),
                "name": member["name"],
                "email": member.get("email"),
                "role": member.get("role"),
                "active": member.get("active", True),
            }
            for member in response.get("users", [])
        ]

    async def get_task_utilisation(self, user_id: int, project_id: str) -> list[dict[str, Any]]:
        tasks = await self.list_tasks(user_id, session_id=f"util-{project_id}", project_id=project_id)
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        for task in tasks:
            owners = task.get("owners") or [{"name": "Unassigned"}]
            status_name = (task.get("status") or {}).get("name", "Unknown")
            for owner in owners:
                counts[owner["name"]]["total"] += 1
                counts[owner["name"]][status_name] += 1

        summary = [
            {
                "member": member,
                "total_tasks": counter["total"],
                "status_breakdown": dict(counter),
            }
            for member, counter in sorted(counts.items(), key=lambda item: item[1]["total"], reverse=True)
        ]
        return summary

    async def resolve_member_id(self, user_id: int, project_id: str, member_name: str) -> str | None:
        members = await self.list_project_members(user_id, project_id)
        member_name_lower = member_name.lower()
        for member in members:
            if member["name"].lower() == member_name_lower:
                return member["id"]
        for member in members:
            if member_name_lower in member["name"].lower():
                return member["id"]
        return None

    async def resolve_status_update_fields(
        self,
        user_id: int,
        project_id: str,
        requested_status: str,
    ) -> dict[str, Any]:
        requested_status_lower = requested_status.lower()
        tasks = await self.list_tasks(user_id, session_id=f"status-{project_id}", project_id=project_id)
        status_map: dict[str, str] = {}
        for task in tasks:
            status = task.get("status") or {}
            status_name = status.get("name")
            status_type = status.get("type")
            status_id = status.get("id")
            if status_id and status_name:
                status_map[status_name.lower()] = str(status_id)
            if status_id and status_type:
                status_map[status_type.lower()] = str(status_id)

        if requested_status_lower in status_map:
            return {"custom_status": status_map[requested_status_lower]}

        if requested_status_lower in {"completed", "complete", "closed", "done"}:
            return {"percent_complete": 100}
        if requested_status_lower in {"open", "reopen", "notcompleted"}:
            return {"percent_complete": 0}
        return {}

    @staticmethod
    def _normalise_task(task: dict[str, Any], include_raw: bool = False) -> dict[str, Any]:
        owners = (task.get("details") or {}).get("owners", [])
        payload = {
            "id": str(task.get("id") or task.get("id_string")),
            "name": task.get("name"),
            "description": task.get("description"),
            "priority": task.get("priority"),
            "percent_complete": task.get("percent_complete"),
            "start_date": task.get("start_date"),
            "end_date": task.get("end_date"),
            "tasklist": task.get("tasklist"),
            "status": task.get("status"),
            "owners": [{"id": str(owner["id"]), "name": owner["name"]} for owner in owners],
        }
        if include_raw:
            payload["raw"] = task
        return payload

