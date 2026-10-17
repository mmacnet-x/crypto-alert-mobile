"""2단계 테스트: 심볼 변환 + 감시 목록 설정 (네트워크 미사용)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_alert import config
from crypto_alert.exchanges.symbols import (
    SymbolError,
    from_binance_symbol,
    from_upbit_market,
    normalize_symbol,
    to_binance_symbol,
    to_upbit_market,
)


def test_normalize_upbit_formats() -> None:
    """업비트는 어떤 표기든 BTC/KRW 형태로 통일된다."""
    assert normalize_symbol("upbit", "BTC") == "BTC/KRW"
    assert normalize_symbol("upbit", "btc") == "BTC/KRW"
    assert normalize_symbol("upbit", "BTC/KRW") == "BTC/KRW"
    assert normalize_symbol("upbit", "KRW-BTC") == "BTC/KRW"


def test_normalize_upbit_rejects_non_krw() -> None:
    with pytest.raises(SymbolError):
        normalize_symbol("upbit", "BTC/USDT")


def test_normalize_binance_formats() -> None:
    """슬래시 유무 관계없이 DRIFTUSDT → DRIFT/USDT 처리."""
    assert normalize_symbol("binance", "BTC/USDT") == "BTC/USDT"
    assert normalize_symbol("binance", "btc-usdt") == "BTC/USDT"
    assert normalize_symbol("binance", "DRIFTUSDT") == "DRIFT/USDT"
    assert normalize_symbol("binance", "MOCAUSDT") == "MOCA/USDT"
    assert normalize_symbol("binance", "ZETAUSDT") == "ZETA/USDT"


def test_normalize_rejects_unknown() -> None:
    with pytest.raises(SymbolError):
        normalize_symbol("binance", "XYZQ")
    with pytest.raises(SymbolError):
        normalize_symbol("bybit", "BTC/USDT")
    with pytest.raises(SymbolError):
        normalize_symbol("upbit", "")


def test_symbol_conversion_helpers() -> None:
    assert to_upbit_market("BTC/KRW") == "KRW-BTC"
    assert from_upbit_market("KRW-BTC") == "BTC/KRW"
    assert to_binance_symbol("BTC/USDT") == "BTCUSDT"
    assert from_binance_symbol("BTCUSDT") == "BTC/USDT"
    assert from_binance_symbol("BTC/USDT") == "BTC/USDT"


def test_load_watchlist_creates_default_file(tmp_path: Path) -> None:
    """파일이 없으면 기본 목록(업비트 26 / 바이낸스 7 / OKX 1)으로 생성된다."""
    path = tmp_path / "watchlist.json"
    watchlist = config.load_watchlist(path)
    assert path.exists()
    assert len(watchlist["upbit"]) == 26
    assert len(watchlist["binance"]) == 7
    assert watchlist["upbit"][0] == "BTC/KRW"
    assert "BTTC/USDT" in watchlist["binance"]
    assert watchlist["okx"] == ["PI/USDT"]


def test_okx_symbol_roundtrip(tmp_path: Path) -> None:
    """OKX 종목 추가/삭제와 PAIR 표기 저장."""
    path = tmp_path / "watchlist.json"
    assert config.add_symbol("okx", "ETH-USDT", path) is True
    assert config.add_symbol("okx", "ETH/USDT", path) is False  # 중복
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "ETH/USDT" in raw["okx"] and "PI/USDT" in raw["okx"]  # 기본 PI 유지
    assert config.remove_symbol("okx", "ETHUSDT", path) is True
    assert config.remove_symbol("okx", "ETH/USDT", path) is False
    # okx 키가 없는 기존 파일도 그대로 읽힌다
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"upbit": ["BTC"], "binance": []}), encoding="utf-8")
    assert config.load_watchlist(legacy)["okx"] == []


def test_add_and_remove_symbol(tmp_path: Path) -> None:
    """추가/삭제가 파일에 반영되고 중복 추가는 거절된다."""
    path = tmp_path / "watchlist.json"
    assert config.add_symbol("upbit", "DOGE/KRW", path) is True
    assert config.add_symbol("upbit", "DOGE", path) is False  # 중복

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "DOGE" in raw["upbit"]  # 파일 표기는 티커 형식

    assert config.remove_symbol("upbit", "DOGE", path) is True
    assert config.remove_symbol("upbit", "DOGE", path) is False
    watchlist = config.load_watchlist(path)
    assert "DOGE/KRW" not in watchlist["upbit"]


def test_add_binance_symbol_keeps_pair_format(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    config.add_symbol("binance", "DOGEUSDT", path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "DOGE/USDT" in raw["binance"]


def test_unknown_exchange_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"upbit": [], "bybit": []}), encoding="utf-8")
    with pytest.raises(config.WatchlistError):
        config.load_watchlist(path)


def test_invalid_entry_rejected(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"upbit": ["BTC"], "binance": [123]}), encoding="utf-8")
    with pytest.raises(config.WatchlistError):
        config.load_watchlist(path)


def test_bad_symbol_and_shape_rejected(tmp_path: Path) -> None:
    bad_symbol = tmp_path / "bad_symbol.json"
    bad_symbol.write_text(json.dumps({"upbit": ["BTC/USDT"], "binance": []}), encoding="utf-8")
    with pytest.raises(config.WatchlistError):
        config.load_watchlist(bad_symbol)
    not_dict = tmp_path / "not_dict.json"
    not_dict.write_text(json.dumps(["upbit"]), encoding="utf-8")
    with pytest.raises(config.WatchlistError):
        config.load_watchlist(not_dict)
    not_list = tmp_path / "not_list.json"
    not_list.write_text(json.dumps({"upbit": "BTC", "binance": []}), encoding="utf-8")
    with pytest.raises(config.WatchlistError):
        config.load_watchlist(not_list)


def test_add_remove_unknown_exchange_rejected(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    with pytest.raises(config.WatchlistError):
        config.add_symbol("bybit", "BTCUSDT", path)
    with pytest.raises(config.WatchlistError):
        config.remove_symbol("bybit", "BTCUSDT", path)


def test_symbol_converter_rejects_bad_shape() -> None:
    with pytest.raises(SymbolError):
        normalize_symbol("upbit", "/KRW")
    with pytest.raises(SymbolError):
        normalize_symbol("binance", "/USDT")
    with pytest.raises(SymbolError):
        to_upbit_market("BTC")
    with pytest.raises(SymbolError):
        from_upbit_market("KRW-")
    with pytest.raises(SymbolError):
        to_binance_symbol("BTC")
