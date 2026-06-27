"""
app.services.order_executor
---------------------------
Wrapper around dhanhq 2.2.0's order placement / modification / cancellation API.

This is the ONLY module that places real orders. It enforces:
- LIVE_TRADING_ENABLED master kill switch
- Per-segment product type mapping (CNC / INTRADAY / MARGIN)
- Retry on transient failures (tenacity)
- Order status polling (confirm fill before recording trade)
- LTP retrieval for square-off mark-to-market

All methods return dicts (the raw DhanHQ response) on success and raise
OrderExecutionError on failure.
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.core.config import settings
from app.services.dhan_service import DhanService


# ---------------------------------------------------------------------
#  Exceptions
# ---------------------------------------------------------------------

class OrderExecutionError(Exception):
    """Raised when a real order fails to place or fill."""


class LiveTradingDisabledError(OrderExecutionError):
    """Raised when live trading is disabled (kill switch on)."""


# ---------------------------------------------------------------------
#  Segment → product type + exchange segment mapping
# ---------------------------------------------------------------------

PRODUCT_TYPE_BY_SEGMENT = {
    "NSE_EQ":  lambda: settings.ORDER_PRODUCT_TYPE_EQ,
    "NSE_FNO": lambda: settings.ORDER_PRODUCT_TYPE_FNO,
    "MCX":     lambda: settings.ORDER_PRODUCT_TYPE_MCX,
}

# dhanhq exchange segment constants (from dhanhq.dhanhq class)
EXCHANGE_SEGMENT_BY_OUR_SEGMENT = {
    "NSE_EQ":  "NSE_EQ",
    "NSE_FNO": "NSE_FNO",
    "MCX":     "MCX_COMM",
}


# ---------------------------------------------------------------------
#  OrderExecutor
# ---------------------------------------------------------------------

class OrderExecutor:
    """
    Places real orders via DhanHQ. Wraps DhanService.dhan.place_order(...).

    Usage:
        executor = OrderExecutor()
        resp = executor.place_market_order(
            security_id="2885",
            segment="NSE_EQ",
            transaction_type="BUY",
            quantity=10,
            tag="stock-ct-entry-001",
        )
        order_id = resp["orderId"]
    """

    def __init__(self, dhan_service: DhanService | None = None) -> None:
        self.dhan = dhan_service or DhanService()
        self._preflight_check_done = False

    # ------------------------------------------------------------------
    #  Preflight safety check
    # ------------------------------------------------------------------

    def _preflight(self) -> None:
        """Verify LIVE_TRADING_ENABLED is True. Called once per OrderExecutor."""
        if self._preflight_check_done:
            return
        if not settings.LIVE_TRADING_ENABLED:
            raise LiveTradingDisabledError(
                "LIVE_TRADING_ENABLED=False in .env — real orders are blocked. "
                "Set LIVE_TRADING_ENABLED=true to enable live trading."
            )
        self._preflight_check_done = True
        logger.warning("⚠️  LIVE TRADING IS ENABLED — real orders will be placed")

    # ------------------------------------------------------------------
    #  Place a market order
    # ------------------------------------------------------------------

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.ORDER_RETRY_ATTEMPTS),
        wait=wait_fixed(settings.ORDER_RETRY_DELAY_SEC),
        retry=retry_if_exception_type(OrderExecutionError),
    )
    def place_market_order(
        self,
        security_id: str,
        segment: str,
        transaction_type: str,           # 'BUY' or 'SELL'
        quantity: int,
        tag: str | None = None,
        validity: str = "DAY",
    ) -> dict:
        """
        Place a MARKET order. Returns the DhanHQ response dict (contains 'orderId').
        Raises OrderExecutionError on failure.
        """
        self._preflight()

        if segment not in EXCHANGE_SEGMENT_BY_OUR_SEGMENT:
            raise OrderExecutionError(f"Unknown segment: {segment!r}")
        if transaction_type.upper() not in ("BUY", "SELL"):
            raise OrderExecutionError(f"transaction_type must be BUY or SELL, got {transaction_type!r}")
        if quantity <= 0:
            raise OrderExecutionError(f"quantity must be > 0, got {quantity}")

        exchange_segment = EXCHANGE_SEGMENT_BY_OUR_SEGMENT[segment]
        product_type = PRODUCT_TYPE_BY_SEGMENT[segment]()

        logger.info(
            "📈 Placing MARKET {} {} qty={} sec={} seg={} product={}",
            transaction_type, security_id, quantity, exchange_segment, segment, product_type,
        )

        try:
            resp = self.dhan.dhan.place_order(
                securityId=str(security_id),
                exchangeSegment=exchange_segment,
                transactionType=transaction_type.upper(),
                quantity=int(quantity),
                orderType="MARKET",
                productType=product_type,
                price=0.0,                       # ignored for MARKET orders
                triggerPrice=0.0,
                validity=validity,
                tag=tag,
            )
        except Exception as exc:
            raise OrderExecutionError(f"DhanHQ place_order failed: {exc}") from exc

        return self._validate_order_response(resp, transaction_type, security_id, quantity)

    # ------------------------------------------------------------------
    #  Place a limit order
    # ------------------------------------------------------------------

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.ORDER_RETRY_ATTEMPTS),
        wait=wait_fixed(settings.ORDER_RETRY_DELAY_SEC),
        retry=retry_if_exception_type(OrderExecutionError),
    )
    def place_limit_order(
        self,
        security_id: str,
        segment: str,
        transaction_type: str,
        quantity: int,
        price: float,
        tag: str | None = None,
        validity: str = "DAY",
    ) -> dict:
        """Place a LIMIT order at a specific price."""
        self._preflight()

        if segment not in EXCHANGE_SEGMENT_BY_OUR_SEGMENT:
            raise OrderExecutionError(f"Unknown segment: {segment!r}")
        if price <= 0:
            raise OrderExecutionError(f"price must be > 0, got {price}")

        exchange_segment = EXCHANGE_SEGMENT_BY_OUR_SEGMENT[segment]
        product_type = PRODUCT_TYPE_BY_SEGMENT[segment]()

        logger.info(
            "📈 Placing LIMIT {} {} qty={} @ ₹{} sec={} seg={}",
            transaction_type, security_id, quantity, price, exchange_segment, segment,
        )

        try:
            resp = self.dhan.dhan.place_order(
                securityId=str(security_id),
                exchangeSegment=exchange_segment,
                transactionType=transaction_type.upper(),
                quantity=int(quantity),
                orderType="LIMIT",
                productType=product_type,
                price=float(price),
                triggerPrice=0.0,
                validity=validity,
                tag=tag,
            )
        except Exception as exc:
            raise OrderExecutionError(f"DhanHQ place_order failed: {exc}") from exc

        return self._validate_order_response(resp, transaction_type, security_id, quantity)

    # ------------------------------------------------------------------
    #  Cancel a pending order
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending order by ID."""
        self._preflight()
        logger.info("❌ Cancelling order {}", order_id)
        try:
            return self.dhan.dhan.cancel_order(order_id)
        except Exception as exc:
            raise OrderExecutionError(f"DhanHQ cancel_order failed: {exc}") from exc

    # ------------------------------------------------------------------
    #  Get order status (for fill confirmation)
    # ------------------------------------------------------------------

    def get_order_status(self, order_id: str) -> dict:
        """Fetch the current status of an order. Returns DhanHQ response."""
        self._preflight()
        try:
            return self.dhan.dhan.get_order_by_id(order_id)
        except Exception as exc:
            raise OrderExecutionError(f"DhanHQ get_order_by_id failed: {exc}") from exc

    # ------------------------------------------------------------------
    #  Wait for order to be filled (poll)
    # ------------------------------------------------------------------

    def wait_for_fill(
        self,
        order_id: str,
        timeout_sec: int = 30,
        poll_interval_sec: float = 1.0,
    ) -> dict:
        """
        Poll order status until it's TRADED (filled) or timeout.
        Returns the final order status dict.
        Raises OrderExecutionError if order is REJECTED/CANCELLED or times out.
        """
        self._preflight()
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                resp = self.get_order_status(order_id)
            except OrderExecutionError:
                time.sleep(poll_interval_sec)
                continue

            # DhanHQ order status response shape:
            # {'status': 'success', 'data': {'orderId': ..., 'orderStatus': 'TRADED', 'averageTradedPrice': ...}}
            data = resp.get("data", {}) if isinstance(resp, dict) else {}
            status = (data.get("orderStatus") or "").upper()

            if status in ("TRADED", "COMPLETE"):
                avg_price = data.get("averageTradedPrice") or data.get("price")
                logger.info("✅ Order {} FILLED @ ₹{}", order_id, avg_price)
                return data
            if status in ("REJECTED", "CANCELLED"):
                raise OrderExecutionError(
                    f"Order {order_id} {status}: {data.get('statusMessage', 'no details')}"
                )
            # PENDING / TRANSIT / etc → keep polling
            time.sleep(poll_interval_sec)

        raise OrderExecutionError(
            f"Order {order_id} not filled within {timeout_sec}s (last status: {status})"
        )

    # ------------------------------------------------------------------
    #  Get LTP (last traded price) — for square-off mark-to-market
    # ------------------------------------------------------------------

    def get_ltp(self, security_id: str, segment: str) -> float:
        """
        Fetch the Last Traded Price for an instrument.
        Returns 0.0 if unavailable.
        """
        if segment not in EXCHANGE_SEGMENT_BY_OUR_SEGMENT:
            logger.warning("Unknown segment for LTP: {}", segment)
            return 0.0

        exchange_segment = EXCHANGE_SEGMENT_BY_OUR_SEGMENT[segment]
        try:
            resp = self.dhan.dhan.ticker_data({exchange_segment: [int(security_id)]})
        except Exception as exc:
            logger.error("DhanHQ ticker_data failed for {}: {}", security_id, exc)
            return 0.0

        if not isinstance(resp, dict):
            return 0.0
        data = resp.get("data", {})
        # Response shape: {'data': {'NSE_EQ:2885': {'last_price': 1234.5, ...}}}
        for _key, val in data.items():
            if isinstance(val, dict) and "last_price" in val:
                return float(val["last_price"])
            # Sometimes the price is under 'lastPrice' or 'ltp'
            if isinstance(val, dict):
                for k in ("lastPrice", "ltp", "last_price"):
                    if k in val:
                        return float(val[k])
        logger.warning("Could not parse LTP from DhanHQ response: {}", resp)
        return 0.0

    # ------------------------------------------------------------------
    #  Get fund limits (for pre-trade balance check)
    # ------------------------------------------------------------------

    def get_fund_limits(self) -> dict:
        """Return DhanHQ fund limits (balance, margin used, collateral, etc.)."""
        self._preflight()
        try:
            return self.dhan.dhan.get_fund_limits()
        except Exception as exc:
            raise OrderExecutionError(f"DhanHQ get_fund_limits failed: {exc}") from exc

    # ------------------------------------------------------------------
    #  Response validation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_order_response(
        resp: dict, txn_type: str, security_id: str, quantity: int,
    ) -> dict:
        """Check that DhanHQ accepted the order. Returns the response."""
        if not isinstance(resp, dict):
            raise OrderExecutionError(f"DhanHQ returned non-dict: {resp!r}")
        status = (resp.get("status") or "").lower()
        if status != "success":
            raise OrderExecutionError(
                f"DhanHQ order rejected: status={status} "
                f"remarks={resp.get('remarks')} response={resp}"
            )
        order_id = resp.get("orderId") or (resp.get("data") or {}).get("orderId")
        if not order_id:
            # Some responses nest orderId inside data
            logger.warning("DhanHQ success but no orderId in response: {}", resp)
        logger.info(
            "✅ Order accepted: {} {} qty={} → orderId={}",
            txn_type, security_id, quantity, order_id,
        )
        return resp


# ---------------------------------------------------------------------
#  Singleton accessor
# ---------------------------------------------------------------------

_executor: OrderExecutor | None = None


def get_order_executor() -> OrderExecutor:
    global _executor
    if _executor is None:
        _executor = OrderExecutor()
    return _executor
