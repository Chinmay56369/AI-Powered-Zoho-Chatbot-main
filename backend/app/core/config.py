from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = "Zoho Project Assistant"
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    backend_base_url: str = Field(default="http://localhost:8000", alias="BACKEND_BASE_URL")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    database_path: str = Field(default="./zoho_assistant.db", alias="DATABASE_PATH")

    zoho_client_id: str = Field(default="", alias="ZOHO_CLIENT_ID")
    zoho_client_secret: str = Field(default="", alias="ZOHO_CLIENT_SECRET")
    zoho_redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
        alias="ZOHO_REDIRECT_URI",
    )
    zoho_accounts_base_url: str = Field(
        default="https://accounts.zoho.com",
        alias="ZOHO_ACCOUNTS_BASE_URL",
    )
    zoho_projects_api_base_url: str = Field(
        default="https://projectsapi.zoho.com",
        alias="ZOHO_PROJECTS_API_BASE_URL",
    )
    zoho_portal_id: str | None = Field(default=None, alias="ZOHO_PORTAL_ID")
    zoho_scopes: str = Field(
        default=(
            "ZohoProjects.portals.READ,"
            "ZohoProjects.projects.READ,"
            "ZohoProjects.tasks.ALL,"
            "ZohoProjects.users.READ"
        ),
        alias="ZOHO_SCOPES",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_path(self) -> Path:
        path = Path(self.database_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @property
    def resolved_zoho_accounts_base_url(self) -> str:
        return self.zoho_accounts_base_url.rstrip("/")

    @property
    def resolved_zoho_projects_api_base_url(self) -> str:
        configured = self.zoho_projects_api_base_url.rstrip("/")
        accounts_suffix = _extract_zoho_suffix(self.resolved_zoho_accounts_base_url)
        projects_suffix = _extract_zoho_suffix(configured)

        # Zoho Projects uses product-specific regional domains such as
        # projectsapi.zoho.in, which do not match the generic OAuth api_domain.
        if configured == "https://projectsapi.zoho.com" and accounts_suffix != ".com":
            return f"https://projectsapi.zoho{accounts_suffix}"

        if accounts_suffix != projects_suffix:
            return f"https://projectsapi.zoho{accounts_suffix}"

        return configured


def _extract_zoho_suffix(url: str) -> str:
    host = urlparse(url).hostname or ""
    marker = "zoho"
    if marker not in host:
        return ".com"
    return host.split(marker, maxsplit=1)[1] or ".com"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
