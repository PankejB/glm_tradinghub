"""
app.api.alerts
--------------
GET  /api/alerts/status  — is Telegram configured?
POST /api/alerts/test    — send a test message
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import get_current_user
from app.services.alert_service import get_alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/status")
def alerts_status(_=Depends(get_current_user)):
    """Returns whether Telegram alerts are configured + enabled."""
    return {
        "enabled": settings.TELEGRAM_ENABLED,
        "token_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "chat_id_configured": bool(settings.TELEGRAM_CHAT_ID),
        "chat_id": settings.TELEGRAM_CHAT_ID if settings.TELEGRAM_CHAT_ID else None,
        "alert_settings": {
            "on_entry": settings.TELEGRAM_ALERT_ON_ENTRY,
            "on_exit": settings.TELEGRAM_ALERT_ON_EXIT,
            "on_error": settings.TELEGRAM_ALERT_ON_ERROR,
            "on_circuit_breaker": settings.TELEGRAM_ALERT_ON_CIRCUIT_BREAKER,
        },
        "warning": (
            "✅ Telegram alerts are ENABLED."
            if settings.TELEGRAM_ENABLED
            else "Telegram alerts are DISABLED. Set TELEGRAM_ENABLED=true + TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in backend/.env to enable."
        ),
    }


class TestAlertRequest(BaseModel):
    message: str | None = None


@router.post("/test")
def send_test_alert(
    payload: TestAlertRequest | None = None,
    _=Depends(get_current_user),
):
    """Send a test Telegram message to verify configuration."""
    if not settings.TELEGRAM_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Telegram alerts are disabled. Set TELEGRAM_ENABLED=true in backend/.env first.",
        )
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set in backend/.env",
        )

    service = get_alert_service()
    success = service.send_test_alert()
    if not success:
        raise HTTPException(
            status_code=502,
            detail="Failed to send Telegram message. Check that the bot token + chat ID are correct, and the bot is a member of the channel.",
        )
    return {
        "status": "sent",
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "message": "✅ Test alert sent to Telegram. Check your channel/DM.",
    }
