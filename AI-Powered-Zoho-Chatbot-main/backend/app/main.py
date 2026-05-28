from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.app.agents.action_agent import ActionAgent
from backend.app.agents.graph import ProjectAssistantGraph
from backend.app.agents.query_agent import QueryAgent
from backend.app.agents.router import SupervisorRouter
from backend.app.agents.tools import ZohoProjectsToolkit
from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_chat import router as chat_router
from backend.app.core.config import get_settings
from backend.app.core.database import Database
from backend.app.services.memory_store import MemoryStore
from backend.app.services.zoho_client import ZohoClient


@dataclass
class AppServices:
    settings: object
    database: Database
    memory_store: MemoryStore
    zoho_client: ZohoClient
    assistant_graph: ProjectAssistantGraph


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database = Database(str(settings.resolved_database_path))
    await database.connect()
    http_client = httpx.AsyncClient(timeout=30.0)

    memory_store = MemoryStore(database)
    zoho_client = ZohoClient(settings, database, http_client)
    toolkit = ZohoProjectsToolkit(zoho_client, memory_store)
    router = SupervisorRouter(settings)
    query_agent = QueryAgent(toolkit, memory_store)
    action_agent = ActionAgent(toolkit, memory_store)
    assistant_graph = ProjectAssistantGraph(router, query_agent, action_agent, memory_store)

    app.state.services = AppServices(
        settings=settings,
        database=database,
        memory_store=memory_store,
        zoho_client=zoho_client,
        assistant_graph=assistant_graph,
    )

    yield

    await http_client.aclose()
    await database.close()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=False,
)

app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "auth_login": "/auth/login",
        "chat_endpoint": "/chat",
        "health": "/health",
    }

