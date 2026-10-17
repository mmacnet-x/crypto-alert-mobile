"""시가총액 순위 자체 계산 (외부 API 불필요).

시가총액 = 유통공급량(supplies.json) x USD 가격
- 바이낸스 USDT 페어 가격은 그대로 USD로 사용
- 업비트 KRW 페어 가격은 환율(USDT/KRW)로 나눠 USD 환산
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from crypto_alert.exchanges.base import Ticker
from crypto_alert.paths import resource_path

__all__ = ["MarketRank", "compute_ranking", "load_supplies", "supplies_path"]

# 다른 거래소에서 다른 티커를 쓰는 동일 자산 매핑
_SUPPLY_ALIASES: Final[dict[str, str]] = {"BTTC": "BTT"}

DEFAULT_USD_KRW: Final[float] = 1350.0  # 환율 미수신 시 기본값


def supplies_path() -> Path:
    """유통공급량 JSON 경로를 반환한다."""
    return resource_path("supplies.json")


def load_supplies(path: Path | None = None) -> dict[str, float]:
    """유통공급량 표를 읽는다 ('_' 시작 키는 무시)."""
    target = path or supplies_path()
    if not target.exists():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        if isinstance(value, (int, float)) and value > 0:
            result[str(key).upper()] = float(value)
    return result


@dataclass(frozen=True, slots=True)
class MarketRank:
    """시가총액 순위 한 항목."""

    base: str  # 기본 자산 (예: BTC)
    symbol: str  # 가격 근거 심볼 (예: BTC/USDT)
    exchange: str  # 가격 근거 거래소
    price_usd: float  # USD 환산 가격
    market_cap_usd: float  # 시가총액 (USD)
    change_rate: float  # 24h 등락률 (소수)
    supply: float  # 유통공급량


def _supply_of(base: str, supplies: Mapping[str, float]) -> float | None:
    for key in (base, _SUPPLY_ALIASES.get(base, "")):
        if key and key in supplies:
            return supplies[key]
    return None


def compute_ranking(
    tickers: Mapping[str, Ticker],
    supplies: Mapping[str, float],
    usd_krw: float = DEFAULT_USD_KRW,
    exchanges: Mapping[str, str] | None = None,
) -> list[MarketRank]:
    """티커 캐시에서 시가총액 순위를 계산한다 (내림차순).

    동일 자산이 두 거래소에 있으면 USDT(달러) 가격을 우선 사용하고,
    공급량이 없는 자산은 제외한다.
    """
    fx = usd_krw if usd_krw > 0 else DEFAULT_USD_KRW
    # base -> (is_usd, ticker, exchange)
    chosen: dict[str, tuple[bool, Ticker, str]] = {}
    for symbol, ticker in tickers.items():
        base, _, quote = symbol.partition("/")
        if exchanges is not None and symbol in exchanges:
            exchange = exchanges[symbol]
        else:
            exchange = "upbit" if quote == "KRW" else "binance" if quote == "USDT" else "other"
        is_usd = quote == "USDT"
        current = chosen.get(base)
        if current is None or (is_usd and not current[0]):
            chosen[base] = (is_usd, ticker, exchange)

    ranks: list[MarketRank] = []
    for base, (is_usd, ticker, exchange) in chosen.items():
        supply = _supply_of(base, supplies)
        if supply is None or ticker.price <= 0:
            continue
        price_usd = ticker.price if is_usd else ticker.price / fx
        ranks.append(
            MarketRank(
                base=base,
                symbol=ticker.symbol,
                exchange=exchange,
                price_usd=price_usd,
                market_cap_usd=supply * price_usd,
                change_rate=ticker.change_rate,
                supply=supply,
            )
        )
    ranks.sort(key=lambda item: item.market_cap_usd, reverse=True)
    return ranks
