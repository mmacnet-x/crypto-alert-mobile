"""거래소 어댑터 패키지: 공통 인터페이스 + 업비트/바이낸스/OKX 구현."""

from __future__ import annotations

from crypto_alert.exchanges.base import (
    Candle,
    ExchangeClient,
    ExchangeError,
    Interval,
    Ticker,
)
from crypto_alert.exchanges.binance import BinanceClient
from crypto_alert.exchanges.okx import OKXClient
from crypto_alert.exchanges.symbols import SymbolError, normalize_symbol
from crypto_alert.exchanges.upbit import UpbitClient

__all__ = [
    "BinanceClient",
    "Candle",
    "ExchangeClient",
    "ExchangeError",
    "Interval",
    "OKXClient",
    "SymbolError",
    "Ticker",
    "UpbitClient",
    "normalize_symbol",
]
