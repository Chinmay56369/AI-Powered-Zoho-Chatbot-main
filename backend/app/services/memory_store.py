from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.app.core.database import Database


ORDINAL_WORDS = {
    "first": 0,
    "1st": 0,
    "one": 0,
    "second": 1,
    "2nd": 1,
    "two": 1,
    "third": 2,
    "3rd": 2,
    "three": 2,
    "fourth": 3,
    "4th": 3,
    "four": 3,
    "fifth": 4,
    "5th": 4,
    "five": 4,
}


class MemoryStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def ensure_session(self, session_id: str, user_id: int) -> None:
        await self.database.execute(
            """
            INSERT INTO conversation_sessions (session_id, user_id)
            VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                user_id = excluded.user_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, user_id),
        )

    async def save_message(self, session_id: str, role: str, content: str) -> None:
        await self.database.execute(
            """
            INSERT INTO conversation_messages (session_id, role, content)
            VALUES (?, ?, ?)
            """,
            (session_id, role, content),
        )

    async def get_recent_messages(self, session_id: str, limit: int = 8) -> list[dict[str, str]]:
        rows = await self.database.fetch_all(
            """
            SELECT role, content
            FROM conversation_messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    async def remember_projects(
        self,
        session_id: str,
        user_id: int,
        projects: list[dict[str, Any]],
    ) -> None:
        payload = json.dumps(projects)
        await self.database.execute(
            """
            UPDATE conversation_sessions
            SET last_project_listing_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (payload, session_id),
        )
        await self.set_memory(user_id, "recent_projects", projects[:10])

    async def remember_query(self, user_id: int, query: str, limit: int = 12) -> None:
        cleaned = " ".join(query.split()).strip()
        if not cleaned:
            return

        long_term = await self.get_long_term_memory(user_id)
        existing = long_term.get("recent_queries")
        recent_queries = [item for item in existing if isinstance(item, str)] if isinstance(existing, list) else []
        recent_queries = [item for item in recent_queries if item.lower() != cleaned.lower()]
        recent_queries.insert(0, cleaned)
        await self.set_memory(user_id, "recent_queries", recent_queries[:limit])

    async def remember_tasks(self, session_id: str, tasks: list[dict[str, Any]]) -> None:
        payload = json.dumps(tasks)
        await self.database.execute(
            """
            UPDATE conversation_sessions
            SET last_task_listing_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (payload, session_id),
        )

    async def set_active_project(self, session_id: str, user_id: int, project_id: str, name: str) -> None:
        await self.database.execute(
            """
            UPDATE conversation_sessions
            SET active_project_id = ?, active_project_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (project_id, name, session_id),
        )
        await self.set_memory(user_id, "last_active_project", {"id": project_id, "name": name})
        await self.record_project_access(user_id, project_id, name)

    async def record_project_access(self, user_id: int, project_id: str, name: str, limit: int = 10) -> None:
        long_term = await self.get_long_term_memory(user_id)
        existing = long_term.get("frequent_projects")
        frequent_projects = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []

        now = datetime.now(UTC).isoformat(timespec="seconds")
        updated = False
        for project in frequent_projects:
            if str(project.get("id")) == project_id:
                project["name"] = name
                project["access_count"] = int(project.get("access_count", 0)) + 1
                project["last_accessed_at"] = now
                updated = True
                break

        if not updated:
            frequent_projects.append(
                {
                    "id": project_id,
                    "name": name,
                    "access_count": 1,
                    "last_accessed_at": now,
                }
            )

        frequent_projects.sort(
            key=lambda item: (
                -int(item.get("access_count", 0)),
                item.get("last_accessed_at", ""),
            )
        )
        await self.set_memory(user_id, "frequent_projects", frequent_projects[:limit])

    async def get_session_context(self, session_id: str) -> dict[str, Any]:
        row = await self.database.fetch_one(
            """
            SELECT active_project_id, active_project_name, last_project_listing_json, last_task_listing_json
            FROM conversation_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )
        if row is None:
            return {}
        return {
            "active_project_id": row["active_project_id"],
            "active_project_name": row["active_project_name"],
            "last_project_listing": self._loads(row["last_project_listing_json"]),
            "last_task_listing": self._loads(row["last_task_listing_json"]),
        }

    async def set_memory(self, user_id: int, key: str, value: Any) -> None:
        payload = json.dumps(value)
        await self.database.execute(
            """
            INSERT INTO user_memories (user_id, memory_key, memory_value)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, memory_key) DO UPDATE SET
                memory_value = excluded.memory_value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, key, payload),
        )

    async def get_long_term_memory(self, user_id: int) -> dict[str, Any]:
        rows = await self.database.fetch_all(
            """
            SELECT memory_key, memory_value
            FROM user_memories
            WHERE user_id = ?
            """,
            (user_id,),
        )
        return {row["memory_key"]: self._loads(row["memory_value"]) for row in rows}

    async def resolve_project_reference(
        self,
        user_id: int,
        session_id: str,
        message: str,
    ) -> dict[str, str] | None:
        context = await self.get_session_context(session_id)
        message_lower = message.lower()
        last_projects = context.get("last_project_listing") or []

        for word, index in ORDINAL_WORDS.items():
            if word in message_lower and index < len(last_projects):
                project = last_projects[index]
                return {"id": str(project["id"]), "name": project["name"]}

        explicit = re.search(r"project\s+#?(\d+)", message_lower)
        if explicit:
            explicit_id = explicit.group(1)
            for project in last_projects:
                if str(project["id"]) == explicit_id:
                    return {"id": explicit_id, "name": project["name"]}
            return {"id": explicit_id, "name": explicit_id}

        for project in last_projects:
            if project["name"].lower() in message_lower:
                return {"id": str(project["id"]), "name": project["name"]}

        if context.get("active_project_id") and any(
            token in message_lower for token in ("it", "that project", "this project", "same project")
        ):
            return {
                "id": context["active_project_id"],
                "name": context.get("active_project_name") or context["active_project_id"],
            }

        if context.get("active_project_id"):
            return {
                "id": context["active_project_id"],
                "name": context.get("active_project_name") or context["active_project_id"],
            }

        long_term = await self.get_long_term_memory(user_id)
        recent_projects = long_term.get("recent_projects")
        if isinstance(recent_projects, list):
            for project in recent_projects:
                if isinstance(project, dict) and str(project.get("name", "")).lower() in message_lower:
                    return {"id": str(project["id"]), "name": project["name"]}

        frequent_projects = long_term.get("frequent_projects")
        if isinstance(frequent_projects, list):
            for project in frequent_projects:
                if isinstance(project, dict) and str(project.get("name", "")).lower() in message_lower:
                    return {"id": str(project["id"]), "name": project["name"]}
            if any(token in message_lower for token in ("usual project", "frequent project", "default project")):
                frequent = next((item for item in frequent_projects if isinstance(item, dict) and item.get("id")), None)
                if frequent:
                    return {"id": str(frequent["id"]), "name": frequent.get("name") or str(frequent["id"])}

        last_active = long_term.get("last_active_project")
        if isinstance(last_active, dict) and last_active.get("id"):
            return {"id": str(last_active["id"]), "name": last_active.get("name") or str(last_active["id"])}

        if isinstance(frequent_projects, list):
            frequent = next((item for item in frequent_projects if isinstance(item, dict) and item.get("id")), None)
            if frequent:
                return {"id": str(frequent["id"]), "name": frequent.get("name") or str(frequent["id"])}

        return None

    async def resolve_task_reference(self, session_id: str, message: str) -> dict[str, str] | None:
        context = await self.get_session_context(session_id)
        last_tasks = context.get("last_task_listing") or []
        message_lower = message.lower()

        for word, index in ORDINAL_WORDS.items():
            if word in message_lower and index < len(last_tasks):
                task = last_tasks[index]
                return {"id": str(task["id"]), "name": task["name"]}

        explicit = re.search(r"task\s+#?(\d+)", message_lower)
        if explicit:
            task_id = explicit.group(1)
            for task in last_tasks:
                if str(task["id"]) == task_id:
                    return {"id": task_id, "name": task["name"]}
            return {"id": task_id, "name": f"Task {task_id}"}

        bare_hash = re.search(r"#(\d+)", message_lower)
        if bare_hash:
            numeric = bare_hash.group(1)
            if len(numeric) <= 2 and last_tasks:
                ordinal_index = int(numeric) - 1
                if 0 <= ordinal_index < len(last_tasks):
                    task = last_tasks[ordinal_index]
                    return {"id": str(task["id"]), "name": task["name"]}
            return {"id": numeric, "name": f"Task {numeric}"}

        for task in last_tasks:
            if task["name"].lower() in message_lower:
                return {"id": str(task["id"]), "name": task["name"]}

        return None

    async def create_pending_action(
        self,
        session_id: str,
        user_id: int,
        action_name: str,
        summary: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        action_id = str(uuid4())
        await self.database.execute(
            """
            INSERT INTO pending_actions (id, session_id, user_id, action_name, summary, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action_id, session_id, user_id, action_name, summary, json.dumps(payload)),
        )
        return {
            "id": action_id,
            "action_name": action_name,
            "summary": summary,
            "payload": payload,
        }

    async def get_pending_action(self, session_id: str, user_id: int) -> dict[str, Any] | None:
        row = await self.database.fetch_one(
            """
            SELECT id, action_name, summary, payload_json
            FROM pending_actions
            WHERE session_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id, user_id),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "action_name": row["action_name"],
            "summary": row["summary"],
            "payload": self._loads(row["payload_json"]) or {},
        }

    async def clear_pending_action(self, action_id: str) -> None:
        await self.database.execute(
            "DELETE FROM pending_actions WHERE id = ?",
            (action_id,),
        )

    @staticmethod
    def _loads(payload: str | None) -> Any:
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
