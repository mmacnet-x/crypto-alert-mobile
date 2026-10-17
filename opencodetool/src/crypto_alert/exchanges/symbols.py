"""거래소별 심볼 표기 변환 유틸리티.

내부 표준 표기는 ``BASE/QUOTE`` 형식이다.

- 업비트 원화마켓: ``BTC`` / ``KRW-BTC`` / ``BTC/KRW`` → 표준 ``BTC/KRW``
- 바이낸스: ``BTC/USDT`` / ``BTCUSDT`` → 표준 ``BTC/USDT``
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "SymbolError",
    "from_binance_symbol",
    "from_okx_inst_id",
    "from_upbit_market",
    "normalize_symbol",
    "to_binance_symbol",
    "to_okx_inst_id",
    "to_upbit_market",
]

# 긴 쪽부터 매칭해야 FDUSD/FDUSDUSDT 같은 오탈를 막을 수 있다.
_BINANCE_QUOTES: Final[tuple[str, ...]] = (
    "FDUSD",
    "USDT",
    "USDC",
    "BUSD",
    "TUSD",
    "BTC",
    "ETH",
    "BNB",
    "TRY",
)


class SymbolError(ValueError):
    """심볼 표기를 해석할 수 없을 때 발생."""


def normalize_symbol(exchange: str, raw: str) -> str:
    """사용자 입력을 내부 표준 심볼(BASE/QUOTE)로 정규화한다."""
    text = raw.strip().upper().replace(" ", "")
    if not text:
        raise SymbolError("심볼이 비어 있습니다")

    if exchange == "upbit":
        text = text.removeprefix("KRW-")
        if "/" in text:
            base, _, quote = text.partition("/")
            if quote != "KRW":
                raise SymbolError(f"업비트는 원화마켓만 지원합니다: {raw!r}")
        else:
            base = text
        if not base:
            raise SymbolError(f"심볼을 해석할 수 없습니다: {raw!r}")
        return f"{base}/KRW"

    if exchange == "binance":
        text = text.replace("-", "/")
        if "/" in text:
            base, _, quote = text.partition("/")
            if not base or not quote:
                raise SymbolError(f"심볼을 해석할 수 없습니다: {raw!r}")
            return f"{base}/{quote}"
        for quote in sorted(_BINANCE_QUOTES, key=len, reverse=True):
            if text.endswith(quote) and len(text) > len(quote):
                return f"{text[: -len(quote)]}/{quote}"
        raise SymbolError(f"바이낸스 심볼을 해석할 수 없습니다: {raw!r}")

    if exchange == "okx":
        text = text.replace("-", "/")
        if "/" in text:
            base, _, quote = text.partition("/")
            if not base or not quote:
                raise SymbolError(f"심볼을 해석할 수 없습니다: {raw!r}")
            return f"{base}/{quote}"
        for quote in sorted(_BINANCE_QUOTES, key=len, reverse=True):
            if text.endswith(quote) and len(text) > len(quote):
                return f"{text[: -len(quote)]}/{quote}"
        raise SymbolError(f"OKX 심볼을 해석할 수 없습니다: {raw!r}")

    raise SymbolError(f"알 수 없는 거래소입니다: {exchange!r}")


def to_upbit_market(symbol: str) -> str:
    """``BTC/KRW`` → ``KRW-BTC`` (업비트 API 형식)."""
    base, _, quote = symbol.partition("/")
    if not base or not quote:
        raise SymbolError(f"업비트 심볼 형식이 잘못되었습니다: {symbol!r}")
    return f"{quote}-{base}"


def from_upbit_market(market: str) -> str:
    """``KRW-BTC`` → ``BTC/KRW``."""
    quote, _, base = market.partition("-")
    if not base or not quote:
        raise SymbolError(f"업비트 마켓 코드가 잘못되었습니다: {market!r}")
    return f"{base}/{quote}"


def to_binance_symbol(symbol: str) -> str:
    """``BTC/USDT`` → ``BTCUSDT`` (바이낸스 API 형식)."""
    base, _, quote = symbol.partition("/")
    if not base or not quote:
        raise SymbolError(f"바이낸스 심볼 형식이 잘못되었습니다: {symbol!r}")
    return f"{base}{quote}"


def from_binance_symbol(raw: str) -> str:
    """``BTCUSDT`` 또는 ``BTC/USDT`` → ``BTC/USDT``."""
    return normalize_symbol("binance", raw)


def to_okx_inst_id(symbol: str) -> str:
    """``PI/USDT`` → ``PI-USDT`` (OKX API 형식)."""
    base, _, quote = symbol.partition("/")
    if not base or not quote:
        raise SymbolError(f"OKX 심볼 형식이 잘못되었습니다: {symbol!r}")
    return f"{base}-{quote}"


def from_okx_inst_id(inst_id: str) -> str:
    """``PI-USDT`` 또는 ``PI/USDT`` → ``PI/USDT``."""
    return normalize_symbol("okx", inst_id)
