import asyncio

from backend.app.core.database import Database
from backend.app.services.memory_store import MemoryStore


async def _build_store() -> tuple[Database, MemoryStore, int]:
    database = Database(":memory:")
    await database.connect()
    store = MemoryStore(database)
    await database.execute(
        """
        INSERT INTO users (zoho_login_id, display_name, email, portal_id, portal_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("zoho-user-1", "Rajib Panda", "rajib@example.com", "portal-1", "Zoho Projects"),
    )
    user = await database.fetch_one("SELECT id FROM users WHERE zoho_login_id = ?", ("zoho-user-1",))
    assert user is not None
    return database, store, int(user["id"])


def test_short_term_memory_keeps_active_project_within_session():
    async def scenario():
        database, store, user_id = await _build_store()
        try:
            await store.ensure_session("session-a", user_id)
            await store.remember_projects(
                "session-a",
                user_id,
                [
                    {"id": "1001", "name": "Website Redesign"},
                    {"id": "1002", "name": "Marketing Launch"},
                ],
            )

            project = await store.resolve_project_reference(user_id, "session-a", "show tasks for the first project")

            assert project == {"id": "1001", "name": "Website Redesign"}
        finally:
            await database.close()

    asyncio.run(scenario())


def test_long_term_memory_persists_queries_and_projects_across_sessions():
    async def scenario():
        database, store, user_id = await _build_store()
        try:
            await store.ensure_session("session-a", user_id)
            await store.remember_query(user_id, "Show tasks in Website Redesign")
            await store.set_active_project("session-a", user_id, "1001", "Website Redesign")
            await store.remember_projects(
                "session-a",
                user_id,
                [
                    {"id": "1001", "name": "Website Redesign"},
                    {"id": "1002", "name": "Marketing Launch"},
                ],
            )

            memories = await store.get_long_term_memory(user_id)
            assert memories["recent_queries"][0] == "Show tasks in Website Redesign"
            assert memories["last_active_project"]["name"] == "Website Redesign"
            assert memories["frequent_projects"][0]["name"] == "Website Redesign"

            await store.ensure_session("session-b", user_id)
            project = await store.resolve_project_reference(user_id, "session-b", "show tasks")

            assert project == {"id": "1001", "name": "Website Redesign"}
        finally:
            await database.close()

    asyncio.run(scenario())

