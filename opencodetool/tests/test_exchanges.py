"""2단계 테스트: 거래소 응답 파싱 (네트워크 미사용, 샘플 픽스처)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import aiohttp
import msgpack
import pytest

from crypto_alert.exchanges.base import (
    ExchangeClient,
    ExchangeError,
    Interval,
    Ticker,
    chunked,
    decode_ws_message,
)
from crypto_alert.exchanges.binance import (
    BinanceClient,
    parse_kline_row,
)
from crypto_alert.exchanges.binance import (
    parse_ticker_row as parse_binance_ticker_row,
)
from crypto_alert.exchanges.binance import (
    parse_ws_payload as parse_binance_ws,
)
from crypto_alert.exchanges.upbit import (
    UpbitClient,
    candle_request,
    parse_candle_row,
)
from crypto_alert.exchanges.upbit import (
    parse_ticker_row as parse_upbit_ticker_row,
)
from crypto_alert.exchanges.upbit import (
    parse_ws_payload as parse_upbit_ws,
)

# --- 업비트 ---------------------------------------------------------------


def test_upbit_candle_request_mapping() -> None:
    assert candle_request(Interval.M15) == ("/v1/candles/minutes/15", {})
    assert candle_request(Interval.H4) == ("/v1/candles/minutes/240", {})
    assert candle_request(Interval.D1) == ("/v1/candles/days", {"unit": 1})
    assert candle_request(Interval.W1) == ("/v1/candles/days", {"unit": 7})
    assert candle_request(Interval.MN) == ("/v1/candles/days", {"unit": 30})


def test_upbit_parse_candle_row() -> None:
    row = {
        "market": "KRW-BTC",
        "candle_date_time_utc": "2026-10-08T01:00:00",
        "opening_price": 100.0,
        "high_price": 110.0,
        "low_price": 90.0,
        "trade_price": 105.0,
        "candle_acc_trade_volume": 12.5,
    }
    candle = parse_candle_row("BTC/KRW", Interval.M15, row)
    assert candle.symbol == "BTC/KRW"
    assert candle.time == datetime(2026, 10, 8, 1, 0, tzinfo=UTC)
    assert candle.open == 100.0
    assert candle.close == 105.0
    assert candle.volume == 12.5


def test_upbit_parse_ticker_row() -> None:
    row = {
        "market": "KRW-ETH",
        "trade_price": 3_500_000.0,
        "change_rate": 0.0234,
        "acc_trade_volume": 123.45,
        "timestamp": 1_760_000_000_000,
    }
    ticker = parse_upbit_ticker_row(row)
    assert ticker.symbol == "ETH/KRW"
    assert ticker.price == 3_500_000.0
    assert ticker.change_rate == 0.0234
    assert ticker.time.tzinfo is not None


def test_upbit_ws_payload() -> None:
    payload = {
        "type": "ticker",
        "code": "KRW-XRP",
        "trade_price": 2.5,
        "change_rate": -0.0123,
        "acc_trade_volume_24h": 1_000_000.0,
        "timestamp": 1_760_000_000_000,
    }
    ticker = parse_upbit_ws(payload)
    assert ticker is not None
    assert ticker.symbol == "XRP/KRW"
    assert ticker.change_rate == -0.0123
    assert parse_upbit_ws({"type": "candle"}) is None
    assert parse_upbit_ws(["not", "a", "dict"]) is None


# --- 바이낸스 -------------------------------------------------------------


def test_binance_parse_kline_row() -> None:
    row = [1_760_000_000_000, "100.1", "110.0", "90.0", "105.5", "12.5", 1_760_000_059_999]
    candle = parse_kline_row("BTC/USDT", Interval.M15, row)
    assert candle.time == datetime.fromtimestamp(1_760_000_000, tz=UTC)
    assert candle.open == 100.1
    assert candle.close == 105.5
    assert candle.volume == 12.5


def test_binance_parse_ticker_row() -> None:
    row = {
        "symbol": "BTCUSDT",
        "lastPrice": "105000.1",
        "priceChangePercent": "1.234",
        "volume": "999.5",
        "closeTime": 1_760_000_000_000,
    }
    ticker = parse_binance_ticker_row(row)
    assert ticker.symbol == "BTC/USDT"
    assert ticker.price == 105000.1
    assert ticker.change_rate == 0.01234  # % → 소수 변환
    assert ticker.volume == 999.5


def test_binance_ws_payload_combined_stream() -> None:
    payload = {
        "stream": "btcusdt@ticker",
        "data": {
            "e": "24hrTicker",
            "E": 1_760_000_000_000,
            "s": "BTCUSDT",
            "c": "105000.0",
            "P": "1.23",
            "v": "10.5",
        },
    }
    ticker = parse_binance_ws(payload)
    assert ticker is not None
    assert ticker.symbol == "BTC/USDT"
    assert ticker.change_rate == 0.0123
    assert parse_binance_ws({"stream": "x", "data": {"e": "kline"}}) is None
    assert parse_binance_ws("garbage") is None


# --- 공통 -----------------------------------------------------------------


def test_interval_parse() -> None:
    assert Interval.parse("15m") is Interval.M15
    assert Interval.parse("4h") is Interval.H4
    assert Interval.parse("1w") is Interval.W1
    assert Interval.parse("1M") is Interval.MN
    try:
        Interval.parse("7d")
    except ValueError as exc:
        assert "지원하지 않는 주기" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("7d는 실패해야 한다")


def test_decode_ws_message_json_and_msgpack() -> None:
    assert decode_ws_message('{"a": 1}') == {"a": 1}
    assert decode_ws_message(b'{"a": 1}') == {"a": 1}
    assert decode_ws_message(msgpack.packb({"code": "KRW-BTC"})) == {"code": "KRW-BTC"}


# --- 공통 헬퍼 (스텁) --------------------------------------------------------


class _StubClient(ExchangeClient):
    """네트워크 없이 base 공통 로직만 검증하는 최소 구현."""

    name = "stub"
    base_url = "https://stub.invalid"

    def __init__(self, session: Any, subscribe: Any = None) -> None:
        super().__init__(session)
        self._subscribe = subscribe if subscribe is not None else {"hello": True}

    async def fetch_candles(self, symbol: str, interval: Interval, limit: int = 200) -> list:
        raise NotImplementedError

    async def fetch_tickers(self, symbols) -> list:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def ticker_ws_url(self, symbols) -> str:  # type: ignore[no-untyped-def]
        return "wss://stub.invalid"

    def ticker_subscribe_message(self, symbols):  # type: ignore[no-untyped-def]
        return self._subscribe

    def parse_ticker_payload(self, payload: Any) -> Ticker | None:
        if isinstance(payload, dict) and payload.get("fire"):
            return Ticker(
                symbol="BTC/KRW",
                price=1.0,
                change_rate=0.0,
                volume=1.0,
                time=datetime(2026, 10, 8, tzinfo=UTC),
            )
        return None


class _FakeResp:
    def __init__(self, status: int = 200, text: str = "[]") -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


class _FakeCM:
    """`async with session.get(...)` / `ws_connect(...)` 스텁."""

    def __init__(self, result: Any = None, exc: BaseException | None = None) -> None:
        self._result = result
        self._exc = exc

    async def __aenter__(self) -> Any:
        if self._exc is not None:
            raise self._exc
        return self._result

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeSession:
    def __init__(self, resp: _FakeResp | None = None, exc: BaseException | None = None) -> None:
        self._resp = resp if resp is not None else _FakeResp()
        self._exc = exc

    def get(self, url: str, params: Any = None, timeout: Any = None) -> _FakeCM:
        return _FakeCM(self._resp, self._exc)

    def ws_connect(self, url: str, heartbeat: Any = None) -> _FakeCM:
        raise NotImplementedError


class _FakeWS:
    def __init__(self, messages: list) -> None:
        self._messages = messages
        self.sent: list[tuple[str, Any]] = []

    async def send_str(self, message: str) -> None:
        self.sent.append(("str", message))

    async def send_json(self, message: Any) -> None:
        self.sent.append(("json", message))

    def __aiter__(self):  # type: ignore[no-untyped-def]
        return self._iter()

    async def _iter(self):  # type: ignore[no-untyped-def]
        for message in self._messages:
            yield message


def _msg(msg_type: Any, data: Any) -> Any:
    return SimpleNamespace(type=msg_type, data=data)


def test_base_helpers() -> None:
    assert list(chunked(["a", "b", "c"], 2)) == [["a", "b"], ["c"]]
    assert list(chunked([], 3)) == []
    err = ExchangeError("oops", status=400)
    assert err.status == 400 and str(err) == "oops"
    assert ExchangeError("x").status is None
    with pytest.raises(ValueError, match="지원하지 않는 주기"):
        Interval.parse("1m")


def test_base_get_paths() -> None:
    client = _StubClient(_FakeSession())
    assert asyncio.run(client._get("/ping")) == []
    client = _StubClient(_FakeSession(_FakeResp(500, "boom")))
    with pytest.raises(ExchangeError) as exc_info:
        asyncio.run(client._get("/ping"))
    assert exc_info.value.status == 500
    client = _StubClient(_FakeSession(exc=aiohttp.ClientError("끊김")))
    with pytest.raises(ExchangeError, match="요청 실패"):
        asyncio.run(client._get("/ping"))
    client = _StubClient(_FakeSession(_FakeResp(200, "깨진응답{{{")))
    with pytest.raises(ExchangeError, match="잘못된 응답"):
        asyncio.run(client._get("/ping"))


def test_base_fetch_each_partial_failure(caplog) -> None:
    client = _StubClient(session=None)

    async def _one(symbol: str) -> list[Ticker]:
        if symbol == "BAD":
            raise ExchangeError("없음", status=404)
        return [
            Ticker(
                symbol=symbol,
                price=1.0,
                change_rate=0.0,
                volume=1.0,
                time=datetime(2026, 10, 8, tzinfo=UTC),
            )
        ]

    got = asyncio.run(client._fetch_each(["BTC/KRW", "BAD"], _one))
    assert [t.symbol for t in got] == ["BTC/KRW"]


def test_base_read_loop_branches() -> None:
    client = _StubClient(session=None)
    got: list[Ticker] = []
    stop = asyncio.Event()

    async def _run() -> None:
        ws = _FakeWS(
            [
                _msg(aiohttp.WSMsgType.TEXT, '{"fire": true}'),
                _msg(aiohttp.WSMsgType.TEXT, '{"fire": false}'),
                _msg(aiohttp.WSMsgType.BINARY, msgpack.packb({"fire": True})),
                _msg(aiohttp.WSMsgType.PING, b""),
                _msg(aiohttp.WSMsgType.ERROR, b""),
            ]
        )
        await client._read_loop(ws, got.append, stop)

    asyncio.run(_run())
    assert len(got) == 2 and all(t.symbol == "BTC/KRW" for t in got)

    async def _run_stop() -> None:
        stop.set()
        ws = _FakeWS([_msg(aiohttp.WSMsgType.TEXT, '{"fire": true}')])
        await client._read_loop(ws, got.append, stop)

    asyncio.run(_run_stop())
    assert len(got) == 2  # 중단 시 콜백 미호출


def test_base_stream_reconnect_and_messages() -> None:
    class _Session(_FakeSession):
        def __init__(self) -> None:
            self.calls = 0
            self.ws = _FakeWS(
                [
                    _msg(aiohttp.WSMsgType.TEXT, '{"fire": true}'),
                    _msg(aiohttp.WSMsgType.CLOSED, b""),
                ]
            )

        def ws_connect(self, url: str, heartbeat: Any = None) -> _FakeCM:
            self.calls += 1
            if self.calls == 1:
                raise aiohttp.ClientError("첫 연결 실패")
            return _FakeCM(self.ws)

    session = _Session()
    client = _StubClient(session, subscribe={"sub": True})
    got: list[Ticker] = []
    stop = asyncio.Event()

    async def _run() -> None:
        await client.stream_tickers(["BTC/KRW"], lambda t: (got.append(t), stop.set()), stop)

    import time

    started = time.monotonic()
    asyncio.run(_run())
    assert time.monotonic() - started >= 1.0  # 재연결 대기 발생
    assert len(got) == 1
    assert session.ws.sent == [("json", {"sub": True})]
    assert session.calls == 2


def test_base_stream_str_subscribe_and_empty() -> None:
    client = _StubClient(session=None, subscribe="hello")
    stop = asyncio.Event()
    stop.set()
    asyncio.run(client.stream_tickers([], lambda t: None, stop))  # 종목 없음 → 즉시 종료

    ws = _FakeWS(
        [
            _msg(aiohttp.WSMsgType.TEXT, '{"fire": true}'),
            _msg(aiohttp.WSMsgType.CLOSED, b""),
        ]
    )

    class _Session(_FakeSession):
        def ws_connect(self, url: str, heartbeat: Any = None) -> _FakeCM:
            return _FakeCM(ws)

    client = _StubClient(_Session(), subscribe="hello")
    got: list[Ticker] = []
    stop = asyncio.Event()

    async def _run() -> None:
        await client.stream_tickers(["BTC/KRW"], lambda t: (got.append(t), stop.set()), stop)

    asyncio.run(_run())
    assert len(got) == 1 and ws.sent == [("str", "hello")]


# --- 업비트/바이낸스 fetch (스텁 _get) ----------------------------------------


def _upbit_candle_rows() -> list[dict]:
    base = [
        ("2026-10-08T04:00:00", 100.0),
        ("2026-10-08T03:00:00", 99.0),
    ]
    return [
        {
            "candle_date_time_utc": clock,
            "opening_price": price,
            "high_price": price + 1,
            "low_price": price - 1,
            "trade_price": price + 0.5,
            "candle_acc_trade_volume": 10.0,
        }
        for clock, price in base
    ]


def _upbit_ticker_row(market: str = "KRW-BTC") -> dict:
    return {
        "market": market,
        "trade_price": 100_000_000.0,
        "change_rate": 0.01,
        "acc_trade_volume": 5.0,
        "timestamp": 1_759_900_000_000,
    }


def test_upbit_fetch_with_stub(monkeypatch) -> None:
    client = UpbitClient(session=None)  # type: ignore[arg-type]

    async def _ok(path: str, params: Any = None) -> Any:
        return _upbit_candle_rows()

    monkeypatch.setattr(client, "_get", _ok)
    candles = asyncio.run(client.fetch_candles("BTC/KRW", Interval.H4, limit=3))
    assert [c.close for c in candles] == [99.5, 100.5]  # 과거 → 최신 정렬
    assert client.ticker_ws_url(["BTC/KRW"]) == UpbitClient.WS_URL
    assert client.parse_ticker_payload({"type": "ticker", "code": 123}) is None

    async def _bad(path: str, params: Any = None) -> Any:
        return {"oops": True}

    monkeypatch.setattr(client, "_get", _bad)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_candles("BTC/KRW", Interval.M15))
    with pytest.raises(ValueError, match="미지원"):
        candle_request("1m")  # type: ignore[arg-type]


def test_upbit_fetch_tickers_fallback(monkeypatch) -> None:
    client = UpbitClient(session=None)  # type: ignore[arg-type]

    async def _flaky(path: str, params: Any = None) -> Any:
        if "," in params["markets"]:
            raise ExchangeError("부분 실패", status=400)
        return [_upbit_ticker_row(params["markets"])]

    monkeypatch.setattr(client, "_get", _flaky)
    tickers = asyncio.run(client.fetch_tickers(["BTC/KRW", "ETH/KRW"]))
    assert [t.symbol for t in tickers] == ["BTC/KRW", "ETH/KRW"]

    async def _fatal(path: str, params: Any = None) -> Any:
        raise ExchangeError("서버 오류", status=500)

    monkeypatch.setattr(client, "_get", _fatal)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_tickers(["BTC/KRW"]))

    async def _odd(path: str, params: Any = None) -> Any:
        return {"oops": True}

    monkeypatch.setattr(client, "_get", _odd)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_tickers(["BTC/KRW"]))
    assert asyncio.run(client._fetch_one_ticker("BTC/KRW")) == []
    # 타임스탬프 없으면 현재 시각으로 대체
    row = {k: v for k, v in _upbit_ticker_row().items() if k != "timestamp"}
    assert parse_upbit_ticker_row(row).price == 100_000_000.0


def test_binance_fetch_with_stub(monkeypatch) -> None:
    client = BinanceClient(session=None)  # type: ignore[arg-type]
    rows = [
        [1_759_900_000_000, "100.0", "101.0", "99.0", "100.5", "10.0"],
        [1_759_890_000_000, "99.0", "100.0", "98.0", "99.5", "11.0"],
    ]

    async def _ok(path: str, params: Any = None) -> Any:
        return rows

    monkeypatch.setattr(client, "_get", _ok)
    candles = asyncio.run(client.fetch_candles("BTC/USDT", Interval.M15))
    assert [c.close for c in candles] == [99.5, 100.5]

    async def _bad(path: str, params: Any = None) -> Any:
        return {"oops": True}

    monkeypatch.setattr(client, "_get", _bad)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_candles("BTC/USDT", Interval.M15))


def test_binance_fetch_tickers_variants(monkeypatch) -> None:
    client = BinanceClient(session=None)  # type: ignore[arg-type]
    row = {
        "symbol": "BTCUSDT",
        "lastPrice": "83000.0",
        "priceChangePercent": "1.00",
        "volume": "100.0",
        "closeTime": 1_759_900_000_000,
    }

    async def _single(path: str, params: Any = None) -> Any:
        return dict(row)  # 단일 dict 응답도 허용

    monkeypatch.setattr(client, "_get", _single)
    assert asyncio.run(client.fetch_tickers(["BTC/USDT"]))[0].symbol == "BTC/USDT"
    assert asyncio.run(client._fetch_one_ticker("BTC/USDT"))[0].price == 83_000.0
    assert "streams=" in client.ticker_ws_url(["BTC/USDT"])
    assert client.ticker_subscribe_message(["BTC/USDT"]) is None
    assert client.parse_ticker_payload({"e": "kline"}) is None
    assert parse_binance_ticker_row({k: v for k, v in row.items() if k != "closeTime"}).price > 0

    async def _bad(path: str, params: Any = None) -> Any:
        raise ExchangeError("부분 실패", status=400)

    monkeypatch.setattr(client, "_get", _bad)

    async def _fallback(symbols, fetch_one) -> list:  # type: ignore[no-untyped-def]
        return [parse_binance_ticker_row(dict(row))]

    monkeypatch.setattr(client, "_fetch_each", _fallback)
    assert len(asyncio.run(client.fetch_tickers(["BTC/USDT"]))) == 1

    async def _fatal(path: str, params: Any = None) -> Any:
        raise ExchangeError("서버 오류", status=500)

    monkeypatch.setattr(client, "_get", _fatal)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_tickers(["BTC/USDT"]))


def test_base_stream_cancelled_reraises() -> None:
    class _CancelWS(_FakeWS):
        async def _iter(self):  # type: ignore[no-untyped-def]
            raise asyncio.CancelledError
            yield  # pragma: no cover — 도달 불가 (제너레이터 표시용)

    class _Session(_FakeSession):
        def ws_connect(self, url: str, heartbeat: Any = None) -> _FakeCM:
            return _FakeCM(_CancelWS([]))

    client = _StubClient(_Session())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client.stream_tickers(["BTC/KRW"], lambda t: None, asyncio.Event()))


def test_upbit_single_ticker_and_subscribe(monkeypatch) -> None:
    client = UpbitClient(session=None)  # type: ignore[arg-type]

    async def _ok(path: str, params: Any = None) -> Any:
        return [_upbit_ticker_row()]

    monkeypatch.setattr(client, "_get", _ok)
    tickers = asyncio.run(client.fetch_tickers(["BTC/KRW"]))
    assert [t.symbol for t in tickers] == ["BTC/KRW"]
    message = client.ticker_subscribe_message(["BTC/KRW", "ETH/KRW"])
    assert message[1] == {"type": "ticker", "codes": ["KRW-BTC", "KRW-ETH"]}
    assert client.parse_ticker_payload({"type": "ticker", "code": "KRW-BTC"}) is not None
