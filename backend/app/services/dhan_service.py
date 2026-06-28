"""
app.services.dhan_service
-------------------------
Wrapper around the dhanhq 2.2.0 SDK.

dhanhq 2.2.0 API (different from 1.x):
    from dhanhq import DhanContext, dhanhq
    ctx = DhanContext(client_id, access_token)
    dhan = dhanhq(ctx)
    dhan.historical_daily_data(security_id, exchange_segment, instrument_type,
                                from_date, to_date, expiry_code=0, oi=False)
    dhan.intraday_minute_data(security_id, exchange_segment, instrument_type,
                               from_date, to_date, interval=1, oi=False)

Exchange segments (constants on the dhanhq class):
    dhan.NSE = 'NSE_EQ'
    dhan.BSE = 'BSE_EQ'
    dhan.FNO = 'NSE_FNO'
    dhan.MCX = 'MCX_COMM'         # NOTE: was 'MCX' in 1.x, now 'MCX_COMM'
    dhan.CUR = 'NSE_CURRENCY'

Instrument types we use:
    NSE_EQ       → 'EQUITY'
    NSE_FNO      → 'INDEX' | 'OPTIDX' | 'OPTSTK' | 'FUTIDX' | 'FUTSTK'
    MCX_COMM     → 'FUTCOM' | 'OPTCOM'

Responsibilities:
- Authenticate via DhanContext
- Fetch historical OHLCV for NSE_EQ, NSE_FNO, MCX
- Persist bars into the OhlcvBar table (idempotent upserts)
- Load bars back from DB as a pandas DataFrame
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Any

import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ohlcv_bar import OhlcvBar


# --- Segment → (dhanhq constant value, default instrument_type) -------------
# Keys are OUR segment codes; values map to dhanhq's exchange_segment + instrument_type
SEGMENT_MAP: dict[str, dict] = {
    "NSE_EQ":  {"exchange_segment": "NSE_EQ",   "instrument_type": "EQUITY"},
    "NSE_FNO": {"exchange_segment": "NSE_FNO",  "instrument_type": "INDEX"},   # default for NIFTY/BANKNIFTY
    "MCX":     {"exchange_segment": "MCX_COMM", "instrument_type": "FUTCOM"},
}

# Map our interval strings → dhanhq method + (interval int for intraday)
INTERVAL_MAP: dict[str, dict] = {
    "1m":  {"method": "intraday_minute_data", "interval": 1},
    "5m":  {"method": "intraday_minute_data", "interval": 5},
    "15m": {"method": "intraday_minute_data", "interval": 15},
    "30m": {"method": "intraday_minute_data", "interval": 30},
    "1h":  {"method": "intraday_minute_data", "interval": 60},
    "1D":  {"method": "historical_daily_data", "interval": None},
}


class DhanService:
    """Sync wrapper around dhanhq 2.2.0."""

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
    ) -> None:
        self.client_id = client_id or settings.DHAN_CLIENT_ID
        self.access_token = access_token or settings.DHAN_ACCESS_TOKEN
        self._dhan = None
        self._ctx = None

    # ------------------------------------------------------------------ init
    @property
    def dhan(self):
        """Lazily build the dhanhq client."""
        if self._dhan is None:
            try:
                from dhanhq import DhanContext, dhanhq  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "dhanhq is not installed. Run: pip install dhanhq==2.2.0"
                ) from exc
            self._ctx = DhanContext(self.client_id, self.access_token)
            self._dhan = dhanhq(self._ctx)
            logger.info(
                "DhanHQ client initialised for client_id={}", self.client_id
            )
        return self._dhan

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
        instrument_type: str | None = None,
        expiry_code: int = 0,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV bars.

        Returns DataFrame with columns:
            timestamp, open, high, low, close, volume
        """
        if segment not in SEGMENT_MAP:
            raise ValueError(f"Unsupported segment: {segment!r}. Supported: {list(SEGMENT_MAP)}")
        if interval not in INTERVAL_MAP:
            raise ValueError(f"Unsupported interval: {interval!r}. Supported: {list(INTERVAL_MAP)}")

        seg = SEGMENT_MAP[segment]
        # Allow caller to override instrument_type (e.g. 'OPTIDX' for index options)
        instr_type = instrument_type or seg["instrument_type"]
        exchange_segment = seg["exchange_segment"]

        end = to_date or date.today()
        start = from_date or (end - timedelta(days=365))

        # dhanhq expects ISO date strings 'YYYY-MM-DD'
        from_str = start.strftime("%Y-%m-%d") if hasattr(start, "strftime") else str(start)
        to_str = end.strftime("%Y-%m-%d") if hasattr(end, "strftime") else str(end)

        logger.info(
            "DhanHQ historical fetch: sec={} seg={} instr={} interval={} {}..{}",
            security_id, exchange_segment, instr_type, interval, from_str, to_str,
        )

        interval_cfg = INTERVAL_MAP[interval]
        method_name = interval_cfg["method"]

        if method_name == "historical_daily_data":
            resp = self.dhan.historical_daily_data(
                security_id=str(security_id),
                exchange_segment=exchange_segment,
                instrument_type=instr_type,
                from_date=from_str,
                to_date=to_str,
                expiry_code=expiry_code,
            )
        else:
            # intraday_minute_data — interval is an int (minutes)
            resp = self.dhan.intraday_minute_data(
                security_id=str(security_id),
                exchange_segment=exchange_segment,
                instrument_type=instr_type,
                from_date=from_str,
                to_date=to_str,
                interval=interval_cfg["interval"],
            )

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
        dhanhq 2.2.0 returns a dict with 'status', 'remarks', 'data'.
        'data' can be either a list-of-dicts or a JSON string.

        Normalises into a DataFrame with columns:
            timestamp, open, high, low, close, volume
        """
        if resp is None:
            logger.error("DhanHQ returned None response")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Some error responses come back without a 'data' key
        if isinstance(resp, dict):
            status = resp.get("status", "")
            if status == "failure":
                logger.error(
                    "DhanHQ failure: remarks={} data={}",
                    resp.get("remarks"), resp.get("data"),
                )
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Extract data payload
        if isinstance(resp, dict):
            data = resp.get("data", resp)
        else:
            data = resp

        # data may be a JSON string in some responses
        if isinstance(data, str):
            try:
                import json
                data = json.loads(data)
            except json.JSONDecodeError:
                logger.error("DhanHQ data is non-JSON string: {!r}", data[:200])
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        if not data:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Some responses nest a list under another key
        if isinstance(data, dict):
            for k in ("historicalDailyOHLC", "historical_daily_ohlc", "ohlcv", "candles", "bars", "open_close"):
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break

        df = pd.DataFrame(data)
        # Normalise column names — dhanhq 2.2.0 typically returns:
        #   {'start_Time': epoch_ms, 'open': '...','high': '...','low': '...','close': '...','volume': '...'}
        # Or sometimes 'timestamp' instead of 'start_Time'
        col_map = {
            # Timestamp variants
            "timestamp": "timestamp",
            "date": "timestamp",
            "bhavdate": "timestamp",
            "start_Time": "timestamp",
            "start_time": "timestamp",
            "time": "timestamp",
            "ts": "timestamp",
            # OHLCV — case variants
            "open": "open",     "OPEN": "open",   "Open": "open",
            "high": "high",     "HIGH": "high",   "High": "high",
            "low": "low",       "LOW": "low",     "Low": "low",
            "close": "close",   "CLOSE": "close", "Close": "close",
            "volume": "volume", "VOLUME": "volume", "Volume": "volume",
        }
        df = df.rename(columns={c: col_map[c] for c in df.columns if c in col_map})
        for required in ("timestamp", "open", "high", "low", "close"):
            if required not in df.columns:
                logger.error("DhanHQ response missing column {}. Got: {}", required, df.columns.tolist())
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        if "volume" not in df.columns:
            df["volume"] = 0

        # Timestamp: dhanhq often returns epoch milliseconds (int) — convert
        ts = df["timestamp"]
        if pd.api.types.is_numeric_dtype(ts):
            # Heuristic: epoch seconds vs epoch milliseconds
            sample = ts.iloc[0]
            if sample > 1e12:  # ms
                df["timestamp"] = pd.to_datetime(ts, unit="ms", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            else:  # seconds
                df["timestamp"] = pd.to_datetime(ts, unit="s", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", dayfirst=True)

        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        for c in ("open", "high", "low", "close"):
            # Coerce to numeric, handling string values like "1234.50"
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

        # Drop rows with NaN OHLC (sometimes dhanhq returns a header row)
        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

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
        """Upsert OHLCV rows into the OhlcvBar table. Returns count inserted.

        Handles two edge cases that previously broke syncs:
        1. Duplicate timestamps within the batch — dhanhq sometimes returns
           the same bar twice (especially around expiries for FNO/MCX).
           Postgres rejects ON CONFLICT DO UPDATE if the same row would be
           affected twice. Fix: deduplicate by (security_id, timeframe, timestamp).
        2. Constraint name drift — use index_elements=[...] instead of
           constraint="uq_..." so we don't depend on the exact name.
        """
        if df.empty:
            return 0

        # --- Build row list -------------------------------------------------
        rows = []
        for _, r in df.iterrows():
            ts_val = r["timestamp"]
            if hasattr(ts_val, "to_pydatetime"):
                ts = ts_val.to_pydatetime()
            elif isinstance(ts_val, pd.Timestamp):
                ts = ts_val.to_pydatetime()
            else:
                ts = pd.Timestamp(ts_val).to_pydatetime()
            rows.append({
                "segment": segment,
                "security_id": str(security_id),
                "symbol": symbol,
                "timeframe": interval,
                "timestamp": ts,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["volume"]),
            })

        # --- Deduplicate by (security_id, timeframe, timestamp) -------------
        # Keep the LAST occurrence (in case dhanhq sends a corrected value)
        seen: dict[tuple, dict] = {}
        for row in rows:
            key = (row["security_id"], row["timeframe"], row["timestamp"])
            seen[key] = row
        unique_rows = list(seen.values())
        if len(unique_rows) < len(rows):
            logger.warning(
                "Deduplicated {} → {} rows for {} ({} dupes removed)",
                len(rows), len(unique_rows), symbol, len(rows) - len(unique_rows),
            )

        # --- Bulk upsert ----------------------------------------------------
        db = SessionLocal()
        try:
            stmt = pg_insert(OhlcvBar).values(unique_rows)
            # Use index_elements (more robust than constraint="name")
            upd = stmt.on_conflict_do_update(
                index_elements=["security_id", "timeframe", "timestamp"],
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
            logger.info(
                "Persisted {} bars for {} ({})",
                len(unique_rows), symbol, interval,
            )
            return len(unique_rows)
        except Exception as exc:
            db.rollback()
            logger.error(
                "persist_bars failed for {} ({} rows): {}",
                symbol, len(unique_rows), exc,
            )
            raise
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
        instrument_type: str | None = None,
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
            instrument_type=instrument_type,
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
