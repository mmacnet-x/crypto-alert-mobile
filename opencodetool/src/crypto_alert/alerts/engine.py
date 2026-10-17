"""알림 감지 엔진: 시세/캔들을 받아 규칙 발동 여부를 판정한다.

- 가격 조건은 실시간 티커로, 지표 조건은 캔들로 평가한다
- 거짓→참으로 바뀌는 순간에만 1회 발동 + 쿨다운 (같은 상태 유지 시 반복 울림 방지)
- 발송(팝업/사운드/텔레그램)은 6단계에서 ``_dispatch_alert``에 붙인다
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from crypto_alert.alerts.conditions import evaluate
from crypto_alert.alerts.rules import AlertRule
from crypto_alert.exchanges.base import Candle, Ticker

__all__ = [
    "ALERT_KEY_PREFIX",
    "AlertEngine",
    "AlertEvent",
    "alert_key",
    "parse_alert_key",
]

#: 지표용 캔들 요청 키 접두사 (차트 요청 키와 구분용)
ALERT_KEY_PREFIX = "alert:"


def alert_key(exchange: str, symbol: str, interval: str) -> str:
    """지표 규칙용 캔들 요청 키 (예: ``alert:upbit:BTC/KRW:15m``)."""
    return f"{ALERT_KEY_PREFIX}{exchange}:{symbol}:{interval}"


def parse_alert_key(key: str) -> tuple[str, str, str] | None:
    """알림 캔들 키를 (거래소, 종목, 주기)로 분해한다. 아니면 None."""
    if not key.startswith(ALERT_KEY_PREFIX):
        return None
    parts = key[len(ALERT_KEY_PREFIX) :].split(":")
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


@dataclass(frozen=True, slots=True)
class AlertEvent:
    """규칙 발동 한 건 (6단계 발송기가 그대로 소비한다)."""

    rule_id: str
    exchange: str
    symbol: str
    interval: str
    condition: str
    message: str
    price: float | None
    time: datetime


class AlertEngine:
    """규칙 목록을 들고 발동 여부를 판정한다 (Qt 무의존 순수 로직)."""

    def __init__(self, rules: list[AlertRule] | tuple[AlertRule, ...] = ()) -> None:
        self._rules: list[AlertRule] = list(rules)
        self._state: dict[str, bool] = {}  # 규칙 id → 직전 평가 결과
        self._last_fired: dict[str, datetime] = {}  # 규칙 id → 마지막 발동 시각

    @property
    def rules(self) -> list[AlertRule]:
        """현재 규칙 목록 (복사본)."""
        return list(self._rules)

    def set_rules(self, rules: list[AlertRule]) -> None:
        """규칙을 교체한다. 사라진 규칙의 상태는 버린다."""
        self._rules = list(rules)
        alive = {rule.id for rule in self._rules}
        self._state = {key: value for key, value in self._state.items() if key in alive}
        self._last_fired = {key: value for key, value in self._last_fired.items() if key in alive}

    def needs_candles(self) -> list[tuple[str, str, str]]:
        """지표 계산용 캔들이 필요한 (거래소, 종목, 주기) 목록 (중복 제거)."""
        seen: set[tuple[str, str, str]] = set()
        out: list[tuple[str, str, str]] = []
        for rule in self._rules:
            if rule.enabled and rule.needs == "candles":
                key = rule.candle_key()
                if key not in seen:
                    seen.add(key)
                    out.append(key)
        return out

    def check_ticker(self, ticker: Ticker, now: datetime | None = None) -> list[AlertEvent]:
        """실시간 티커로 가격 규칙을 평가한다."""
        events: list[AlertEvent] = []
        moment = now or datetime.now(tz=UTC)
        for rule in self._rules:
            if not rule.enabled or rule.needs != "price":
                continue
            if rule.symbol != ticker.symbol:
                continue
            fired, detail = evaluate(rule.condition, rule.params, price=ticker.price)
            event = self._maybe_fire(rule, fired, detail, ticker.price, moment)
            if event is not None:
                events.append(event)
        return events

    def check_candles(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        candles: list[Candle],
        now: datetime | None = None,
    ) -> list[AlertEvent]:
        """캔들로 지표 규칙을 평가한다 (마지막 봉 기준)."""
        events: list[AlertEvent] = []
        if not candles:
            return events
        moment = now or datetime.now(tz=UTC)
        for rule in self._rules:
            if not rule.enabled or rule.needs != "candles":
                continue
            if (rule.exchange, rule.symbol, rule.interval) != (exchange, symbol, interval):
                continue
            fired, detail = evaluate(rule.condition, rule.params, candles=candles)
            event = self._maybe_fire(rule, fired, detail, candles[-1].close, moment)
            if event is not None:
                events.append(event)
        return events

    def _maybe_fire(
        self,
        rule: AlertRule,
        fired: bool,
        detail: str,
        price: float | None,
        now: datetime,
    ) -> AlertEvent | None:
        """거짓→참 전환 + 쿨다운 경과 시에만 발동한다."""
        previous = self._state.get(rule.id, False)
        self._state[rule.id] = fired
        if not fired or previous:
            return None
        last = self._last_fired.get(rule.id)
        if last is not None and (now - last).total_seconds() < rule.cooldown_sec:
            return None
        self._last_fired[rule.id] = now
        message = f"{rule.symbol} {rule.condition_label}: {detail}"
        return AlertEvent(
            rule_id=rule.id,
            exchange=rule.exchange,
            symbol=rule.symbol,
            interval=rule.interval,
            condition=rule.condition,
            message=message,
            price=price,
            time=now,
        )
