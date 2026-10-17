"""보유종목: 사용자가 직접 입력하는 수동 포지션 관리 (JSON 저장)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from crypto_alert.paths import app_data_dir

__all__ = [
    "Holding",
    "PositionValue",
    "holdings_path",
    "load_holdings",
    "save_holdings",
    "value_of",
]


def holdings_path() -> Path:
    """보유종목 JSON 경로를 반환한다."""
    return app_data_dir() / "holdings.json"


@dataclass(frozen=True, slots=True)
class Holding:
    """사용자가 입력한 보유 포지션 한 건."""

    symbol: str  # 표준 심볼 (예: BTC/KRW)
    quantity: float  # 보유 수량
    avg_price: float  # 평균 매수가 (심볼 통화 기준)


@dataclass(frozen=True, slots=True)
class PositionValue:
    """평가 결과."""

    value: float  # 평가금액
    pnl: float  # 손익금액
    pnl_rate: float  # 손익률 (소수, 0.05 = +5%)


def load_holdings(path: Path | None = None) -> list[Holding]:
    """보유종목 목록을 읽는다 (파일 없으면 빈 목록)."""
    target = path or holdings_path()
    if not target.exists():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    holdings: list[Holding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        quantity = item.get("quantity")
        avg_price = item.get("avg_price")
        if not isinstance(symbol, str) or not symbol:
            continue
        if not isinstance(quantity, (int, float)) or not isinstance(avg_price, (int, float)):
            continue
        if quantity < 0 or avg_price < 0:
            continue
        holdings.append(
            Holding(symbol=symbol, quantity=float(quantity), avg_price=float(avg_price))
        )
    return holdings


def save_holdings(holdings: list[Holding], path: Path | None = None) -> None:
    """보유종목 목록을 파일에 저장한다."""
    target = path or holdings_path()
    payload = [
        {"symbol": item.symbol, "quantity": item.quantity, "avg_price": item.avg_price}
        for item in holdings
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def value_of(holding: Holding, current_price: float) -> PositionValue:
    """현재가 기준 평가금액/손익/손익률을 계산한다."""
    value = holding.quantity * current_price
    cost = holding.quantity * holding.avg_price
    pnl = value - cost
    pnl_rate = (pnl / cost) if cost > 0 else 0.0
    return PositionValue(value=value, pnl=pnl, pnl_rate=pnl_rate)
