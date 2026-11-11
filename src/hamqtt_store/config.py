import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://hamqtt:hamqtt-local-development-password@localhost:5432/hamqtt_store")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    secret_key: str = os.getenv("SECRET_KEY", "change-this-development-secret")
    app_data_dir: str = os.getenv("APP_DATA_DIR", "data")
    session_days: int = int(os.getenv("SESSION_DAYS", "365"))
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    mqtt_poll_seconds: int = int(os.getenv("MQTT_POLL_SECONDS", "10"))
    ha_poll_seconds: int = int(os.getenv("HA_POLL_SECONDS", "10"))
    updater_url: str = os.getenv("UPDATER_URL", "http://updater:8100")
    updater_token: str = os.getenv("UPDATER_TOKEN", "")
    update_repository: str = os.getenv("UPDATE_REPOSITORY", "jasakuva/JASA_HAMQTT_STORAGE")
    update_include_prereleases: bool = os.getenv("UPDATE_INCLUDE_PRERELEASES", "false").lower() in {"1", "true", "yes"}
    hamqtt_engine: str = os.getenv("HAMQTT_ENGINE", "podman")
    hamqtt_version: str = os.getenv("HAMQTT_VERSION", "dev")

settings = Settings()
