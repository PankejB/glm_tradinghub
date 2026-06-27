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

    # --- Live trading safety rails ---
    # MASTER KILL SWITCH. Must be True for ANY real order to be placed.
    # If False, the system forces paper_mode regardless of API request.
    LIVE_TRADING_ENABLED: bool = False
    # Per-segment DhanHQ product types:
    #   NSE_EQ  → CNC (delivery) or INTRADAY (MIS)
    #   NSE_FNO → INTRADAY (MIS) for options/futures
    #   MCX     → INTRADAY (MIS) for commodities
    ORDER_PRODUCT_TYPE_EQ: str = "CNC"        # CNC = delivery, INTRADAY = MIS
    ORDER_PRODUCT_TYPE_FNO: str = "INTRADAY"
    ORDER_PRODUCT_TYPE_MCX: str = "INTRADAY"
    # Default order type for entries (MARKET = immediate fill, LIMIT = price-controlled)
    ORDER_TYPE_DEFAULT: str = "MARKET"
    # Circuit breaker: stop the live loop if daily loss exceeds this ₹ amount
    MAX_DAILY_LOSS_INR: float = 50_000.0
    # Retry config for transient broker failures
    ORDER_RETRY_ATTEMPTS: int = 3
    ORDER_RETRY_DELAY_SEC: float = 2.0

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
