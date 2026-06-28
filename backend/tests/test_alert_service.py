"""
tests.test_alert_service
------------------------
Unit tests for app/services/alert_service.py.

Uses monkeypatch to mock httpx.Client so no real Telegram messages are sent.
"""
from unittest.mock import MagicMock, patch
import pytest

from app.services.alert_service import AlertService


@pytest.fixture
def mock_httpx_post(monkeypatch):
    """Mock httpx.Client.post to always return success."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"ok":true}'

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr("app.services.alert_service.httpx.Client", lambda **kwargs: mock_client)
    return mock_client


@pytest.fixture
def enabled_service(monkeypatch):
    """AlertService with TELEGRAM_ENABLED=True."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_ENABLED", True)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "-1001234567890")
    monkeypatch.setattr(settings, "TELEGRAM_ALERT_ON_ENTRY", True)
    monkeypatch.setattr(settings, "TELEGRAM_ALERT_ON_EXIT", True)
    monkeypatch.setattr(settings, "TELEGRAM_ALERT_ON_ERROR", True)
    monkeypatch.setattr(settings, "TELEGRAM_ALERT_ON_CIRCUIT_BREAKER", True)
    return AlertService()


@pytest.fixture
def disabled_service(monkeypatch):
    """AlertService with TELEGRAM_ENABLED=False."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_ENABLED", False)
    return AlertService()


class TestAlertServiceInit:
    def test_disabled_by_default(self, disabled_service):
        assert disabled_service.enabled is False

    def test_enabled_when_configured(self, enabled_service):
        assert enabled_service.enabled is True
        assert enabled_service.token == "123:ABC"
        assert enabled_service.chat_id == "-1001234567890"


class TestDisabledAlerts:
    """When disabled, all send_* methods return False without calling Telegram."""

    def test_disabled_entry_alert(self, disabled_service):
        result = disabled_service.send_entry_alert(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=1000, stop_loss=950, take_profit=1300,
            strategy_slug="stock-counter-trend",
        )
        assert result is False

    def test_disabled_exit_alert(self, disabled_service):
        result = disabled_service.send_exit_alert(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=1000, exit_price=1050, pnl=500,
            exit_reason="target", strategy_slug="stock-counter-trend",
        )
        assert result is False

    def test_disabled_error_alert(self, disabled_service):
        assert disabled_service.send_error_alert("test error") is False

    def test_disabled_circuit_breaker_alert(self, disabled_service):
        assert disabled_service.send_circuit_breaker_alert(1, -60000, 50000) is False

    def test_disabled_test_alert(self, disabled_service):
        assert disabled_service.send_test_alert() is False


class TestEnabledAlerts:
    """When enabled, send_* methods call the Telegram API."""

    def test_entry_alert_sends_message(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_entry_alert(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=1000.50, stop_loss=950, take_profit=1300,
            strategy_slug="stock-counter-trend",
            paper_mode=True,
            broker_order_id="ORD-123",
            bar_score=2.5,
        )
        assert result is True
        mock_httpx_post.post.assert_called_once()
        # Verify the payload
        call_args = mock_httpx_post.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["chat_id"] == "-1001234567890"
        assert "PAPER ENTRY" in payload["text"]
        assert "RELIANCE" in payload["text"]
        assert "1000.50" in payload["text"]
        assert "ORD-123" in payload["text"]
        assert "2.50" in payload["text"]

    def test_exit_alert_with_profit(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_exit_alert(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=1000, exit_price=1050, pnl=500,
            exit_reason="target", strategy_slug="stock-counter-trend",
        )
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "EXIT" in payload["text"]
        assert "🟢" in payload["text"]  # green for profit
        assert "+500" in payload["text"]

    def test_exit_alert_with_loss(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_exit_alert(
            symbol="RELIANCE", side="BUY", quantity=10,
            entry_price=1000, exit_price=950, pnl=-500,
            exit_reason="stop_loss", strategy_slug="stock-counter-trend",
        )
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "🔴" in payload["text"]  # red for loss
        assert "-500" in payload["text"]

    def test_error_alert_includes_message(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_error_alert(
            error_message="Order rejected: insufficient funds",
            context="live_trading_loop",
            strategy_slug="stock-counter-trend",
        )
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "ERROR" in payload["text"]
        assert "insufficient funds" in payload["text"]
        assert "live_trading_loop" in payload["text"]

    def test_circuit_breaker_alert(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_circuit_breaker_alert(
            strategy_id=1, daily_loss=-60000, max_loss=50000,
        )
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "CIRCUIT BREAKER" in payload["text"]
        assert "60000" in payload["text"]
        assert "50000" in payload["text"]

    def test_startup_alert(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_startup_alert("stock-counter-trend", "RELIANCE", True)
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "TRADING STARTED" in payload["text"]
        assert "PAPER" in payload["text"]

    def test_stop_alert(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_stop_alert("stock-counter-trend", 1_050_000, square_off=True)
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "TRADING STOPPED" in payload["text"]
        assert "1050000" in payload["text"]
        assert "squared off" in payload["text"].lower()

    def test_test_alert(self, enabled_service, mock_httpx_post):
        result = enabled_service.send_test_alert()
        assert result is True
        payload = mock_httpx_post.post.call_args.kwargs["json"]
        assert "Telegram Alerts Working" in payload["text"]


class TestAlertFailureHandling:
    """Alerts should never raise — failures are logged and return False."""

    def test_api_error_returns_false(self, enabled_service, monkeypatch):
        """Telegram API returns non-200 → False."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"ok":false,"description":"Unauthorized"}'

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("app.services.alert_service.httpx.Client", lambda **kwargs: mock_client)

        result = enabled_service.send_test_alert()
        assert result is False

    def test_network_exception_returns_false(self, enabled_service, monkeypatch):
        """httpx raises exception → False, not propagated."""
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("Network timeout")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("app.services.alert_service.httpx.Client", lambda **kwargs: mock_client)

        result = enabled_service.send_test_alert()
        assert result is False  # should not raise
