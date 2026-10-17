"""화면 표시용 포맷팅 유틸리티."""

from __future__ import annotations

__all__ = ["format_change", "format_market_cap", "format_price", "format_volume"]


def format_price(price: float) -> str:
    """가격을 읽기 좋은 형태로 포맷한다."""
    if price >= 100:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:,.4f}"
    if price == 0:
        return "0"
    return f"{price:.10f}".rstrip("0")


def format_change(rate: float) -> str:
    """등락률(소수)을 퍼센트 문자열로 표시한다 (예: +1.23%)."""
    return f"{rate * 100:+.2f}%"


def format_volume(volume: float) -> str:
    """거래량을 천단위 구분자로 표시한다."""
    return f"{volume:,.2f}"


def format_market_cap(value_usd: float) -> str:
    """시가총액(USD)을 약어로 표시한다 (예: 2.15T)."""
    if value_usd >= 1_000_000_000_000:
        return f"${value_usd / 1_000_000_000_000:,.2f}T"
    if value_usd >= 1_000_000_000:
        return f"${value_usd / 1_000_000_000:,.2f}B"
    if value_usd >= 1_000_000:
        return f"${value_usd / 1_000_000:,.1f}M"
    return f"${value_usd:,.0f}"
