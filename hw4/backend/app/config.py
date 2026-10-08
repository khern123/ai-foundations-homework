"""Application settings loaded from environment variables.

Values come from the process environment, falling back to the project-root
.env file (hw4/.env). Secrets are never hardcoded here.
"""

import os
import secrets
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _portkey_key() -> str | None:
    """PORTKEY_API_KEY from the environment / hw4/.env, else from the nearest parent .env
    (the shared AI Foundations .env). Read into memory only; never logged or returned."""
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if key:
        return key
    for parent in PROJECT_ROOT.parents:
        env_file = parent / ".env"
        if env_file.is_file():
            key = (dotenv_values(env_file).get("PORTKEY_API_KEY") or "").strip()
            if key:
                return key
    return None


class Settings:
    app_name: str = "Campus Customs API"
    app_env: str = os.getenv("APP_ENV", "development")
    cors_origins: list[str] = _split_csv(
        os.getenv("CORS_ORIGINS", "http://localhost:5173")
    )
    # Optional override so tests can point the API at a throwaway copy of the database.
    database_path: Path = Path(
        os.getenv("DATABASE_PATH") or PROJECT_ROOT / "backend" / "data" / "campus_customs.db"
    )
    # Chat agent: OpenAI via the Portkey gateway. The key stays server-side.
    portkey_api_key: str | None = _portkey_key()
    portkey_base_url: str = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
    chat_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    # Signs session tokens. Set SESSION_SECRET in hw4/.env so logins survive restarts; otherwise a
    # random per-process secret is used (everyone is signed out when the server restarts).
    session_secret: str = os.getenv("SESSION_SECRET", "").strip() or secrets.token_hex(32)

    def __repr__(self) -> str:  # never print the key, even by accident
        return f"Settings(app_env={self.app_env!r}, chat_model={self.chat_model!r}, portkey_api_key=***, session_secret=***)"


settings = Settings()
