# Zoho Project Assistant

An assignment-ready Zoho Projects chatbot built with:

- `FastAPI` for OAuth, sessions, and chat APIs
- `LangGraph` for supervisor-based multi-agent routing
- `React + Vite` for the browser chat UI
- `SQLite` for OAuth token storage, short-term context, long-term memory, and pending approvals

## What this implements

- User-based Zoho OAuth 2.0 Authorization Code flow
- Separate `QueryAgent` and `ActionAgent`
- Supervisor/router node that decides which agent handles a message
- All 8 required Zoho tools:
  - `list_projects`
  - `list_tasks`
  - `get_task_details`
  - `create_task`
  - `update_task`
  - `delete_task`
  - `list_project_members`
  - `get_task_utilisation`
- Human-in-the-loop confirmation for every write action
- Short-term memory inside the current chat session
- Long-term memory persisted across logins with SQLite

## Repo layout

```text
backend/
  app/
    agents/        # supervisor, query agent, action agent, graph, tool wrapper
    api/           # auth and chat routes
    core/          # config, DB, dependencies
    services/      # Zoho client and memory store
    schemas/       # request/response models
frontend/
  src/
    components/    # login gate, chat window, confirmation card
```

## Architecture overview

### Requirement mapping: LangGraph + stateful memory + 8 tools

- LangGraph stateful graph:
  - implemented in [backend/app/agents/graph.py](backend/app/agents/graph.py)
  - flow includes context loading, confirmation checks, routing, query handling, and action handling
- Short-term memory within session:
  - active project
  - last listed projects
  - last listed tasks
  - recent chat messages
  - implemented through [backend/app/services/memory_store.py](backend/app/services/memory_store.py)
- Long-term memory across sessions:
  - recent projects
  - recent user queries
  - frequently accessed projects
  - last active project across logins
  - persisted in SQLite through `user_memories`
- Required tools implemented:
  - `list_projects`
  - `list_tasks`
  - `get_task_details`
  - `create_task`
  - `update_task`
  - `delete_task`
  - `list_project_members`
  - `get_task_utilisation`
  - implemented in [backend/app/agents/tools.py](backend/app/agents/tools.py)
- FastAPI backend contract:
  - `POST /chat` uses Pydantic request and response models in [backend/app/api/routes_chat.py](backend/app/api/routes_chat.py)
  - `GET /auth/login` and `GET /auth/callback` implement the OAuth flow in [backend/app/api/routes_auth.py](backend/app/api/routes_auth.py)
  - backend I/O uses `async def`, `httpx.AsyncClient`, and `aiosqlite`
  - session-based user identity is handled with `SessionMiddleware` and dependency injection in [backend/app/main.py](backend/app/main.py) and [backend/app/core/dependencies.py](backend/app/core/dependencies.py)
- Chat UI:
  - browser-based React UI in `frontend/src`
  - login screen starts the OAuth flow through [frontend/src/components/LoginGate.tsx](frontend/src/components/LoginGate.tsx)
  - conversation thread renders user and assistant messages in [frontend/src/components/ChatWindow.tsx](frontend/src/components/ChatWindow.tsx)
  - loading states include initial workspace restore and in-chat `Thinking…` feedback
 





<img width="1465" height="718" alt="Screenshot 2026-05-28 at 11 57 37 AM" src="https://github.com/user-attachments/assets/dd037e1d-9095-4728-89c2-020e8a413d3c" />



### Backend flow

1. User clicks `Login with Zoho`
2. FastAPI redirects to Zoho OAuth
3. `/auth/callback` exchanges the code and stores user-specific access and refresh tokens
4. `/chat` sends the user message into a LangGraph state graph
5. The supervisor routes to:
   - `QueryAgent` for read-only requests
   - `ActionAgent` for create/update/delete/assign requests
6. Any write request becomes a pending action first
7. Only a follow-up `confirm` executes the Zoho mutation

### Memory strategy

- Short-term memory:
  - active project for the current session
  - last listed projects
  - last listed tasks
  - recent chat messages
- Long-term memory:
  - recent projects
  - recent user queries
  - frequently accessed projects
  - last active project across logins

## Setup

### 1. Backend

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Copy `.env.example` to `.env` and fill in:

```env
SECRET_KEY=change-me
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REDIRECT_URI=http://localhost:8000/auth/callback
ZOHO_ACCOUNTS_BASE_URL=https://accounts.zoho.com
ZOHO_PROJECTS_API_BASE_URL=https://projectsapi.zoho.com
OPENAI_API_KEY=
```

Run the API:

```bash
uvicorn backend.app.main:app --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

If needed, create `frontend/.env` with:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Zoho OAuth configuration

Create a Zoho web-based client and set the redirect URI to:

```text
http://localhost:8000/auth/callback
```

Recommended scopes for this project:

```text
ZohoProjects.portals.READ,
ZohoProjects.projects.READ,
ZohoProjects.tasks.ALL,
ZohoProjects.users.READ
```

If your Zoho account is in a non-US data center, update:

- `ZOHO_ACCOUNTS_BASE_URL`
- `ZOHO_PROJECTS_API_BASE_URL`

Examples:

- India accounts: `https://accounts.zoho.in`
- EU accounts: `https://accounts.zoho.eu`

## Sample prompts

- `What projects do I have?`
- `Show tasks for the first one`
- `Create a task called API Integration in the first project`
- `Delete task #2 from the same project`
- `Who has the most tasks this month in Website Redesign?`

## Known limitations

- Natural-language parsing is intentionally lightweight and rule-driven for task mutation details, with optional OpenAI-assisted routing when `OPENAI_API_KEY` is provided.
- Zoho task status updates can vary by portal configuration; the implementation tries to resolve matching custom status IDs from visible project tasks and falls back to progress-based updates when needed.
- The current UI is single-threaded per browser session and optimized for the assignment demo rather than production-scale collaboration.
