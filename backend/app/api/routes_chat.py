from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.core.dependencies import ensure_session_id, get_current_user_id, get_services
from backend.app.schemas.chat import ChatRequest, ChatResponse, MeResponse, PendingActionPreview

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

MEMORY_CONTROL_MESSAGES = {"confirm", "cancel", "yes", "no", "approve", "stop"}


@router.get("/health")
@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/me", response_model=MeResponse)
async def me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return MeResponse(authenticated=False, login_url="/auth/login")

    services = get_services(request)
    user = await services.database.fetch_one(
        "SELECT id, display_name, email, portal_id, portal_name FROM users WHERE id = ?",
        (int(user_id),),
    )
    if user is None:
        request.session.clear()
        return MeResponse(authenticated=False, login_url="/auth/login")

    return MeResponse(
        authenticated=True,
        user={
            "id": int(user["id"]),
            "display_name": user["display_name"],
            "email": user["email"],
            "portal_id": user["portal_id"],
            "portal_name": user["portal_name"],
        },
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user_id: int = Depends(get_current_user_id),
):
    services = get_services(request)
    session_id = ensure_session_id(request)

    await services.memory_store.ensure_session(session_id, user_id)
    await services.memory_store.save_message(session_id, "user", payload.message)
    if payload.message.strip().lower() not in MEMORY_CONTROL_MESSAGES:
        await services.memory_store.remember_query(user_id, payload.message)
    try:
        result = await services.assistant_graph.run(
            user_id=user_id,
            session_id=session_id,
            message=payload.message,
        )
        await services.memory_store.save_message(session_id, "assistant", result["reply"])
    except Exception as exc:
        logger.exception("Chat execution failed for user %s in session %s", user_id, session_id)
        detail = str(exc).strip() or "Chat execution failed."
        raise HTTPException(status_code=500, detail=detail) from exc

    pending_action = result.get("pending_action")
    return ChatResponse(
        reply=result["reply"],
        route=result["route"],
        pending_action=PendingActionPreview(**pending_action) if pending_action else None,
        active_project_name=result.get("active_project_name"),
        used_tools=result.get("used_tools", []),
    )