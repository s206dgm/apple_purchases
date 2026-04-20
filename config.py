from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    google_client_id: str
    google_client_secret: str
    anthropic_api_key: str
    gmail_account: str                          # e.g. "rykai.labs@gmail.com"
    att_phone: str = ""                         # 10-digit, no dashes (legacy, unused)
    ntfy_topic: str = ""                        # e.g. "chris-apple-9x3k"
    portal_db_path: str = str(BASE_DIR.parent / "portal" / "backend" / "data" / "rykai.db")
    db_path: str = str(BASE_DIR / "data" / "apple.db")

    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
