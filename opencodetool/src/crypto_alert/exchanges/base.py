"""거래소 공통 인터페이스와 표준 시세 데이터 모델.

모든 거래소 클라이언트는 이 모듈의 :class:`ExchangeClient` 계약을 따른다.
새 거래소를 추가할 때도 같은 인터페이스만 구현하면 되므로,
알림 엔진이나 차트는 거래소 차이를 알 필요가 없다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

import aiohttp
import msgpack

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10
WS_RECONNECT_INITIAL_SECONDS = 1.0
WS_RECONNECT_MAX_SECONDS = 30.0

__all__ = [
    "Candle",
    "ExchangeClient",
    "ExchangeError",
    "Interval",
    "Ticker",
    "chunked",
    "decode_ws_message",
]


class Interval(StrEnum):
    """캔들 주기 (거래소와 무관한 표준 표기).

    UI 제공 주기: 15분 / 4시간 / 1일 / 1주 / 1월.
    """

    M15 = "15m"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MN = "1M"

    @classmethod
    def parse(cls, value: str) -> Interval:
        """문자열(예: ``"1m"``)을 Interval로 변환한다."""
        try:
            return cls(value)
        except ValueError as exc:
            supported = ", ".join(item.value for item in cls)
            raise ValueError(f"지원하지 않는 주기입니다: {value!r} (가능: {supported})") from exc


@dataclass(frozen=True, slots=True)
class Candle:
    """캔들 하나 (UTC 기준 시작 시각, volume은 기본자산 수량)."""

    symbol: str
    interval: Interval
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class Ticker:
    """현재가 스냅샷 / 실시간 스트림 단위 데이터."""

    symbol: str
    price: float
    change_rate: float  # 등락률(소수): 0.0123 → +1.23%
    volume: float  # 24h 기본자산 거래량
    time: datetime


class ExchangeError(RuntimeError):
    """거래소 API 호출 실패."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status  # HTTP 상태코드 (배치 폴백 판단용)


def chunked(items: Sequence[str], size: int) -> Iterator[list[str]]:
    """시퀀스를 size 크기 묶음으로 나눈다."""
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def decode_ws_message(data: str | bytes) -> Any:
    """WebSocket 메시지를 디코딩한다 (JSON 우선, MessagePack 폴백)."""
    if isinstance(data, str):
        return json.loads(data)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return msgpack.unpackb(data, raw=False)


class ExchangeClient(ABC):
    """거래소 클라이언트가 지켜야 할 공통 계약."""

    name: ClassVar[str] = ""
    base_url: ClassVar[str] = ""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # REST 공통 헬퍼
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET 요청 후 JSON을 반환한다. 실패 시 :class:`ExchangeError`."""
        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        try:
            async with self._session.get(url, params=params, timeout=timeout) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise ExchangeError(
                        f"{self.name} HTTP {resp.status}: {text[:200]}", status=resp.status
                    )
        except ExchangeError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ExchangeError(f"{self.name} 요청 실패: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExchangeError(f"{self.name} 잘못된 응답: {text[:200]}") from exc

    async def _fetch_each(
        self,
        symbols: Sequence[str],
        fetch_one: Callable[[str], Awaitable[list[Ticker]]],
    ) -> list[Ticker]:
        """종목별 개별 조회로 폴백한다 (배치 중 단일 종목 오류와 분리)."""
        results: list[Ticker] = []
        failed: list[str] = []
        for symbol in symbols:
            try:
                results.extend(await fetch_one(symbol))
            except ExchangeError:
                failed.append(symbol)
        if failed:
            logger.warning(
                "%s: 시세 조회 실패 %d개 → %s", self.name, len(failed), ", ".join(failed)
            )
        return results

    # ------------------------------------------------------------------
    # 추상 메서드: 각 거래소가 구현
    # ------------------------------------------------------------------

    @abstractmethod
    async def fetch_candles(
        self, symbol: str, interval: Interval, limit: int = 200
    ) -> list[Candle]:
        """과거 캔들을 과거→최신 순으로 반환한다."""

    @abstractmethod
    async def fetch_tickers(self, symbols: Sequence[str]) -> list[Ticker]:
        """현재가 스냅샷을 반환한다."""

    @abstractmethod
    def ticker_ws_url(self, symbols: Sequence[str]) -> str:
        """현재가 WebSocket URL을 반환한다."""

    @abstractmethod
    def ticker_subscribe_message(
        self, symbols: Sequence[str]
    ) -> str | list[Any] | dict[str, Any] | None:
        """연결 직후 전송할 구독 메시지 (불필요하면 None)."""

    @abstractmethod
    def parse_ticker_payload(self, payload: Any) -> Ticker | None:
        """WebSocket 메시지를 Ticker로 변환 (관련 없으면 None)."""

    # ------------------------------------------------------------------
    # WebSocket 공통 로직 (자동 재연결 포함)
    # ------------------------------------------------------------------

    async def stream_tickers(
        self,
        symbols: Sequence[str],
        on_ticker: Callable[[Ticker], None],
        stop: asyncio.Event,
    ) -> None:
        """실시간 현재가 스트림. 실패 시 지수 백오프로 재연결한다."""
        if not symbols:
            return
        backoff = WS_RECONNECT_INITIAL_SECONDS
        while not stop.is_set():
            try:
                url = self.ticker_ws_url(symbols)
                async with self._session.ws_connect(url, heartbeat=30) as ws:
                    message = self.ticker_subscribe_message(symbols)
                    if isinstance(message, str):
                        await ws.send_str(message)
                    elif message is not None:
                        await ws.send_json(message)
                    backoff = WS_RECONNECT_INITIAL_SECONDS
                    await self._read_loop(ws, on_ticker, stop)
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, TimeoutError, OSError) as exc:
                logger.warning("%s WebSocket 오류: %s", self.name, exc)
            if stop.is_set():
                break
            logger.info("%s 재연결 대기 %.1f초", self.name, backoff)
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, WS_RECONNECT_MAX_SECONDS)

    async def _read_loop(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        on_ticker: Callable[[Ticker], None],
        stop: asyncio.Event,
    ) -> None:
        """수신 루프: Ticker로 변환해 콜백에 전달한다."""
        async for msg in ws:
            if stop.is_set():
                return
            if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                payload = decode_ws_message(msg.data)
            elif msg.type in (
                aiohttp.WSMsgType.ERROR,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
            ):
                return
            else:
                continue
            ticker = self.parse_ticker_payload(payload)
            if ticker is not None:
                on_ticker(ticker)
