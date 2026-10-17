"""8단계 테스트: 화면 포맷터 + watch CLI 포맷터 (네트워크 없이)."""

from __future__ import annotations

from datetime import UTC, datetime

from crypto_alert import formatting as fmt
from crypto_alert.exchanges.base import Ticker
from crypto_alert.watch import format_price as watch_format_price
from crypto_alert.watch import format_ticker


def test_format_price_branches() -> None:
    assert fmt.format_price(113_704_000.0) == "113,704,000.00"
    assert fmt.format_price(3.14159) == "3.1416"
    assert fmt.format_price(0) == "0"
    assert fmt.format_price(0.000054) == "0.000054"
    assert fmt.format_price(0.5) == "0.5"


def test_format_change_sign() -> None:
    assert fmt.format_change(0.0123) == "+1.23%"
    assert fmt.format_change(-0.05) == "-5.00%"
    assert fmt.format_change(0.0) == "+0.00%"


def test_format_volume() -> None:
    assert fmt.format_volume(1234.567) == "1,234.57"


def test_format_market_cap_units() -> None:
    assert fmt.format_market_cap(1.65e12) == "$1.65T"
    assert fmt.format_market_cap(2.5e9) == "$2.50B"
    assert fmt.format_market_cap(4.7e6) == "$4.7M"
    assert fmt.format_market_cap(999.0) == "$999"


def test_watch_format_price_branches() -> None:
    assert watch_format_price(150_000_000.0) == "150,000,000.00"
    assert watch_format_price(2.5) == "2.5000"
    assert watch_format_price(0) == "0"
    assert watch_format_price(0.000054) == "0.000054"


def test_watch_format_ticker() -> None:
    ticker = Ticker(
        symbol="BTC/KRW",
        price=100_000_000.0,
        change_rate=0.015,
        volume=12.5,
        time=datetime(2026, 10, 8, 12, 30, 45, tzinfo=UTC),
    )
    text = format_ticker("업비트", ticker)
    clock = ticker.time.astimezone().strftime("%H:%M:%S")
    assert "[업비트]" in text and "BTC/KRW" in text
    assert "100,000,000.00" in text and "+1.50%" in text and clock in text
