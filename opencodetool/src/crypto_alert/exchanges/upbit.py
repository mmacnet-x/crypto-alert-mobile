"""업비트 원화마켓 클라이언트 (REST + WebSocket).

REST docs: https://docs.upbit.com/
WebSocket: MessagePack 기본 포맷 (JSON도 자동 처리)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar, Final
from uuid import uuid4

from crypto_alert.exchanges.base import (
    Candle,
    ExchangeClient,
    ExchangeError,
    Interval,
    Ticker,
    chunked,
)
from crypto_alert.exchanges.symbols import from_upbit_market, to_upbit_market

__all__ = [
    "UpbitClient",
    "candle_request",
    "parse_candle_row",
    "parse_ticker_row",
    "parse_ws_payload",
]

_MAX_CANDLES: Final[int] = 200  # 업비트 최대 조회 개수
_TICKER_CHUNK_SIZE: Final[int] = 10  # markets 파라미터 청크 크기

# 업비트 분봉: /v1/candles/minutes/{unit}
_UPBIT_MINUTES: Final[dict[Interval, int]] = {
    Interval.M15: 15,
    Interval.H4: 240,
}

# 업비트 일/주/월봉: /v1/candles/days?unit={n}
# (업비트 주봉=7일, 월봉=30일 단위 캔들로 근사 제공)
_UPBIT_DAYS: Final[dict[Interval, int]] = {
    Interval.D1: 1,
    Interval.W1: 7,
    Interval.MN: 30,
}


def candle_request(interval: Interval) -> tuple[str, dict[str, Any]]:
    """주기 → (API 경로, 추가 파라미터) 매핑."""
    if interval in _UPBIT_DAYS:
        return "/v1/candles/days", {"unit": _UPBIT_DAYS[interval]}
    unit = _UPBIT_MINUTES.get(interval)
    if unit is None:
        raise ValueError(f"업비트 미지원 주기입니다: {interval}")
    return f"/v1/candles/minutes/{unit}", {}


def parse_candle_row(symbol: str, interval: Interval, row: Mapping[str, Any]) -> Candle:
    """업비트 캔들 응답 한 행을 :class:`Candle`로 변환한다."""
    time = datetime.fromisoformat(str(row["candle_date_time_utc"])).replace(tzinfo=UTC)
    return Candle(
        symbol=symbol,
        interval=interval,
        time=time,
        open=float(row["opening_price"]),
        high=float(row["high_price"]),
        low=float(row["low_price"]),
        close=float(row["trade_price"]),
        volume=float(row["candle_acc_trade_volume"]),
    )


def parse_ticker_row(row: Mapping[str, Any]) -> Ticker:
    """업비트 시세 스냅샷 한 행을 :class:`Ticker`로 변환한다."""
    return Ticker(
        symbol=from_upbit_market(str(row["market"])),
        price=float(row.get("trade_price") or 0.0),
        change_rate=float(row.get("change_rate") or 0.0),
        volume=float(row.get("acc_trade_volume") or 0.0),
        time=_ms_to_dt(row.get("timestamp") or row.get("trade_timestamp")),
    )


def parse_ws_payload(payload: Any) -> Ticker | None:
    """업비트 WebSocket 메시지를 :class:`Ticker`로 변환한다."""
    if not isinstance(payload, Mapping) or payload.get("type") != "ticker":
        return None
    code = payload.get("code")
    if not isinstance(code, str):
        return None
    return Ticker(
        symbol=from_upbit_market(code),
        price=float(payload.get("trade_price") or 0.0),
        change_rate=float(payload.get("change_rate") or 0.0),
        volume=float(payload.get("acc_trade_volume_24h") or payload.get("acc_trade_volume") or 0.0),
        time=_ms_to_dt(payload.get("timestamp")),
    )


def _ms_to_dt(value: Any) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC)


class UpbitClient(ExchangeClient):
    """업비트 원화마켓 (KRW-*) 클라이언트."""

    name: ClassVar[str] = "upbit"
    base_url: ClassVar[str] = "https://api.upbit.com"
    WS_URL: ClassVar[str] = "wss://api.upbit.com/websocket/v1"

    # --- REST ---------------------------------------------------------

    async def fetch_candles(
        self, symbol: str, interval: Interval, limit: int = 200
    ) -> list[Candle]:
        path, extra = candle_request(interval)
        params: dict[str, Any] = {
            "market": to_upbit_market(symbol),
            "count": min(limit, _MAX_CANDLES),
            **extra,
        }
        data = await self._get(path, params)
        if not isinstance(data, list):
            raise ExchangeError(f"업비트 캔들 응답 형식이 예상과 다릅니다: {type(data).__name__}")
        candles = [parse_candle_row(symbol, interval, row) for row in data]
        candles.sort(key=lambda item: item.time)  # 과거 → 최신 순
        return candles

    async def fetch_tickers(self, symbols: Sequence[str]) -> list[Ticker]:
        results: list[Ticker] = []
        for chunk in chunked(list(symbols), _TICKER_CHUNK_SIZE):
            markets = ",".join(to_upbit_market(item) for item in chunk)
            try:
                data = await self._get("/v1/ticker", {"markets": markets})
            except ExchangeError as exc:
                if exc.status != 400:
                    raise
                results.extend(await self._fetch_each(chunk, self._fetch_one_ticker))
                continue
            if not isinstance(data, list):
                raise ExchangeError("업비트 시세 응답 형식이 예상과 다릅니다")
            results.extend(parse_ticker_row(row) for row in data)
        return results

    async def _fetch_one_ticker(self, symbol: str) -> list[Ticker]:
        data = await self._get("/v1/ticker", {"markets": to_upbit_market(symbol)})
        if not isinstance(data, list):
            return []
        return [parse_ticker_row(row) for row in data]

    # --- WebSocket ----------------------------------------------------

    def ticker_ws_url(self, symbols: Sequence[str]) -> str:
        return self.WS_URL

    def ticker_subscribe_message(self, symbols: Sequence[str]) -> list[dict[str, Any]]:
        return [
            {"ticket": str(uuid4())},
            {"type": "ticker", "codes": [to_upbit_market(item) for item in symbols]},
        ]

    def parse_ticker_payload(self, payload: Any) -> Ticker | None:
        return parse_ws_payload(payload)
