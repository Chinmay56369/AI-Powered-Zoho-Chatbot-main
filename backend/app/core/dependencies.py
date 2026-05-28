from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, Request


def get_services(request: Request):
    return request.app.state.services


def get_current_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return int(user_id)


def ensure_session_id(request: Request) -> str:
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid4())
        request.session["session_id"] = session_id
    return str(session_id)

