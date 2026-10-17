"""8단계 테스트: 데이터 엔진 수명주기 + 요청 처리 (네트워크 없이 스텁 사용)."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime

import pytest

from crypto_alert.engine import DataEngine
from crypto_alert.exchanges.base import ExchangeError, Interval, Ticker


def _ticker(symbol: str = "BTC/KRW") -> Ticker:
    return Ticker(
        symbol=symbol,
        price=100.0,
        change_rate=0.01,
        volume=1.0,
        time=datetime(2026, 10, 8, tzinfo=UTC),
    )


class _StubClient:
    def __init__(self, exc: BaseException | None = None) -> None:
        self._exc = exc
        self.calls: list[str] = []

    async def fetch_candles(self, symbol: str, interval: Interval, limit: int = 200):  # type: ignore[no-untyped-def]
        self.calls.append(symbol)
        if self._exc is not None:
            raise self._exc
        return []

    async def fetch_tickers(self, symbols):  # type: ignore[no-untyped-def]
        self.calls.extend(symbols)
        if self._exc is not None:
            raise self._exc
        return [_ticker(symbol) for symbol in symbols]

    async def stream_tickers(self, symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
        for symbol in symbols:
            on_ticker(_ticker(symbol))


def test_lifecycle_without_start(qapp) -> None:
    engine = DataEngine()
    assert engine.is_running is False
    engine.stop()  # 시작 전 정지는 조용히 무시
    engine.request_candles("k", "upbit", "BTC/KRW", Interval.M15)
    engine.request_snapshot("s", "upbit", ["BTC/KRW"])
    engine.reload_watchlist()
    assert len(engine._pending) == 3
    for pending in engine._pending:
        pending.close()  # 미실행 코루틴 정리 (경고 방지)


def test_double_start_guarded(qapp, monkeypatch) -> None:
    engine = DataEngine()
    monkeypatch.setattr(engine, "_run_thread", lambda: None)
    engine.start()
    engine.start()  # 두 번째 호출은 무시
    assert engine._started is True
    engine.stop()


def test_stop_joins_live_thread() -> None:
    engine = DataEngine()
    thread = threading.Thread(target=time.sleep, args=(0.01,))
    thread.start()
    engine._thread = thread
    engine.stop(timeout=5.0)
    assert not thread.is_alive()


def test_run_thread_happy_path(qapp) -> None:
    """실행 스레드 진입/정리 + stop() 신호 전달."""
    engine = DataEngine()
    ready = threading.Event()

    async def _fake_run() -> None:
        engine._stop = asyncio.Event()
        ready.set()
        await engine._stop.wait()

    engine._run = _fake_run  # type: ignore[method-assign]
    thread = threading.Thread(target=engine._run_thread)
    thread.start()
    assert ready.wait(timeout=5.0)
    assert engine.is_running is True
    engine._thread = thread
    engine.stop(timeout=5.0)
    thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_run_thread_logs_exception(qapp, caplog) -> None:
    import logging

    async def _boom() -> None:
        raise RuntimeError("스레드 고장")

    engine = DataEngine()
    engine._run = _boom  # type: ignore[method-assign]
    engine._run_thread()  # 직접 호출로 예외 정리 경로 실행
    assert any("데이터 엔진 스레드 종료 중 오류" in r.message for r in caplog.records)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_do_candles_paths(qapp) -> None:
    engine = DataEngine()
    errors: list[str] = []
    engine.error_occurred.connect(errors.append)
    # 클라이언트 없음 → 오류 신호
    asyncio.run(engine._do_candles("k", "nope", "BTC/KRW", Interval.M15))
    assert errors and "준비하지 못했습니다" in errors[-1]
    # 정상 조회 → 신호 전달
    engine._clients["upbit"] = _StubClient()
    got: list[tuple] = []
    engine.candles_received.connect(lambda *a: got.append(a))
    asyncio.run(engine._do_candles("k", "upbit", "BTC/KRW", Interval.M15))
    assert got and got[0][0] == "k" and got[0][1] == "BTC/KRW"
    # 조회 실패 → 오류 신호
    engine._clients["upbit"] = _StubClient(ExchangeError("캔들 실패"))
    asyncio.run(engine._do_candles("k", "upbit", "BTC/KRW", Interval.M15))
    assert errors[-1] == "캔들 실패"


def test_do_snapshot_paths(qapp) -> None:
    engine = DataEngine()
    errors: list[str] = []
    engine.error_occurred.connect(errors.append)
    asyncio.run(engine._do_snapshot("s", "nope", ["BTC/KRW"]))
    assert errors and "준비하지 못했습니다" in errors[-1]
    engine._clients["binance"] = _StubClient()
    got: list[tuple] = []
    engine.snapshot_received.connect(lambda *a: got.append(a))
    asyncio.run(engine._do_snapshot("s", "binance", ["BTC/USDT"]))
    assert got and got[0][0] == "s" and got[0][1][0].symbol == "BTC/USDT"
    engine._clients["binance"] = _StubClient(ExchangeError("시세 실패"))
    asyncio.run(engine._do_snapshot("s", "binance", ["BTC/USDT"]))
    assert errors[-1] == "시세 실패"


def test_do_reload_watchlist_error(qapp, monkeypatch) -> None:
    import crypto_alert.engine as engine_mod

    engine = DataEngine()
    errors: list[str] = []
    engine.error_occurred.connect(errors.append)

    def _boom() -> dict:
        raise RuntimeError("파일 깨짐")

    monkeypatch.setattr(engine_mod, "load_watchlist", _boom)
    asyncio.run(engine._do_reload_watchlist())
    assert errors and "감시 목록 로드 실패" in errors[-1]


def test_stream_loop_paths(qapp) -> None:
    engine = DataEngine()
    engine._stop = asyncio.Event()
    got: list[tuple] = []
    conns: list[tuple] = []
    engine.ticker_received.connect(lambda *a: got.append(a))
    engine.connection_changed.connect(lambda *a: conns.append(a))

    # 알 수 없는 거래소 → 즉시 종료
    asyncio.run(engine._stream_loop("nope", ["BTC/KRW"]))
    assert got == [] and conns == []

    # 정상 스트림 1회전 후 중단
    engine._clients["upbit"] = _StubClient()

    async def _run() -> None:
        engine._stop = asyncio.Event()

        async def _once(symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
            on_ticker(_ticker("BTC/KRW"))
            stop.set()

        engine._clients["upbit"].stream_tickers = _once  # type: ignore[method-assign]
        await engine._stream_loop("upbit", ["BTC/KRW"])

    asyncio.run(_run())
    assert [s for s, _t in got] == ["BTC/KRW"]
    assert ("upbit", True) in conns and ("upbit", False) in conns

    # 취소 → 재발생
    async def _cancel(symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
        raise asyncio.CancelledError

    async def _run_cancel() -> None:
        engine._stop = asyncio.Event()
        engine._clients["upbit"].stream_tickers = _cancel  # type: ignore[method-assign]
        await engine._stream_loop("upbit", ["BTC/KRW"])

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run_cancel())

    # 일반 오류 → 오류 신호 후 중단
    async def _fail(symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
        stop.set()
        raise OSError("소켓 끊김")

    errors: list[str] = []
    engine.error_occurred.connect(errors.append)

    async def _run_fail() -> None:
        engine._stop = asyncio.Event()
        engine._clients["upbit"].stream_tickers = _fail  # type: ignore[method-assign]
        await engine._stream_loop("upbit", ["BTC/KRW"])

    asyncio.run(_run_fail())
    assert errors and "소켓 끊김" in errors[-1]


def test_submit_to_running_loop() -> None:
    engine = DataEngine()
    loop = asyncio.new_event_loop()
    done = threading.Event()

    async def _ping() -> None:
        done.set()

    def _run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_run_loop, daemon=True)
    thread.start()
    engine._loop = loop
    try:
        engine._submit(_ping())
        assert done.wait(timeout=5.0)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5.0)
        loop.close()


def test_run_full_cycle(qapp, monkeypatch) -> None:
    """_run 전체: 세션 생성 → 대기 요청 실행 → 스트림 시작 → 중지 정리."""
    import crypto_alert.engine as engine_mod

    engine = DataEngine()
    monkeypatch.setattr(engine_mod, "load_watchlist", lambda: {"upbit": ["BTC/KRW"], "binance": []})

    class _QuietClient:
        async def stream_tickers(self, symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
            return None

        async def fetch_tickers(self, symbols):  # type: ignore[no-untyped-def]
            from crypto_alert.exchanges.base import ExchangeError as _EE

            raise _EE("조용함")

    monkeypatch.setattr(engine_mod, "UpbitClient", lambda session: _QuietClient())
    monkeypatch.setattr(engine_mod, "BinanceClient", lambda session: _QuietClient())
    ticked: list[str] = []
    engine.ticker_received.connect(lambda s, t: ticked.append(s))
    engine.request_snapshot("early", "upbit", ["BTC/KRW"])  # 시작 전 접수 → 실행됨

    async def _main() -> None:
        engine._loop = asyncio.get_running_loop()
        await engine._run()

    async def _run_with_stop() -> None:
        task = asyncio.create_task(_main())
        await asyncio.sleep(0.2)  # 스트림 태스크 기동 대기
        engine._stop.set()
        await task

    errors: list[str] = []
    engine.error_occurred.connect(errors.append)
    asyncio.run(_run_with_stop())
    assert errors and "조용함" in errors[-1]
    assert engine._pending == []


def test_run_empty_watchlist(qapp, monkeypatch) -> None:
    """감시 종목이 없으면 스트림 없이 오류 신호 후 종료."""
    import crypto_alert.engine as engine_mod

    engine = DataEngine()
    monkeypatch.setattr(engine_mod, "load_watchlist", dict)
    errors: list[str] = []
    engine.error_occurred.connect(errors.append)

    async def _main() -> None:
        engine._loop = asyncio.get_running_loop()
        await engine._run()

    asyncio.run(_main())
    assert errors and "감시 종목이 비어 있습니다" in errors[-1]


def test_stream_loop_sleeps_then_cancelled(qapp) -> None:
    """중단 없이 스트림이 끝나면 1초 대기 후 루프 (취소로 탈출)."""
    from types import SimpleNamespace

    engine = DataEngine()

    async def _instant(symbols, on_ticker, stop) -> None:  # type: ignore[no-untyped-def]
        return None

    engine._clients["upbit"] = SimpleNamespace(stream_tickers=_instant)

    async def _run() -> None:
        engine._stop = asyncio.Event()
        await engine._stream_loop("upbit", ["BTC/KRW"])

    with pytest.raises(TimeoutError):
        asyncio.run(asyncio.wait_for(_run(), timeout=2.5))
