"""3단계 테스트: 시가총액 자체 계산 + 보유종목 평가."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_alert.exchanges.base import Interval, Ticker
from crypto_alert.holdings import Holding, load_holdings, save_holdings, value_of
from crypto_alert.marketcap import compute_ranking, load_supplies


def _ticker(symbol: str, price: float, change: float = 0.0) -> Ticker:
    return Ticker(
        symbol=symbol,
        price=price,
        change_rate=change,
        volume=1.0,
        time=datetime(2026, 10, 8, tzinfo=UTC),
    )


# --- 시가총액 -------------------------------------------------------------


def test_ranking_prefers_binance_usd_price() -> None:
    """동일 종목은 USDT(달러) 가격을 우선 사용한다."""
    tickers = {
        "BTC/KRW": _ticker("BTC/KRW", 113_700_000.0),
        "BTC/USDT": _ticker("BTC/USDT", 83_400.0),
    }
    supplies = {"BTC": 20_000_000.0}
    ranks = compute_ranking(tickers, supplies, usd_krw=1_350.0)
    assert len(ranks) == 1  # BTC 하나로 중복 제거
    assert ranks[0].symbol == "BTC/USDT"
    assert ranks[0].price_usd == 83_400.0
    assert ranks[0].market_cap_usd == 20_000_000.0 * 83_400.0


def test_ranking_converts_krw_with_fx() -> None:
    tickers = {"SUI/KRW": _ticker("SUI/KRW", 1_350.0)}
    supplies = {"SUI": 3_000_000_000.0}
    ranks = compute_ranking(tickers, supplies, usd_krw=1_350.0)
    assert ranks[0].price_usd == 1.0  # 1350 KRW / 1350 = $1
    assert ranks[0].market_cap_usd == 3_000_000_000.0


def test_ranking_skips_missing_supply_and_sorts() -> None:
    tickers = {
        "AAA/USDT": _ticker("AAA/USDT", 10.0),  # 공급량 없음 → 제외
        "BBB/USDT": _ticker("BBB/USDT", 2.0),
        "CCC/USDT": _ticker("CCC/USDT", 3.0),
    }
    supplies = {"BBB": 1_000_000.0, "CCC": 100_000_000.0}
    ranks = compute_ranking(tickers, supplies)
    assert [r.base for r in ranks] == ["CCC", "BBB"]  # CCC 시총이 더 큼
    assert "AAA" not in {r.base for r in ranks}


def test_ranking_alias_bttc_to_btt() -> None:
    """바이낸스 BTTC와 업비트 BTT는 같은 자산으로 본다."""
    tickers = {"BTTC/USDT": _ticker("BTTC/USDT", 0.00000037)}
    supplies = {"BTT": 9_860_000_000_000.0}
    ranks = compute_ranking(tickers, supplies)
    assert len(ranks) == 1
    assert ranks[0].base == "BTTC"
    assert ranks[0].market_cap_usd > 0


def test_load_supplies_skips_note_key() -> None:
    path = Path(__file__).with_name("_tmp_supplies.json")
    path.write_text('{"_note": "메모", "BTC": 20000000, "ETH": "bad"}', encoding="utf-8")
    try:
        supplies = load_supplies(path)
    finally:
        path.unlink()
    assert supplies == {"BTC": 20_000_000.0}  # '_' 키와 비수치 값 제외


# --- 보유종목 -------------------------------------------------------------


def test_holdings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "holdings.json"
    items = [Holding(symbol="BTC/KRW", quantity=0.5, avg_price=100_000_000.0)]
    save_holdings(items, path)
    assert load_holdings(path) == items


def test_load_holdings_missing_file(tmp_path: Path) -> None:
    assert load_holdings(tmp_path / "none.json") == []


def test_value_of_profit() -> None:
    holding = Holding(symbol="ETH/KRW", quantity=2.0, avg_price=3_000_000.0)
    result = value_of(holding, current_price=3_500_000.0)
    assert result.value == 7_000_000.0
    assert result.pnl == 1_000_000.0
    assert abs(result.pnl_rate - (1_000_000.0 / 6_000_000.0)) < 1e-12


def test_value_of_zero_cost() -> None:
    holding = Holding(symbol="XRP/KRW", quantity=10.0, avg_price=0.0)
    assert value_of(holding, current_price=2_000.0).pnl_rate == 0.0


def test_ranking_exchange_override() -> None:
    """감시 목록 기반 거래소 표기 (OKX USDT도 USD 가격으로)."""
    from crypto_alert.marketcap import compute_ranking

    tickers = {"PI/USDT": _ticker("PI/USDT", 0.08)}
    ranks = compute_ranking(tickers, {"PI": 8_000_000_000.0}, exchanges={"PI/USDT": "okx"})
    assert len(ranks) == 1
    assert ranks[0].exchange == "okx"
    assert ranks[0].price_usd == 0.08
    fallback = compute_ranking(tickers, {"PI": 8_000_000_000.0})
    assert fallback[0].exchange == "binance"  # 매핑 없으면 기존 휴리스틱


# --- 차트 선택 키 ---------------------------------------------------------


def test_interval_values_match_ui() -> None:
    """UI 주기 값이 업비트/바이낸스 API에서 유효한 표기인지 확인한다."""
    assert {iv.value for iv in Interval} == {"15m", "4h", "1d", "1w", "1M"}


def test_load_supplies_missing_and_malformed(tmp_path: Path) -> None:
    assert load_supplies(tmp_path / "없음.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert load_supplies(bad) == {}


def test_load_holdings_skips_bad_rows(tmp_path: Path) -> None:
    path = tmp_path / "holdings.json"
    path.write_text(
        json.dumps(
            [
                {"symbol": "BTC/KRW", "quantity": 0.5, "avg_price": 100_000_000.0},
                "문자열",
                {"symbol": "", "quantity": 1.0, "avg_price": 1.0},
                {"symbol": "ETH/KRW", "quantity": "많음", "avg_price": 1.0},
                {"symbol": "XRP/KRW", "quantity": -1.0, "avg_price": 1.0},
            ]
        ),
        encoding="utf-8",
    )
    holdings = load_holdings(path)
    assert [h.symbol for h in holdings] == ["BTC/KRW"]
    assert load_holdings(tmp_path / "없음.json") == []
    not_list = tmp_path / "not_list.json"
    not_list.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert load_holdings(not_list) == []
