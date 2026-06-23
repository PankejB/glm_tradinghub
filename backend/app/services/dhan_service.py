"""
app.services.dhan_service
-------------------------
Wrapper around the dhanhq SDK.

Responsibilities:
- Authenticate (client_id + access_token from env)
- Fetch historical OHLCV for NSE_EQ, NSE_FNO, MCX
- Persist bars into the OhlcvBar table (idempotent upserts)
- Map symbols to DhanHQ security_ids

The wrapper is sync (dhanhq is sync). Celery workers call it directly;
FastAPI routes call it through Celery tasks to avoid blocking the event loop.
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Any, Iterable

import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ohlcv_bar import OhlcvBar


# --- DhanHQ segment codes ---------------------------------------------------
SEGMENT_MAP = {
    "NSE_EQ": "NSE_EQ",
    "NSE_FNO": "NSE_FNO",
    "MCX": "MCX",
}

# DhanHQ interval codes
INTERVAL_MAP = {
    "1m": "1_MINUTE",
    "5m": "5_MINUTE",
    "15m": "15_MINUTE",
    "30m": "30_MINUTE",
    "1h": "1_HOUR",
    "1D": "1_DAY",
}


class DhanService:
    """Thin sync wrapper around dhanhq.dhan_http."""

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
    ) -> None:
        self.client_id = client_id or settings.DHAN_CLIENT_ID
        self.access_token = access_token or settings.DHAN_ACCESS_TOKEN
        self._client = None

    # ------------------------------------------------------------------ init
    @property
    def client(self):
        """Lazily build the dhanhq client. Imports inside method so tests can run
        without the SDK installed."""
        if self._client is None:
            try:
                from dhanhq import dhan_http  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "dhanhq is not installed. Run: pip install dhanhq"
                ) from exc
            self._client = dhan_http.DhanHttp(
                self.client_id, self.access_token
            )
            logger.info("DhanHQ client initialised for client_id={}", self.client_id)
        return self._client

    # ------------------------------------------------------- historical data
    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    def fetch_historical(
        self,
        security_id: str,
        segment: str,
        interval: str = "1D",
        from_date: datetime | date | None = None,
        to_date: datetime | date | None = None,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV bars.

        Returns DataFrame with columns:
            timestamp, open, high, low, close, volume
        """
        if segment not in SEGMENT_MAP:
            raise ValueError(f"Unsupported segment: {segment}")
        if interval not in INTERVAL_MAP:
            raise ValueError(f"Unsupported interval: {interval}")

        end = to_date or date.today()
        start = from_date or (end - timedelta(days=365))

        # dhanhq expects ISO date strings
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": SEGMENT_MAP[segment],
            "instrument": SEGMENT_MAP[segment],
            "expiryCode": 0,
            "fromDate": start.strftime("%Y-%m-%d"),
            "toDate": end.strftime("%Y-%m-%d"),
        }

        logger.info(
            "DhanHQ historical fetch: sec={} seg={} interval={} {}..{}",
            security_id, segment, interval, start, end,
        )

        # The dhanhq method name varies across SDK versions; try both.
        try:
            resp = self.client.fetch_historical_daily_ohlc(
                securityId=payload["securityId"],
                exchangeSegment=payload["exchangeSegment"],
                instrument=payload["instrument"],
                expiryCode=payload["expiryCode"],
                fromDate=payload["fromDate"],
                toDate=payload["toDate"],
            )
        except AttributeError:
            resp = self.client.ohlc_daily(**payload)

        df = self._parse_dhan_response(resp, security_id=security_id, segment=segment)
        if df.empty:
            logger.warning("DhanHQ returned 0 bars for sec={}", security_id)
        return df

    # -------------------------------------------------- response parsing
    @staticmethod
    def _parse_dhan_response(
        resp: Any, security_id: str, segment: str
    ) -> pd.DataFrame:
        """
        dhanhq returns either a list-of-dicts or a dict with 'data' key.
        Normalises into a DataFrame.
        """
        if isinstance(resp, dict):
            data = resp.get("data", resp)
        else:
            data = resp

        if not data:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Some responses nest a list under another key
        if isinstance(data, dict):
            for k in ("historicalDailyOHLC", "ohlcv", "candles", "bars"):
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break

        df = pd.DataFrame(data)
        # Normalise column names
        col_map = {
            "timestamp": "timestamp",
            "date": "timestamp",
            "bhavdate": "timestamp",
            "open": "open",
            "OPEN": "open",
            "high": "high",
            "HIGH": "high",
            "low": "low",
            "LOW": "low",
            "close": "close",
            "CLOSE": "close",
            "volume": "volume",
            "VOLUME": "volume",
        }
        df = df.rename(columns={c: col_map[c] for c in df.columns if c in col_map})
        for required in ("timestamp", "open", "high", "low", "close"):
            if required not in df.columns:
                logger.error("DhanHQ response missing column {}: {}", required, df.columns.tolist())
                return pd.DataFrame()
        if "volume" not in df.columns:
            df["volume"] = 0

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        for c in ("open", "high", "low", "close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    # ------------------------------------------------- persist to DB
    def persist_bars(
        self,
        df: pd.DataFrame,
        security_id: str,
        symbol: str,
        segment: str,
        interval: str = "1D",
    ) -> int:
        """Upsert OHLCV rows into the OhlcvBar table. Returns count inserted."""
        if df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "segment": segment,
                "security_id": str(security_id),
                "symbol": symbol,
                "timeframe": interval,
                "timestamp": r["timestamp"].to_pydatetime() if hasattr(r["timestamp"], "to_pydatetime") else r["timestamp"],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["volume"]),
            })

        db = SessionLocal()
        try:
            stmt = pg_insert(OhlcvBar).values(rows)
            # Conflict on (security_id, timeframe, timestamp) -> update OHLCV
            upd = stmt.on_conflict_do_update(
                constraint="uq_ohlcv_sec_tf_ts",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            db.execute(upd)
            db.commit()
            logger.info("Persisted {} bars for {} ({})", len(rows), symbol, interval)
            return len(rows)
        finally:
            db.close()

    # ------------------------------------------- combined sync helper
    def sync_historical(
        self,
        security_id: str,
        symbol: str,
        segment: str,
        interval: str = "1D",
        days: int = 365,
    ) -> int:
        """Fetch + persist. Returns number of bars saved."""
        end = date.today()
        start = end - timedelta(days=days)
        df = self.fetch_historical(
            security_id=security_id,
            segment=segment,
            interval=interval,
            from_date=start,
            to_date=end,
        )
        return self.persist_bars(df, security_id, symbol, segment, interval)

    # -------------------------------------------------- load from DB
    @staticmethod
    def load_bars(
        security_id: str,
        timeframe: str = "1D",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Load OHLCV bars from local DB into a DataFrame."""
        db = SessionLocal()
        try:
            q = db.query(OhlcvBar).filter(
                OhlcvBar.security_id == str(security_id),
                OhlcvBar.timeframe == timeframe,
            )
            if start:
                q = q.filter(OhlcvBar.timestamp >= start)
            if end:
                q = q.filter(OhlcvBar.timestamp <= end)
            q = q.order_by(OhlcvBar.timestamp.asc())
            rows = q.all()
            if not rows:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
            return pd.DataFrame([{
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            } for r in rows])
        finally:
            db.close()


# Singleton-style accessor
_dhan: DhanService | None = None

def get_dhan_service() -> DhanService:
    global _dhan
    if _dhan is None:
        _dhan = DhanService()
    return _dhan
