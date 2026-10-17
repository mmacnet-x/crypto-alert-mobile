"""알림 규칙 데이터 모델 (JSON 저장용, UI·엔진 공용)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from crypto_alert.alerts.conditions import (
    CONDITIONS,
    ConditionError,
    describe_rule,
    validate_params,
)
from crypto_alert.config import EXCHANGES
from crypto_alert.exchanges.base import Interval

__all__ = ["AlertRule", "RuleError", "new_rule"]

#: 발동 후 같은 규칙이 다시 울리기까지 최소 간격 기본값 (초)
DEFAULT_COOLDOWN_SEC = 600


class RuleError(ValueError):
    """규칙 내용이 잘못되었을 때 발생."""


@dataclass(slots=True)
class AlertRule:
    """알림 규칙 하나 (거래소/종목/주기 + 조건 + 파라미터)."""

    id: str
    exchange: str
    symbol: str
    interval: str  # Interval 값 ("15m" 등)
    condition: str  # CONDITIONS 키
    params: dict[str, float | int] = field(default_factory=dict)
    enabled: bool = True
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC

    @property
    def needs(self) -> str:
        """ "price" (실시간가) 또는 "candles" (지표 계산용)."""
        return CONDITIONS[self.condition].needs

    @property
    def condition_label(self) -> str:
        """조건의 한글 이름."""
        return CONDITIONS[self.condition].label

    def candle_key(self) -> tuple[str, str, str]:
        """지표용 캔들 식별자 (거래소, 종목, 주기)."""
        return (self.exchange, self.symbol, self.interval)

    def short(self) -> str:
        """목록에 표시할 짧은 설명."""
        return describe_rule(self.condition, self.params)

    def to_dict(self) -> dict[str, Any]:
        """JSON 저장용 딕셔너리."""
        return {
            "id": self.id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "interval": self.interval,
            "condition": self.condition,
            "params": dict(self.params),
            "enabled": self.enabled,
            "cooldown_sec": self.cooldown_sec,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertRule:
        """딕셔너리에서 규칙을 복원한다 (검증 포함)."""
        if not isinstance(data, dict):
            raise RuleError(f"규칙 형식이 잘못되었습니다: {data!r}")
        rule_id = str(data.get("id") or uuid.uuid4().hex[:8])
        exchange = str(data.get("exchange", ""))
        if exchange not in EXCHANGES:
            raise RuleError(f"알 수 없는 거래소: {exchange!r}")
        symbol = str(data.get("symbol", "")).strip()
        if not symbol:
            raise RuleError("종목이 비어 있습니다")
        try:
            interval = Interval.parse(str(data.get("interval", ""))).value
        except ValueError as exc:
            raise RuleError(str(exc)) from exc
        condition = str(data.get("condition", ""))
        if condition not in CONDITIONS:
            raise RuleError(f"알 수 없는 조건: {condition!r}")
        raw_params = data.get("params", {})
        if not isinstance(raw_params, dict):
            raise RuleError(f"파라미터 형식이 잘못되었습니다: {raw_params!r}")
        try:
            params = validate_params(condition, dict(raw_params))
        except ConditionError as exc:
            raise RuleError(f"파라미터 오류: {exc}") from exc
        try:
            cooldown = int(data.get("cooldown_sec", DEFAULT_COOLDOWN_SEC))
        except (TypeError, ValueError) as exc:
            raise RuleError(f"쿨다운이 잘못되었습니다: {data.get('cooldown_sec')!r}") from exc
        if not 0 <= cooldown <= 86_400:
            raise RuleError(f"쿨다운 범위 초과: {cooldown} (가능: 0~86400초)")
        return cls(
            id=rule_id,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            condition=condition,
            params=params,
            enabled=bool(data.get("enabled", True)),
            cooldown_sec=cooldown,
        )


def new_rule(
    exchange: str,
    symbol: str,
    interval: str,
    condition: str,
    params: dict[str, float | int] | None = None,
    enabled: bool = True,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
) -> AlertRule:
    """새 규칙을 만든다 (id 자동 발급, 검증 포함)."""
    return AlertRule.from_dict(
        {
            "id": uuid.uuid4().hex[:8],
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "condition": condition,
            "params": dict(params or {}),
            "enabled": enabled,
            "cooldown_sec": cooldown_sec,
        }
    )
