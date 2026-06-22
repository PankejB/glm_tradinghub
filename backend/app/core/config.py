"""
app.core.config
---------------
Centralized settings using pydantic-settings.
Reads from environment / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- DhanHQ broker ---
    DHAN_CLIENT_ID: str = "demo_client_id"
    DHAN_ACCESS_TOKEN: str = "demo_access_token"

    # --- Database ---
    DB_URL: str = "postgresql+psycopg2://trader:traderpass@localhost:5432/trading_db"

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- JWT / Auth ---
    JWT_SECRET: str = "dev_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # --- App ---
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # --- Trading defaults ---
    DEFAULT_CAPITAL: float = 1_000_000.0
    RISK_PER_TRADE_PCT: float = 1.0
    LIVE_LOOP_INTERVAL_SEC: int = 30
    MARKET_OPEN_IST: str = "09:15"
    MARKET_CLOSE_IST: str = "15:30"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Singleton-style import for modules that just need the values
settings = get_settings()
