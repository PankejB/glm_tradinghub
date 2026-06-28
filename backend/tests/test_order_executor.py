"""
tests.test_order_executor
-------------------------
Unit tests for app/services/order_executor.py.

Uses a mocked DhanHQ client — no real API calls are made.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.order_executor import (
    OrderExecutor, OrderExecutionError, LiveTradingDisabledError,
)


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def mock_dhan_service():
    """Returns a DhanService with a mocked dhanhq client."""
    mock = MagicMock()
    mock.dhan = MagicMock()
    return mock


@pytest.fixture
def executor_with_live_enabled(mock_dhan_service, monkeypatch):
    """OrderExecutor with LIVE_TRADING_ENABLED=True (simulated)."""
    # Patch settings.LIVE_TRADING_ENABLED to True
    from app.core.config import settings
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "ORDER_PRODUCT_TYPE_EQ", "CNC")
    monkeypatch.setattr(settings, "ORDER_PRODUCT_TYPE_FNO", "INTRADAY")
    monkeypatch.setattr(settings, "ORDER_PRODUCT_TYPE_MCX", "INTRADAY")
    monkeypatch.setattr(settings, "ORDER_TYPE_DEFAULT", "MARKET")
    monkeypatch.setattr(settings, "ORDER_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "ORDER_RETRY_DELAY_SEC", 0.01)
    return OrderExecutor(dhan_service=mock_dhan_service)


@pytest.fixture
def executor_with_live_disabled(mock_dhan_service, monkeypatch):
    """OrderExecutor with LIVE_TRADING_ENABLED=False."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False)
    return OrderExecutor(dhan_service=mock_dhan_service)


# ============================================================
#  Kill switch (LIVE_TRADING_ENABLED)
# ============================================================

class TestLiveTradingKillSwitch:
    def test_disabled_raises_on_market_order(self, executor_with_live_disabled):
        with pytest.raises(LiveTradingDisabledError, match="LIVE_TRADING_ENABLED=False"):
            executor_with_live_disabled.place_market_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="BUY", quantity=10,
            )

    def test_disabled_raises_on_limit_order(self, executor_with_live_disabled):
        with pytest.raises(LiveTradingDisabledError):
            executor_with_live_disabled.place_limit_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="BUY", quantity=10, price=1000.0,
            )

    def test_disabled_raises_on_cancel(self, executor_with_live_disabled):
        with pytest.raises(LiveTradingDisabledError):
            executor_with_live_disabled.cancel_order("12345")

    def test_disabled_raises_on_status_check(self, executor_with_live_disabled):
        with pytest.raises(LiveTradingDisabledError):
            executor_with_live_disabled.get_order_status("12345")


# ============================================================
#  Market order placement
# ============================================================

class TestPlaceMarketOrder:
    def test_successful_market_order(self, executor_with_live_enabled, mock_dhan_service):
        # Arrange: dhanhq returns success with orderId
        mock_dhan_service.dhan.place_order.return_value = {
            "status": "success",
            "orderId": "ORD-12345",
        }
        # Act
        resp = executor_with_live_enabled.place_market_order(
            security_id="2885", segment="NSE_EQ",
            transaction_type="BUY", quantity=10,
        )
        # Assert
        assert resp["status"] == "success"
        assert resp["orderId"] == "ORD-12345"
        # Verify dhanhq was called with correct params
        mock_dhan_service.dhan.place_order.assert_called_once()
        call_kwargs = mock_dhan_service.dhan.place_order.call_args.kwargs
        assert call_kwargs["securityId"] == "2885"
        assert call_kwargs["exchangeSegment"] == "NSE_EQ"
        assert call_kwargs["transactionType"] == "BUY"
        assert call_kwargs["quantity"] == 10
        assert call_kwargs["orderType"] == "MARKET"
        assert call_kwargs["productType"] == "CNC"  # NSE_EQ default

    def test_market_order_uses_correct_product_type_per_segment(
        self, executor_with_live_enabled, mock_dhan_service,
    ):
        mock_dhan_service.dhan.place_order.return_value = {"status": "success", "orderId": "X"}
        # NSE_FNO
        executor_with_live_enabled.place_market_order(
            security_id="13", segment="NSE_FNO",
            transaction_type="BUY", quantity=75,
        )
        assert mock_dhan_service.dhan.place_order.call_args.kwargs["productType"] == "INTRADAY"
        assert mock_dhan_service.dhan.place_order.call_args.kwargs["exchangeSegment"] == "NSE_FNO"

        # MCX
        executor_with_live_enabled.place_market_order(
            security_id="466583", segment="MCX",
            transaction_type="BUY", quantity=1,
        )
        assert mock_dhan_service.dhan.place_order.call_args.kwargs["productType"] == "INTRADAY"
        assert mock_dhan_service.dhan.place_order.call_args.kwargs["exchangeSegment"] == "MCX_COMM"

    def test_market_order_rejected_by_broker(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.place_order.return_value = {
            "status": "failure",
            "remarks": "Insufficient funds",
        }
        with pytest.raises(OrderExecutionError, match="DhanHQ order rejected"):
            executor_with_live_enabled.place_market_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="BUY", quantity=999999,
            )

    def test_market_order_invalid_segment(self, executor_with_live_enabled):
        with pytest.raises(OrderExecutionError, match="Unknown segment"):
            executor_with_live_enabled.place_market_order(
                security_id="X", segment="INVALID_SEG",
                transaction_type="BUY", quantity=1,
            )

    def test_market_order_invalid_transaction_type(self, executor_with_live_enabled):
        with pytest.raises(OrderExecutionError, match="transaction_type must be BUY or SELL"):
            executor_with_live_enabled.place_market_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="HOLD", quantity=1,
            )

    def test_market_order_zero_quantity(self, executor_with_live_enabled):
        with pytest.raises(OrderExecutionError, match="quantity must be > 0"):
            executor_with_live_enabled.place_market_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="BUY", quantity=0,
            )

    def test_market_order_dhanhq_exception(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.place_order.side_effect = Exception("Network timeout")
        with pytest.raises(OrderExecutionError, match="DhanHQ place_order failed"):
            executor_with_live_enabled.place_market_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="BUY", quantity=1,
            )

    def test_tag_passed_through(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.place_order.return_value = {"status": "success", "orderId": "X"}
        executor_with_live_enabled.place_market_order(
            security_id="2885", segment="NSE_EQ",
            transaction_type="BUY", quantity=1,
            tag="entry-strategy-1",
        )
        assert mock_dhan_service.dhan.place_order.call_args.kwargs["tag"] == "entry-strategy-1"


# ============================================================
#  Limit order placement
# ============================================================

class TestPlaceLimitOrder:
    def test_successful_limit_order(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.place_order.return_value = {
            "status": "success", "orderId": "ORD-L-1",
        }
        resp = executor_with_live_enabled.place_limit_order(
            security_id="2885", segment="NSE_EQ",
            transaction_type="BUY", quantity=10, price=1000.0,
        )
        assert resp["orderId"] == "ORD-L-1"
        kwargs = mock_dhan_service.dhan.place_order.call_args.kwargs
        assert kwargs["orderType"] == "LIMIT"
        assert kwargs["price"] == 1000.0

    def test_limit_order_zero_price(self, executor_with_live_enabled):
        with pytest.raises(OrderExecutionError, match="price must be > 0"):
            executor_with_live_enabled.place_limit_order(
                security_id="2885", segment="NSE_EQ",
                transaction_type="BUY", quantity=1, price=0,
            )


# ============================================================
#  Order status polling / wait_for_fill
# ============================================================

class TestWaitForFill:
    def test_filled_immediately(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {
                "orderId": "X",
                "orderStatus": "TRADED",
                "averageTradedPrice": 1005.50,
            },
        }
        data = executor_with_live_enabled.wait_for_fill("X", timeout_sec=5, poll_interval_sec=0.01)
        assert data["orderStatus"] == "TRADED"
        assert data["averageTradedPrice"] == 1005.50

    def test_rejected(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderId": "X", "orderStatus": "REJECTED", "statusMessage": "Insufficient margin"},
        }
        with pytest.raises(OrderExecutionError, match="REJECTED"):
            executor_with_live_enabled.wait_for_fill("X", timeout_sec=5, poll_interval_sec=0.01)

    def test_cancelled(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderId": "X", "orderStatus": "CANCELLED"},
        }
        with pytest.raises(OrderExecutionError, match="CANCELLED"):
            executor_with_live_enabled.wait_for_fill("X", timeout_sec=5, poll_interval_sec=0.01)

    def test_pending_then_filled(self, executor_with_live_enabled, mock_dhan_service):
        """Order is PENDING on first poll, TRADED on second."""
        mock_dhan_service.dhan.get_order_by_id.side_effect = [
            {"status": "success", "data": {"orderStatus": "PENDING"}},
            {"status": "success", "data": {"orderStatus": "TRADED", "averageTradedPrice": 1000.0}},
        ]
        data = executor_with_live_enabled.wait_for_fill("X", timeout_sec=5, poll_interval_sec=0.01)
        assert data["orderStatus"] == "TRADED"
        assert mock_dhan_service.dhan.get_order_by_id.call_count == 2

    def test_timeout(self, executor_with_live_enabled, mock_dhan_service):
        """Order stays PENDING forever → timeout."""
        mock_dhan_service.dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderStatus": "PENDING"},
        }
        with pytest.raises(OrderExecutionError, match="not filled within"):
            executor_with_live_enabled.wait_for_fill("X", timeout_sec=1, poll_interval_sec=0.05)


# ============================================================
#  LTP retrieval
# ============================================================

class TestGetLtp:
    def test_successful_ltp(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.ticker_data.return_value = {
            "status": "success",
            "data": {
                "NSE_EQ:2885": {
                    "last_price": 1234.50,
                    "volume": 100000,
                },
            },
        }
        ltp = executor_with_live_enabled.get_ltp("2885", "NSE_EQ")
        assert ltp == 1234.50

    def test_ltp_zero_on_error(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.ticker_data.side_effect = Exception("API error")
        ltp = executor_with_live_enabled.get_ltp("2885", "NSE_EQ")
        assert ltp == 0.0

    def test_ltp_zero_on_empty_response(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.ticker_data.return_value = {"status": "success", "data": {}}
        ltp = executor_with_live_enabled.get_ltp("2885", "NSE_EQ")
        assert ltp == 0.0

    def test_ltp_zero_on_unknown_segment(self, executor_with_live_enabled):
        ltp = executor_with_live_enabled.get_ltp("2885", "UNKNOWN")
        assert ltp == 0.0

    def test_ltp_alternate_key_names(self, executor_with_live_enabled, mock_dhan_service):
        """DhanHQ sometimes uses 'lastPrice' instead of 'last_price'."""
        mock_dhan_service.dhan.ticker_data.return_value = {
            "status": "success",
            "data": {"NSE_EQ:2885": {"lastPrice": 999.0}},
        }
        ltp = executor_with_live_enabled.get_ltp("2885", "NSE_EQ")
        assert ltp == 999.0


# ============================================================
#  Fund limits
# ============================================================

class TestGetFundLimits:
    def test_successful(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {"availabelBalance": 500000.0},
        }
        resp = executor_with_live_enabled.get_fund_limits()
        assert resp["status"] == "success"

    def test_failure(self, executor_with_live_enabled, mock_dhan_service):
        mock_dhan_service.dhan.get_fund_limits.side_effect = Exception("Auth error")
        with pytest.raises(OrderExecutionError, match="get_fund_limits failed"):
            executor_with_live_enabled.get_fund_limits()
