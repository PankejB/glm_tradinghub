"""
app.services.alert_service
--------------------------
Sends Telegram alerts for trade events (entry, exit, error, circuit breaker).

Uses the Telegram Bot API directly via httpx (no extra SDK needed).
Messages are formatted with Markdown for rich display.

Setup:
1. Create a bot via @BotFather on Telegram → get TELEGRAM_BOT_TOKEN
2. Create a channel/group, add the bot → get TELEGRAM_CHAT_ID
   (Invite @userinfobot to the channel to get the chat ID)
3. Set TELEGRAM_ENABLED=true + the token + chat_id in backend/.env
4. Test with: GET /api/alerts/test

All send_* methods are non-blocking failures — if Telegram is down, the
trading loop continues. Errors are logged but never raised.
"""
from __future__ import annotations

import httpx
from datetime import datetime
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.core.config import settings


TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class AlertService:
    """Sends Telegram alerts for trade events."""

    def __init__(self) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = (
            settings.TELEGRAM_ENABLED
            and bool(self.token)
            and bool(self.chat_id)
        )
        if self.enabled:
            logger.info("📱 Telegram alerts ENABLED (chat_id={})", self.chat_id)
        else:
            logger.debug("Telegram alerts disabled (TELEGRAM_ENABLED=false or missing token/chat_id)")

    # ------------------------------------------------------------------
    #  Core send method
    # ------------------------------------------------------------------

    @retry(
        reraise=False,
        stop=stop_after_attempt(2),
        wait=wait_fixed(1.0),
        retry=retry_if_exception_type(httpx.HTTPError),
    )
    def _send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to Telegram. Returns True on success, False on failure."""
        if not self.enabled:
            return False

        url = TELEGRAM_API_BASE.format(token=self.token, method="sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning(
                        "Telegram API returned {}: {}",
                        resp.status_code, resp.text[:200],
                    )
                    return False
                return True
        except Exception as exc:
            logger.warning("Telegram send failed: {}", exc)
            return False

    # ------------------------------------------------------------------
    #  Trade event alerts
    # ------------------------------------------------------------------

    def send_entry_alert(
        self,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_loss: float | None,
        take_profit: float | None,
        strategy_slug: str,
        paper_mode: bool = True,
        broker_order_id: str | None = None,
        bar_score: float | None = None,
    ) -> bool:
        """Alert on trade entry."""
        if not settings.TELEGRAM_ALERT_ON_ENTRY:
            return False

        mode_emoji = "📝" if paper_mode else "⚠️"
        mode_text = "PAPER" if paper_mode else "LIVE"

        lines = [
            f"{mode_emoji} *{mode_text} ENTRY: {side} {symbol}*",
            f"Strategy: `{strategy_slug}`",
            f"Qty: `{quantity}` @ ₹`{entry_price:.2f}`",
        ]
        if stop_loss is not None:
            lines.append(f"Stop Loss: ₹`{stop_loss:.2f}`")
        if take_profit is not None:
            lines.append(f"Take Profit: ₹`{take_profit:.2f}`")
        if broker_order_id:
            lines.append(f"Order ID: `{broker_order_id}`")
        if bar_score is not None:
            lines.append(f"Bar Score: `{bar_score:.2f}`")
        lines.append(f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        return self._send_message("\n".join(lines))

    def send_exit_alert(
        self,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        exit_price: float,
        pnl: float,
        exit_reason: str,
        strategy_slug: str,
        paper_mode: bool = True,
        broker_order_id: str | None = None,
    ) -> bool:
        """Alert on trade exit."""
        if not settings.TELEGRAM_ALERT_ON_EXIT:
            return False

        mode_emoji = "📝" if paper_mode else "⚠️"
        mode_text = "PAPER" if paper_mode else "LIVE"
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        pnl_sign = "+" if pnl >= 0 else ""

        lines = [
            f"{mode_emoji} *{mode_text} EXIT: {side} {symbol}*",
            f"Strategy: `{strategy_slug}`",
            f"Entry: ₹`{entry_price:.2f}` → Exit: ₹`{exit_price:.2f}`",
            f"Qty: `{quantity}`",
            f"{pnl_emoji} PnL: ₹`{pnl_sign}{pnl:.2f}`",
            f"Reason: `{exit_reason}`",
        ]
        if broker_order_id:
            lines.append(f"Order ID: `{broker_order_id}`")
        lines.append(f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        return self._send_message("\n".join(lines))

    def send_error_alert(
        self,
        error_message: str,
        context: str = "",
        strategy_slug: str = "",
    ) -> bool:
        """Alert on system error."""
        if not settings.TELEGRAM_ALERT_ON_ERROR:
            return False

        lines = [
            "🚨 *ERROR*",
        ]
        if strategy_slug:
            lines.append(f"Strategy: `{strategy_slug}`")
        if context:
            lines.append(f"Context: `{context}`")
        lines.append(f"```\n{error_message[:500]}\n```")
        lines.append(f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        return self._send_message("\n".join(lines))

    def send_circuit_breaker_alert(
        self,
        strategy_id: int,
        daily_loss: float,
        max_loss: float,
    ) -> bool:
        """Alert when circuit breaker trips."""
        if not settings.TELEGRAM_ALERT_ON_CIRCUIT_BREAKER:
            return False

        lines = [
            "🚨 *CIRCUIT BREAKER TRIPPED*",
            f"Strategy ID: `{strategy_id}`",
            f"Daily Loss: ₹`{abs(daily_loss):.2f}`",
            f"Limit: ₹`{max_loss:.2f}`",
            "Live trading loop has been *stopped automatically*.",
            f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        return self._send_message("\n".join(lines))

    def send_startup_alert(
        self,
        strategy_slug: str,
        symbol: str,
        paper_mode: bool,
    ) -> bool:
        """Alert when live trading loop starts."""
        mode_emoji = "📝" if paper_mode else "⚠️"
        mode_text = "PAPER" if paper_mode else "LIVE"
        lines = [
            f"{mode_emoji} *{mode_text} TRADING STARTED*",
            f"Strategy: `{strategy_slug}`",
            f"Symbol: `{symbol}`",
            f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        return self._send_message("\n".join(lines))

    def send_stop_alert(
        self,
        strategy_slug: str,
        final_equity: float,
        square_off: bool = False,
    ) -> bool:
        """Alert when live trading loop stops."""
        lines = [
            "⏹️ *TRADING STOPPED*",
            f"Strategy: `{strategy_slug}`",
            f"Final Equity: ₹`{final_equity:.2f}`",
        ]
        if square_off:
            lines.append("⚠️ All positions squared off")
        lines.append(f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return self._send_message("\n".join(lines))

    # ------------------------------------------------------------------
    #  Test alert
    # ------------------------------------------------------------------

    def send_test_alert(self) -> bool:
        """Send a test message to verify Telegram config."""
        lines = [
            "✅ *Telegram Alerts Working*",
            "Your algo trading system will now send alerts for:",
            "• Trade entries 📈",
            "• Trade exits 📊",
            "• Errors 🚨",
            "• Circuit breaker trips ⛔",
            f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        return self._send_message("\n".join(lines))


# ---------------------------------------------------------------------
#  Singleton accessor
# ---------------------------------------------------------------------

_alert_service: AlertService | None = None


def get_alert_service() -> AlertService:
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService()
    return _alert_service
