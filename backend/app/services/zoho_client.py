from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.app.core.config import Settings
from backend.app.core.database import Database


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: str
    accounts_base_url: str
    api_base_url: str
    scope: str


class ZohoClient:
    def __init__(self, settings: Settings, database: Database, http_client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.database = database
        self.http_client = http_client

    def build_authorization_url(self, state: str) -> str:
        params = urlencode(
            {
                "scope": self.settings.zoho_scopes,
                "client_id": self.settings.zoho_client_id,
                "response_type": "code",
                "access_type": "offline",
                "redirect_uri": self.settings.zoho_redirect_uri,
                "state": state,
                "prompt": "consent",
            }
        )
        return f"{self.settings.resolved_zoho_accounts_base_url}/oauth/v2/auth?{params}"

    async def exchange_code_for_user(
        self,
        code: str,
        accounts_base_url: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        resolved_accounts_base_url = (accounts_base_url or self.settings.resolved_zoho_accounts_base_url).rstrip("/")
        resolved_projects_api_base_url = self._resolve_projects_api_base_url(location)
        response = await self.http_client.post(
            f"{resolved_accounts_base_url}/oauth/v2/token",
            data={
                "code": code,
                "client_id": self.settings.zoho_client_id,
                "client_secret": self.settings.zoho_client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.settings.zoho_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data = self._parse_json_response(response, "token exchange")
        if "access_token" not in token_data:
            error_code = token_data.get("error") or token_data.get("error_code") or "unknown_error"
            description = token_data.get("error_description") or token_data.get("message") or str(token_data)
            raise RuntimeError(
                "Zoho token exchange did not return an access token. "
                f"Error: {error_code}. Details: {description}. "
                "If you refreshed the callback URL, generate a new login because Zoho auth codes are single-use."
            )

        bundle = TokenBundle(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            expires_at=(
                datetime.now(tz=UTC)
                + timedelta(seconds=self._extract_expiry_seconds(token_data))
            ).isoformat(),
            accounts_base_url=resolved_accounts_base_url,
            api_base_url=resolved_projects_api_base_url,
            scope=token_data.get("scope", self.settings.zoho_scopes),
        )

        try:
            portal_data = await self._fetch_portals(bundle.access_token, bundle.api_base_url)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "Zoho OAuth succeeded, but fetching Projects portals failed from "
                f"{bundle.api_base_url}/restapi/portals/ with status {exc.response.status_code}. "
                "Check ZOHO_PROJECTS_API_BASE_URL for your Zoho data center."
            ) from exc
        portal = self._choose_portal(portal_data)
        login_id = str(portal_data.get("login_id", portal.get("owner", portal["id"])))
        display_name = portal.get("name") or portal.get("portal_name") or f"Zoho User {login_id}"

        existing = await self.database.fetch_one(
            "SELECT id FROM users WHERE zoho_login_id = ?",
            (login_id,),
        )
        if existing is None:
            cursor = await self.database.execute(
                """
                INSERT INTO users (zoho_login_id, display_name, email, portal_id, portal_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    login_id,
                    display_name,
                    portal.get("email"),
                    str(portal["id"]),
                    portal.get("name") or portal.get("portal_name") or str(portal["id"]),
                ),
            )
            user_id = int(cursor.lastrowid)
        else:
            user_id = int(existing["id"])
            await self.database.execute(
                """
                UPDATE users
                SET display_name = ?, email = ?, portal_id = ?, portal_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    display_name,
                    portal.get("email"),
                    str(portal["id"]),
                    portal.get("name") or portal.get("portal_name") or str(portal["id"]),
                    user_id,
                ),
            )

        await self._save_tokens(user_id, bundle)
        user_row = await self.database.fetch_one(
            "SELECT id, display_name, email, portal_id, portal_name FROM users WHERE id = ?",
            (user_id,),
        )
        return dict(user_row)

    async def ensure_fresh_token(self, user_id: int) -> str:
        token_row = await self.database.fetch_one(
            """
            SELECT access_token, refresh_token, expires_at, accounts_base_url, api_base_url, scope
            FROM oauth_tokens
            WHERE user_id = ?
            """,
            (user_id,),
        )
        if token_row is None:
            raise RuntimeError("User is not authenticated with Zoho.")

        expires_at = datetime.fromisoformat(token_row["expires_at"])
        if expires_at <= datetime.now(tz=UTC) + timedelta(minutes=2):
            token_row = await self._refresh_token(user_id, dict(token_row))
        return str(token_row["access_token"])

    async def get_user_portal(self, user_id: int) -> dict[str, str]:
        row = await self.database.fetch_one(
            "SELECT portal_id, portal_name FROM users WHERE id = ?",
            (user_id,),
        )
        if row is None:
            raise RuntimeError("Authenticated user record not found.")
        return {"portal_id": row["portal_id"], "portal_name": row["portal_name"]}

    async def list_projects(self, user_id: int) -> dict[str, Any]:
        portal = await self.get_user_portal(user_id)
        return await self._request_json(user_id, "GET", f"/restapi/portal/{portal['portal_id']}/projects/")

    async def list_tasks(self, user_id: int, project_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        portal = await self.get_user_portal(user_id)
        return await self._request_json(
            user_id,
            "GET",
            f"/restapi/portal/{portal['portal_id']}/projects/{project_id}/tasks/",
            params=params or {},
        )

    async def get_task_details(self, user_id: int, project_id: str, task_id: str) -> dict[str, Any]:
        portal = await self.get_user_portal(user_id)
        return await self._request_json(
            user_id,
            "GET",
            f"/restapi/portal/{portal['portal_id']}/projects/{project_id}/tasks/{task_id}/",
        )

    async def create_task(self, user_id: int, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        portal = await self.get_user_portal(user_id)
        return await self._request_json(
            user_id,
            "POST",
            f"/restapi/portal/{portal['portal_id']}/projects/{project_id}/tasks/",
            data=data,
        )

    async def update_task(
        self,
        user_id: int,
        project_id: str,
        task_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        portal = await self.get_user_portal(user_id)
        return await self._request_json(
            user_id,
            "POST",
            f"/restapi/portal/{portal['portal_id']}/projects/{project_id}/tasks/{task_id}/",
            data=data,
        )

    async def delete_task(self, user_id: int, project_id: str, task_id: str) -> None:
        portal = await self.get_user_portal(user_id)
        await self._request_json(
            user_id,
            "DELETE",
            f"/restapi/portal/{portal['portal_id']}/projects/{project_id}/tasks/{task_id}/",
        )

    async def list_project_members(self, user_id: int, project_id: str) -> dict[str, Any]:
        portal = await self.get_user_portal(user_id)
        return await self._request_json(
            user_id,
            "GET",
            f"/restapi/portal/{portal['portal_id']}/projects/{project_id}/users/",
            params={"user_type": "all"},
        )

    async def _request_json(
        self,
        user_id: int,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self.ensure_fresh_token(user_id)
        token_row = await self.database.fetch_one(
            "SELECT api_base_url FROM oauth_tokens WHERE user_id = ?",
            (user_id,),
        )
        api_base_url = (
            token_row["api_base_url"]
            if token_row
            else self.settings.resolved_zoho_projects_api_base_url
        )
        response = await self.http_client.request(
            method,
            f"{api_base_url}{path}",
            params=params,
            data=data,
            headers=self._projects_headers(token),
        )
        if response.status_code == 401:
            await self._refresh_token_from_db(user_id)
            refreshed = await self.ensure_fresh_token(user_id)
            response = await self.http_client.request(
                method,
                f"{api_base_url}{path}",
                params=params,
                data=data,
                headers=self._projects_headers(refreshed),
            )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return self._parse_json_response(response, f"{method} {path}")

    async def _refresh_token(self, user_id: int, token_row: dict[str, Any]) -> dict[str, Any]:
        response = await self.http_client.post(
            f"{token_row['accounts_base_url']}/oauth/v2/token",
            data={
                "refresh_token": token_row["refresh_token"],
                "client_id": self.settings.zoho_client_id,
                "client_secret": self.settings.zoho_client_secret,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        refreshed = response.json()
        bundle = TokenBundle(
            access_token=refreshed["access_token"],
            refresh_token=token_row["refresh_token"],
            expires_at=(
                datetime.now(tz=UTC)
                + timedelta(seconds=self._extract_expiry_seconds(refreshed))
            ).isoformat(),
            accounts_base_url=token_row["accounts_base_url"],
            api_base_url=token_row["api_base_url"] or self.settings.resolved_zoho_projects_api_base_url,
            scope=refreshed.get("scope", token_row["scope"]),
        )
        await self._save_tokens(user_id, bundle)
        token_row.update(
            {
                "access_token": bundle.access_token,
                "refresh_token": bundle.refresh_token,
                "expires_at": bundle.expires_at,
                "api_base_url": bundle.api_base_url,
                "scope": bundle.scope,
            }
        )
        return token_row

    async def _refresh_token_from_db(self, user_id: int) -> None:
        token_row = await self.database.fetch_one(
            """
            SELECT access_token, refresh_token, expires_at, accounts_base_url, api_base_url, scope
            FROM oauth_tokens
            WHERE user_id = ?
            """,
            (user_id,),
        )
        if token_row is None:
            raise RuntimeError("Cannot refresh token for a user that is not authenticated.")
        await self._refresh_token(user_id, dict(token_row))

    async def _fetch_portals(self, access_token: str, api_base_url: str) -> dict[str, Any]:
        response = await self.http_client.get(
            f"{api_base_url}/restapi/portals/",
            headers=self._projects_headers(access_token),
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            raise RuntimeError(
                "Zoho OAuth succeeded, but this account did not return any Zoho Projects portals. "
                "Make sure the same Zoho user has access to Zoho Projects and is part of at least one portal."
            )
        return self._parse_json_response(response, "fetch portals")

    def _choose_portal(self, portal_data: dict[str, Any]) -> dict[str, Any]:
        portals = portal_data.get("portals") or []
        if not portals:
            raise RuntimeError("No Zoho Projects portals are available for this user.")

        if self.settings.zoho_portal_id:
            for portal in portals:
                portal_id = str(portal.get("id") or portal.get("zsoid"))
                if portal_id == self.settings.zoho_portal_id:
                    return {"id": portal_id, **portal}

        first = portals[0]
        return {"id": str(first.get("id") or first.get("zsoid")), **first}

    async def _save_tokens(self, user_id: int, bundle: TokenBundle) -> None:
        await self.database.execute(
            """
            INSERT INTO oauth_tokens (user_id, access_token, refresh_token, expires_at, accounts_base_url, api_base_url, scope)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                accounts_base_url = excluded.accounts_base_url,
                api_base_url = excluded.api_base_url,
                scope = excluded.scope
            """,
            (
                user_id,
                bundle.access_token,
                bundle.refresh_token,
                bundle.expires_at,
                bundle.accounts_base_url,
                bundle.api_base_url,
                bundle.scope,
            ),
        )

    def _resolve_projects_api_base_url(self, location: str | None) -> str:
        if location:
            normalized = location.strip().lower()
            mapping = {
                "com": "https://projectsapi.zoho.com",
                "in": "https://projectsapi.zoho.in",
                "eu": "https://projectsapi.zoho.eu",
                "com.au": "https://projectsapi.zoho.com.au",
                "jp": "https://projectsapi.zoho.jp",
                "com.cn": "https://projectsapi.zoho.com.cn",
            }
            if normalized in mapping:
                return mapping[normalized]
        return self.settings.resolved_zoho_projects_api_base_url

    @staticmethod
    def _projects_headers(access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Accept": "application/json",
        }

    @staticmethod
    def _extract_expiry_seconds(token_data: dict[str, Any]) -> int:
        if token_data.get("expires_in_sec") is not None:
            return int(token_data["expires_in_sec"])
        expires_in = int(token_data.get("expires_in", 3600))
        if expires_in > 86400:
            return expires_in // 1000
        return expires_in

    @staticmethod
    def _parse_json_response(response: httpx.Response, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            snippet = response.text.strip().replace("\n", " ")[:240]
            content_type = response.headers.get("content-type", "unknown")
            raise RuntimeError(
                f"Zoho returned a non-JSON response during {context}. "
                f"Status: {response.status_code}. Content-Type: {content_type}. "
                f"Body preview: {snippet or '<empty>'}"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Zoho returned an unexpected payload during {context}: {type(payload).__name__}"
            )
        return payload
