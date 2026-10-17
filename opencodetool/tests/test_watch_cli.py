"""8단계 테스트: watch 검증 CLI (클라이언트 스텁으로 네트워크 대체)."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import crypto_alert.watch as watch_mod
from crypto_alert.exchanges.base import Candle, ExchangeError, Interval, Ticker


def _ticker(symbol: str) -> Ticker:
    return Ticker(
        symbol=symbol,
        price=100.0,
        change_rate=0.01,
        volume=2.0,
        time=datetime(2026, 10, 8, 12, 0, tzinfo=UTC),
    )


def _candle(symbol: str) -> Candle:
    return Candle(
        symbol=symbol,
        interval=Interval.M15,
        time=datetime(2026, 10, 8, 12, 0, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=3.0,
    )


class _StubClient:
    def __init__(self, exc: BaseException | None = None) -> None:
        self._exc = exc

    async def fetch_tickers(self, symbols):  # type: ignore[no-untyped-def]
        if self._exc is not None:
            raise self._exc
        return [_ticker(symbol) for symbol in symbols]

    async def fetch_candles(self, symbol: str, interval: Interval, limit: int = 3):  # type: ignore[no-untyped-def]
        if self._exc is not None:
            raise self._exc
        return [_candle(symbol)]

    async def stream_tickers(self, symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
        for symbol in symbols:
            on_ticker(_ticker(symbol))


class _FakeSession:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args) -> bool:  # type: ignore[no-untyped-def]
        return False


def _patch_all(monkeypatch, exc=None, watchlist=None):  # type: ignore[no-untyped-def]
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)
    monkeypatch.setattr(watch_mod, "UpbitClient", lambda session: _StubClient(exc))
    monkeypatch.setattr(watch_mod, "BinanceClient", lambda session: _StubClient(exc))
    monkeypatch.setattr(watch_mod, "OKXClient", lambda session: _StubClient(exc))
    if watchlist is not None:
        monkeypatch.setattr(watch_mod, "load_watchlist", lambda: watchlist)


def test_run_full_flow(monkeypatch, capsys) -> None:
    _patch_all(monkeypatch, watchlist={"upbit": ["BTC/KRW"], "binance": ["BTC/USDT"]})
    asyncio.run(watch_mod.run(0.01))
    out = capsys.readouterr().out
    assert "=== 현재가 스냅샷 ===" in out
    assert "2/1종목" not in out and "1/1종목" in out
    assert "=== 캔들 샘플" in out and "O 100" in out
    assert "=== 실시간 시세" in out and "BTC/KRW" in out
    assert "종료되었습니다." in out


def test_run_api_errors(monkeypatch, capsys) -> None:
    _patch_all(
        monkeypatch,
        exc=ExchangeError("먹통"),
        watchlist={"upbit": ["BTC/KRW"], "binance": []},
    )
    asyncio.run(watch_mod.run(0.01))
    out = capsys.readouterr().out
    assert "조회 실패" in out and "캔들 실패" in out


def test_run_empty_watchlist(monkeypatch, capsys) -> None:
    _patch_all(monkeypatch, watchlist={"upbit": [], "binance": []})
    asyncio.run(watch_mod.run(0.01))
    out = capsys.readouterr().out
    assert "감시 종목 없음" in out
    assert "감시 종목이 없어 스트림을 시작하지 않습니다." in out


def test_run_zero_duration_waits_for_stop(monkeypatch) -> None:
    """duration=0이면 Ctrl+C까지 대기 (취소로 탈출 확인)."""
    _patch_all(monkeypatch, watchlist={"upbit": ["BTC/KRW"], "binance": ["BTC/USDT"]})

    async def _main() -> None:
        task = asyncio.create_task(watch_mod.run(0))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_main())


def test_main_parses_duration(monkeypatch) -> None:
    calls: list[float] = []

    async def _fake_run(duration: float) -> None:
        calls.append(duration)

    monkeypatch.setattr(watch_mod, "run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["watch", "--duration", "5"])
    assert watch_mod.main() == 0
    assert calls == [5.0]
