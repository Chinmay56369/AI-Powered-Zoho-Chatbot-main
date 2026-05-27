from __future__ import annotations

from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from backend.app.core.dependencies import ensure_session_id, get_services


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    services = get_services(request)
    if not services.settings.zoho_client_id or not services.settings.zoho_client_secret:
        raise HTTPException(status_code=500, detail="Zoho OAuth is not configured.")

    state = str(uuid4())
    request.session["oauth_state"] = state
    ensure_session_id(request)
    return RedirectResponse(services.zoho_client.build_authorization_url(state))


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    location: str | None = None,
    accounts_server: str | None = Query(default=None, alias="accounts-server"),
):
    services = get_services(request)
    expected_state = request.session.get("oauth_state")
    if not code or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback payload.")

    try:
        user = await services.zoho_client.exchange_code_for_user(
            code,
            accounts_base_url=accounts_server,
            location=location,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Zoho returned {exc.response.status_code} during OAuth callback. "
                "Check your client credentials, redirect URI, and Zoho data-center domains."
            ),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    request.session["user_id"] = int(user["id"])
    ensure_session_id(request)
    request.session.pop("oauth_state", None)
    return RedirectResponse(services.settings.frontend_origin)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"success": True}
