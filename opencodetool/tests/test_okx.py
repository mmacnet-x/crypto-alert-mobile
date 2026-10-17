"""OKX 클라이언트 테스트 (네트워크 미사용, 실측 응답 픽스처)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from crypto_alert.exchanges.base import ExchangeError, Interval
from crypto_alert.exchanges.okx import (
    OKXClient,
    candle_bar,
    parse_candle_row,
    parse_ticker_row,
    parse_ws_payload,
)
from crypto_alert.exchanges.symbols import (
    SymbolError,
    from_okx_inst_id,
    normalize_symbol,
    to_okx_inst_id,
)


def _ticker_row() -> dict:
    return {
        "instId": "PI-USDT",
        "last": "0.08202",
        "open24h": "0.08222",
        "vol24h": "32907278.268",
        "ts": "1791460284071",
    }


def test_candle_bar_mapping() -> None:
    assert candle_bar(Interval.M15) == "15m"
    assert candle_bar(Interval.H4) == "4H"
    assert candle_bar(Interval.D1) == "1D"
    assert candle_bar(Interval.W1) == "1W"
    assert candle_bar(Interval.MN) == "1M"
    with pytest.raises(ValueError, match="미지원"):
        candle_bar("1m")  # type: ignore[arg-type]


def test_parse_candle_row() -> None:
    row = ["1791459900000", "0.08227", "0.08232", "0.08192", "0.08202", "131994.3"]
    candle = parse_candle_row("PI/USDT", Interval.M15, row)
    assert candle.symbol == "PI/USDT"
    assert candle.close == 0.08202 and candle.volume == 131994.3


def test_parse_ticker_row() -> None:
    ticker = parse_ticker_row(_ticker_row())
    assert ticker.symbol == "PI/USDT"
    assert ticker.price == 0.08202
    assert ticker.change_rate == pytest.approx((0.08202 - 0.08222) / 0.08222)
    assert ticker.volume == 32907278.268


def test_parse_ticker_row_zero_open() -> None:
    row = dict(_ticker_row(), open24h="0")
    assert parse_ticker_row(row).change_rate == 0.0


def test_parse_ws_payload() -> None:
    payload = {"arg": {"channel": "tickers", "instId": "PI-USDT"}, "data": [_ticker_row()]}
    ticker = parse_ws_payload(payload)
    assert ticker is not None and ticker.symbol == "PI/USDT"
    assert parse_ws_payload({"event": "subscribe", "arg": {}}) is None
    assert parse_ws_payload({"arg": {"channel": "tickers"}, "data": []}) is None
    assert parse_ws_payload({"arg": {"channel": "tickers"}, "data": ["x"]}) is None
    assert parse_ws_payload({"arg": {"channel": "candle15m"}, "data": [_ticker_row()]}) is None
    assert parse_ws_payload("garbage") is None


def test_symbol_helpers() -> None:
    assert to_okx_inst_id("PI/USDT") == "PI-USDT"
    assert from_okx_inst_id("PI-USDT") == "PI/USDT"
    assert normalize_symbol("okx", "PIUSDT") == "PI/USDT"
    assert normalize_symbol("okx", "PI/USDT") == "PI/USDT"
    with pytest.raises(SymbolError):
        to_okx_inst_id("PIUSDT")
    with pytest.raises(SymbolError):
        normalize_symbol("okx", "???")
    with pytest.raises(SymbolError):
        normalize_symbol("okx", "/USDT")


def test_fetch_with_stub(monkeypatch) -> None:
    client = OKXClient(session=None)  # type: ignore[arg-type]
    rows = [
        ["1791459900000", "2.0", "3.0", "1.0", "2.5", "10.0"],
        ["1791459000000", "1.0", "2.0", "0.5", "1.5", "11.0"],
    ]

    async def _ok(path: str, params: Any = None) -> Any:
        if path.endswith("/candles"):
            assert params["bar"] == "4H" and params["limit"] == "100"
            return {"code": "0", "data": rows}
        return {"code": "0", "data": [_ticker_row()]}

    monkeypatch.setattr(client, "_get", _ok)
    candles = asyncio.run(client.fetch_candles("PI/USDT", Interval.H4))
    assert [c.close for c in candles] == [1.5, 2.5]  # 과거 → 최신 정렬
    tickers = asyncio.run(client.fetch_tickers(["PI/USDT"]))
    assert [t.symbol for t in tickers] == ["PI/USDT"]
    assert client.ticker_ws_url(["PI/USDT"]) == OKXClient.WS_URL
    message = client.ticker_subscribe_message(["PI/USDT"])
    assert message == {
        "op": "subscribe",
        "args": [{"channel": "tickers", "instId": "PI-USDT"}],
    }
    assert client.parse_ticker_payload({"event": "x"}) is None


def test_fetch_candles_pagination(monkeypatch) -> None:
    """OKX 1회 100개 제한 → after 페이지네이션으로 요청 개수만큼 보충."""
    client = OKXClient(session=None)  # type: ignore[arg-type]
    calls: list[dict] = []

    def _rows(newest_ts: int, count: int) -> list:
        return [[str(newest_ts - 900_000 * i), "1", "2", "0.5", "1.5", "10"] for i in range(count)]

    page1 = _rows(1_000_000_000_000, 100)  # 신→구 100개 (풀 페이지)
    oldest = int(page1[-1][0])
    page2 = _rows(oldest - 900_000, 5)  # 과거 5개 → 조기 종료

    async def _paged(path: str, params: Any = None) -> Any:
        calls.append(dict(params))
        return {"code": "0", "data": page2 if "after" in params else page1}

    monkeypatch.setattr(client, "_get", _paged)
    candles = asyncio.run(client.fetch_candles("PI/USDT", Interval.M15, limit=150))
    assert len(candles) == 105  # 100 + 5
    times = [c.time for c in candles]
    assert times == sorted(times) and len(set(times)) == len(times)  # 중복·정렬 없음
    assert calls[0]["limit"] == "100" and "after" not in calls[0]
    assert calls[1]["after"] == str(oldest)  # 가장 오래된 시각 이후부터
    assert calls[1]["limit"] == "50"  # 남은 요청 개수

    # limit 이하로 정확히 자른다 (limit=3 → 페이지 1개만)
    calls.clear()
    short = asyncio.run(client.fetch_candles("PI/USDT", Interval.M15, limit=3))
    assert len(short) == 3
    assert len(calls) == 1 and calls[0]["limit"] == "3"


def test_fetch_error_paths(monkeypatch) -> None:
    client = OKXClient(session=None)  # type: ignore[arg-type]

    async def _code_error(path: str, params: Any = None) -> Any:
        return {"code": "12345", "msg": "bad"}

    monkeypatch.setattr(client, "_get", _code_error)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_candles("PI/USDT", Interval.M15))
    # 시세는 종목별 폴백이라 실패해도 빈 목록 (경고만)
    assert asyncio.run(client.fetch_tickers(["PI/USDT"])) == []

    async def _odd(path: str, params: Any = None) -> Any:
        return {"code": "0", "data": {"oops": True}}

    monkeypatch.setattr(client, "_get", _odd)
    with pytest.raises(ExchangeError):
        asyncio.run(client.fetch_candles("PI/USDT", Interval.M15))
    assert asyncio.run(client._fetch_one_ticker("PI/USDT")) == []
