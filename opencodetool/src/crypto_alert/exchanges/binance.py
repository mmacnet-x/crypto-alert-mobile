"""바이낸스 현물 클라이언트 (REST + WebSocket).

REST docs: https://binance-docs.github.io/apidocs/spot/en/
WebSocket: 조합 스트림 (구독 메시지 없이 URL로 지정)
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar, Final

from crypto_alert.exchanges.base import (
    Candle,
    ExchangeClient,
    ExchangeError,
    Interval,
    Ticker,
)
from crypto_alert.exchanges.symbols import from_binance_symbol, to_binance_symbol

__all__ = [
    "BinanceClient",
    "parse_kline_row",
    "parse_ticker_row",
    "parse_ws_payload",
]

_MAX_CANDLES: Final[int] = 1000


def parse_kline_row(symbol: str, interval: Interval, row: Sequence[Any]) -> Candle:
    """바이낸스 klines 한 행(list)을 :class:`Candle`로 변환한다."""
    return Candle(
        symbol=symbol,
        interval=interval,
        time=datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )


def parse_ticker_row(row: Mapping[str, Any]) -> Ticker:
    """바이낸스 24h 시세 한 행을 :class:`Ticker`로 변환한다."""
    return Ticker(
        symbol=from_binance_symbol(str(row["symbol"])),
        price=float(row.get("lastPrice") or 0.0),
        change_rate=float(row.get("priceChangePercent") or 0.0) / 100.0,  # % → 소수
        volume=float(row.get("volume") or 0.0),
        time=_ms_to_dt(row.get("closeTime")),
    )


def parse_ws_payload(payload: Any) -> Ticker | None:
    """바이낸스 조합 스트림 메시지를 :class:`Ticker`로 변환한다."""
    if not isinstance(payload, Mapping):
        return None
    data = payload.get("data", payload)
    if not isinstance(data, Mapping) or data.get("e") != "24hrTicker":
        return None
    return Ticker(
        symbol=from_binance_symbol(str(data["s"])),
        price=float(data.get("c") or 0.0),
        change_rate=float(data.get("P") or 0.0) / 100.0,
        volume=float(data.get("v") or 0.0),
        time=_ms_to_dt(data.get("E")),
    )


def _ms_to_dt(value: Any) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC)


class BinanceClient(ExchangeClient):
    """바이낸스 현물 (BASE/QUOTE) 클라이언트."""

    name: ClassVar[str] = "binance"
    base_url: ClassVar[str] = "https://api.binance.com"
    WS_BASE: ClassVar[str] = "wss://stream.binance.com:9443"

    # --- REST ---------------------------------------------------------

    async def fetch_candles(
        self, symbol: str, interval: Interval, limit: int = 200
    ) -> list[Candle]:
        params = {
            "symbol": to_binance_symbol(symbol),
            "interval": interval.value,
            "limit": min(limit, _MAX_CANDLES),
        }
        data = await self._get("/api/v3/klines", params)
        if not isinstance(data, list):
            raise ExchangeError(f"바이낸스 캔들 응답 형식이 예상과 다릅니다: {type(data).__name__}")
        candles = [parse_kline_row(symbol, interval, row) for row in data]
        candles.sort(key=lambda item: item.time)
        return candles

    async def fetch_tickers(self, symbols: Sequence[str]) -> list[Ticker]:
        payload = json.dumps(
            [to_binance_symbol(item) for item in symbols],
            separators=(",", ":"),
        )
        try:
            data = await self._get("/api/v3/ticker/24hr", {"symbols": payload})
        except ExchangeError as exc:
            if exc.status != 400:
                raise
            return await self._fetch_each(symbols, self._fetch_one_ticker)
        rows = data if isinstance(data, list) else [data]
        return [parse_ticker_row(row) for row in rows]

    async def _fetch_one_ticker(self, symbol: str) -> list[Ticker]:
        data = await self._get("/api/v3/ticker/24hr", {"symbol": to_binance_symbol(symbol)})
        rows = data if isinstance(data, list) else [data]
        return [parse_ticker_row(row) for row in rows]

    # --- WebSocket ----------------------------------------------------

    def ticker_ws_url(self, symbols: Sequence[str]) -> str:
        streams = "/".join(f"{to_binance_symbol(item).lower()}@ticker" for item in symbols)
        return f"{self.WS_BASE}/stream?streams={streams}"

    def ticker_subscribe_message(self, symbols: Sequence[str]) -> None:
        return None  # 조합 스트림은 URL만으로 구독됨

    def parse_ticker_payload(self, payload: Any) -> Ticker | None:
        return parse_ws_payload(payload)
