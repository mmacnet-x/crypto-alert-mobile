"""OKX 현물 클라이언트 (REST + WebSocket, 공개 API만 사용).

REST docs: https://www.okx.com/docs-v5/en/
캔들: 신→구 순 반환 → 과거→최신으로 정렬한다.
"""

from __future__ import annotations

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
from crypto_alert.exchanges.symbols import from_okx_inst_id, to_okx_inst_id

__all__ = [
    "OKXClient",
    "candle_bar",
    "parse_candle_row",
    "parse_ticker_row",
    "parse_ws_payload",
]

_MAX_CANDLES: Final[int] = 100  # OKX 1회 요청 최대 캔들 수
_MAX_PAGES: Final[int] = 10  # 페이지네이션 최대 횟수 (100 × 10 = 1000개)

# Interval → OKX bar 표기
_OKX_BARS: Final[dict[Interval, str]] = {
    Interval.M15: "15m",
    Interval.H4: "4H",
    Interval.D1: "1D",
    Interval.W1: "1W",
    Interval.MN: "1M",
}


def candle_bar(interval: Interval) -> str:
    """주기 → OKX bar 표기 매핑."""
    bar = _OKX_BARS.get(interval)
    if bar is None:
        raise ValueError(f"OKX 미지원 주기입니다: {interval}")
    return bar


def _check_okx(data: Any, what: str) -> Any:
    """OKX 응답 코드 확인 (code != '0' → ExchangeError)."""
    if not isinstance(data, Mapping) or str(data.get("code")) != "0":
        raise ExchangeError(f"OKX {what} 응답 오류: {str(data)[:200]}")
    return data.get("data")


def parse_candle_row(symbol: str, interval: Interval, row: Sequence[Any]) -> Candle:
    """OKX 캔들 한 행([ts, o, h, l, c, vol, ...])을 :class:`Candle`로 변환한다."""
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
    """OKX 24h 시세 한 행을 :class:`Ticker`로 변환한다."""
    price = float(row.get("last") or 0.0)
    open24 = float(row.get("open24h") or 0.0)
    change_rate = (price - open24) / open24 if open24 > 0 else 0.0
    return Ticker(
        symbol=from_okx_inst_id(str(row["instId"])),
        price=price,
        change_rate=change_rate,
        volume=float(row.get("vol24h") or 0.0),
        time=_ms_to_dt(row.get("ts")),
    )


def parse_ws_payload(payload: Any) -> Ticker | None:
    """OKX 공개 WebSocket 메시지를 :class:`Ticker`로 변환한다."""
    if not isinstance(payload, Mapping):
        return None
    arg = payload.get("arg")
    data = payload.get("data")
    if (
        not isinstance(arg, Mapping)
        or arg.get("channel") != "tickers"
        or not isinstance(data, list)
        or not data
    ):
        return None
    row = data[0]
    if not isinstance(row, Mapping):
        return None
    return parse_ticker_row(row)


def _ms_to_dt(value: Any) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC)


class OKXClient(ExchangeClient):
    """OKX 현물 (BASE-USDT) 클라이언트."""

    name: ClassVar[str] = "okx"
    base_url: ClassVar[str] = "https://www.okx.com"
    WS_URL: ClassVar[str] = "wss://ws.okx.com:8443/ws/v5/public"

    # --- REST ---------------------------------------------------------

    async def fetch_candles(
        self, symbol: str, interval: Interval, limit: int = 200
    ) -> list[Candle]:
        """캔들을 조회한다.

        OKX는 1회 최대 100개라 ``after``(과거 방향) 페이지네이션으로
        요청 개수만큼 보충한 뒤 과거→최신으로 정렬한다.
        """
        inst_id = to_okx_inst_id(symbol)
        bar = candle_bar(interval)
        rows: list[Sequence[Any]] = []
        after = ""
        for _page in range(_MAX_PAGES):
            page_limit = min(_MAX_CANDLES, limit - len(rows))
            if page_limit <= 0:
                break
            params: dict[str, str] = {
                "instId": inst_id,
                "bar": bar,
                "limit": str(page_limit),
            }
            if after:
                params["after"] = after
            data = _check_okx(await self._get("/api/v5/market/candles", params), "캔들")
            if not isinstance(data, list):
                raise ExchangeError(f"OKX 캔들 응답 형식이 예상과 다릅니다: {type(data).__name__}")
            if not data:
                break
            rows.extend(data)
            if len(data) < page_limit:  # 이보다 오래된 데이터 없음
                break
            after = str(data[-1][0])  # 신→구: 마지막 행이 가장 오래된 시각
        candles = [parse_candle_row(symbol, interval, row) for row in rows]
        candles.sort(key=lambda item: item.time)  # 과거 → 최신 순
        return candles[-limit:]

    async def fetch_tickers(self, symbols: Sequence[str]) -> list[Ticker]:
        return await self._fetch_each(symbols, self._fetch_one_ticker)

    async def _fetch_one_ticker(self, symbol: str) -> list[Ticker]:
        data = _check_okx(
            await self._get("/api/v5/market/ticker", {"instId": to_okx_inst_id(symbol)}),
            "시세",
        )
        if not isinstance(data, list):
            return []
        return [parse_ticker_row(row) for row in data]

    # --- WebSocket ----------------------------------------------------

    def ticker_ws_url(self, symbols: Sequence[str]) -> str:
        return self.WS_URL

    def ticker_subscribe_message(self, symbols: Sequence[str]) -> dict[str, Any]:
        return {
            "op": "subscribe",
            "args": [{"channel": "tickers", "instId": to_okx_inst_id(item)} for item in symbols],
        }

    def parse_ticker_payload(self, payload: Any) -> Ticker | None:
        return parse_ws_payload(payload)
