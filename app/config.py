from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Watershed Operations"
    secret_key: str = "development-secret-key"
    database_url: str = "sqlite:///./data/watershed_operations.db"
    default_admin_email: str = "admin@example.org"
    default_admin_password: str = "ChangeMe123!"
    calendar_ics_url: str = ""
    session_cookie_name: str = "watershed_session"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @computed_field
    @property
    def database_path(self) -> Path:
        if self.database_url.startswith("sqlite:///./"):
            return Path(self.database_url.replace("sqlite:///./", "", 1))
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.replace("sqlite:///", "/", 1))
        return Path("data/watershed_operations.db")


@lru_cache
def get_settings() -> Settings:
    return Settings()
