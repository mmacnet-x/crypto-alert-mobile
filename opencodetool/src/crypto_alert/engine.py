"""데이터 엔진: asyncio 이벤트 루프를 전용 스레드에서 돌린다.

- GUI 스레드에서는 이 클래스의 메서드만 호출한다 (스레드 세이프)
- 수신한 시세/캔들은 Qt 시그널로 GUI 스레드에 전달된다
- 차트/알림/시총/보유종목 모두 이 엔진을 공유해 사용한다
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import aiohttp
from PyQt6.QtCore import QObject, pyqtSignal

from crypto_alert.config import load_watchlist
from crypto_alert.exchanges.base import ExchangeClient, ExchangeError, Interval, Ticker
from crypto_alert.exchanges.binance import BinanceClient
from crypto_alert.exchanges.okx import OKXClient
from crypto_alert.exchanges.upbit import UpbitClient

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)

__all__ = ["DataEngine"]


class DataEngine(QObject):
    """비동기 시세 수신기 (Qt 시그널로 결과 전달)."""

    # (심볼, Ticker)
    ticker_received = pyqtSignal(str, object)
    # (요청 키, 심볼, Interval, list[Candle])
    candles_received = pyqtSignal(str, str, object, object)
    # (요청 키, list[Ticker]) — 시총/환율 스냅샷용
    snapshot_received = pyqtSignal(str, object)
    # (거래소, 연결 여부)
    connection_changed = pyqtSignal(str, bool)
    # 오류 메시지
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: aiohttp.ClientSession | None = None
        self._clients: dict[str, ExchangeClient] = {}
        self._watchlist: dict[str, list[str]] = {}
        self._stop = asyncio.Event()  # 루프 생성 후 실제 이벤트로 교체
        self._started = False
        self._pending: list[Any] = []  # 루프 시작 전 접수된 요청

    # ------------------------------------------------------------------
    # 수명주기
    # ------------------------------------------------------------------

    def start(self) -> None:
        """백그라운드 스레드에서 이벤트 루프를 시작한다 (호출 즉시 반환)."""
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run_thread, name="data-engine", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """엔진을 정지시킨다 (창 닫기 시 호출)."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._loop is not None and self._loop.is_running()

    # ------------------------------------------------------------------
    # GUI 스레드에서 호출하는 요청 API
    # ------------------------------------------------------------------

    def request_candles(self, key: str, exchange: str, symbol: str, interval: Interval) -> None:
        """캔들 조회를 요청한다. 결과는 candles_received로 온다."""
        self._submit(self._do_candles(key, exchange, symbol, interval))

    def request_snapshot(self, key: str, exchange: str, symbols: list[str]) -> None:
        """현재가 스냅샷을 요청한다 (시총/환율용). 결과는 snapshot_received."""
        self._submit(self._do_snapshot(key, exchange, symbols))

    def reload_watchlist(self) -> None:
        """감시 목록을 다시 읽는다 (종목 추가/삭제 후 호출)."""
        self._submit(self._do_reload_watchlist())

    def _submit(self, coro: Any) -> None:
        if self._loop is not None and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        else:
            self._pending.append(coro)  # 루프 시작 후 실행

    # ------------------------------------------------------------------
    # 스레드 진입점
    # ------------------------------------------------------------------

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._run())
        except Exception:
            logger.exception("데이터 엔진 스레드 종료 중 오류")
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _run(self) -> None:
        self._stop = asyncio.Event()
        self._watchlist = load_watchlist()
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            self._session = session
            self._clients = {
                "upbit": UpbitClient(session),
                "binance": BinanceClient(session),
                "okx": OKXClient(session),
            }
            for coro in self._pending:  # 시작 전 접수된 요청 실행
                self._loop.create_task(coro)
            self._pending.clear()
            tasks = [
                asyncio.create_task(self._stream_loop(exchange, symbols))
                for exchange, symbols in self._watchlist.items()
                if symbols
            ]
            if not tasks:
                self.error_occurred.emit("감시 종목이 비어 있습니다 (watchlist.json)")
                return
            try:
                await self._stop.wait()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _stream_loop(self, exchange: str, symbols: list[str]) -> None:
        """한 거래소의 실시간 시세 스트림 (끊기면 재연결)."""
        client = self._clients.get(exchange)
        if client is None:
            return

        def on_ticker(ticker: Ticker) -> None:
            self.ticker_received.emit(ticker.symbol, ticker)

        while not self._stop.is_set():
            self.connection_changed.emit(exchange, True)
            try:
                await client.stream_tickers(symbols, on_ticker, self._stop)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — 스트림 유지
                logger.warning("%s 스트림 오류: %s", exchange, exc)
                self.error_occurred.emit(f"{exchange} 스트림 오류: {exc}")
            finally:
                self.connection_changed.emit(exchange, False)
            if not self._stop.is_set():
                await asyncio.sleep(1.0)

    # ------------------------------------------------------------------
    # 요청 처리 코루틴
    # ------------------------------------------------------------------

    async def _do_candles(self, key: str, exchange: str, symbol: str, interval: Interval) -> None:
        client = self._clients.get(exchange)
        if client is None:
            self.error_occurred.emit(f"거래소를 준비하지 못했습니다: {exchange}")
            return
        try:
            candles = await client.fetch_candles(symbol, interval, limit=200)
        except ExchangeError as exc:
            self.error_occurred.emit(str(exc))
            return
        self.candles_received.emit(key, symbol, interval, candles)

    async def _do_snapshot(self, key: str, exchange: str, symbols: list[str]) -> None:
        client = self._clients.get(exchange)
        if client is None:
            self.error_occurred.emit(f"거래소를 준비하지 못했습니다: {exchange}")
            return
        try:
            tickers = await client.fetch_tickers(symbols)
        except ExchangeError as exc:
            self.error_occurred.emit(str(exc))
            return
        self.snapshot_received.emit(key, tickers)

    async def _do_reload_watchlist(self) -> None:
        try:
            self._watchlist = load_watchlist()
        except Exception as exc:  # noqa: BLE001 — 사용자 편집 파일 방어
            self.error_occurred.emit(f"감시 목록 로드 실패: {exc}")
