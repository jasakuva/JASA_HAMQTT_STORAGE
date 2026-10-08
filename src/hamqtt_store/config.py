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
    mqtt_poll_seconds: int = int(os.getenv("MQTT_POLL_SECONDS", "10"))
    ha_poll_seconds: int = int(os.getenv("HA_POLL_SECONDS", "10"))

settings = Settings()
