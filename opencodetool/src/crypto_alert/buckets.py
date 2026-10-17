"""캔들 구간(bucket) 계산: 실시간 갱신 시 새 캔들 경계 판정에 사용한다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_alert.exchanges.base import Interval

__all__ = ["bucket_start", "interval_seconds", "is_new_bucket"]

# 주기별 대략적 초 단위 (막대 폭/근사값, 1월은 30일로 근사)
_NOMINAL_SECONDS: dict[Interval, int] = {
    Interval.M15: 15 * 60,
    Interval.H4: 4 * 60 * 60,
    Interval.D1: 24 * 60 * 60,
    Interval.W1: 7 * 24 * 60 * 60,
    Interval.MN: 30 * 24 * 60 * 60,
}


def interval_seconds(interval: Interval) -> int:
    """주기의 대략적 길이(초)를 반환한다 (막대 폭 계산용)."""
    return _NOMINAL_SECONDS[interval]


def bucket_start(time: datetime, interval: Interval) -> datetime:
    """주어진 시각이 속한 캔들 구간의 시작 시각(UTC)을 반환한다."""
    t = time if time.tzinfo is not None else time.replace(tzinfo=UTC)
    t = t.astimezone(UTC)
    if interval is Interval.M15:
        minute = (t.minute // 15) * 15
        return t.replace(minute=minute, second=0, microsecond=0)
    if interval is Interval.H4:
        hour = (t.hour // 4) * 4
        return t.replace(hour=hour, minute=0, second=0, microsecond=0)
    if interval is Interval.D1:
        return t.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval is Interval.W1:
        day = t.replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday())  # 주 시작 = 월요일
    if interval is Interval.MN:
        return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"지원하지 않는 주기입니다: {interval}")


def is_new_bucket(ticker_time: datetime, last_candle_time: datetime, interval: Interval) -> bool:
    """티커 시각이 마지막 캔들의 구간을 넘어섰으면 True (새 캔들 필요)."""
    return bucket_start(ticker_time, interval) > bucket_start(last_candle_time, interval)
