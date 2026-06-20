from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sales Cockpit"
    environment: str = "local"
    db_path: Path = Path("data/sales_cockpit.db")
    storage_path: Path = Path("storage")
    seed_password: str = "ChangeMe!2026"
    twilio_mode: str = "mock"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_sender: str | None = None
    twilio_messaging_service_sid: str | None = None
    twilio_allowed_recipients: str | None = None
    twilio_validate_signature: bool = True
    twilio_webhook_url: str | None = None
    twilio_status_callback_url: str | None = None
    twilio_content_read_only: bool = True
    schooldrive_mcp_url: str | None = None
    schooldrive_webhook_token: str | None = None
    front_api_token: str | None = None
    front_import_query: str | None = None
    front_import_inbox_ids: str | None = None
    notion_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SALES_COCKPIT_",
        extra="ignore",
    )

    @property
    def root_dir(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def resolved_db_path(self) -> Path:
        return self.root_dir / self.db_path if not self.db_path.is_absolute() else self.db_path

    @property
    def resolved_storage_path(self) -> Path:
        return (
            self.root_dir / self.storage_path
            if not self.storage_path.is_absolute()
            else self.storage_path
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
