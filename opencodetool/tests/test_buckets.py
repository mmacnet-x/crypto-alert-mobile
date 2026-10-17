"""3단계 테스트: 캔들 구간(bucket) 계산."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_alert.buckets import bucket_start, interval_seconds, is_new_bucket
from crypto_alert.exchanges.base import Interval


def test_bucket_start_15m() -> None:
    t = datetime(2026, 10, 8, 13, 37, 45, tzinfo=UTC)
    assert bucket_start(t, Interval.M15) == datetime(2026, 10, 8, 13, 30, tzinfo=UTC)


def test_bucket_start_4h() -> None:
    t = datetime(2026, 10, 8, 13, 37, 45, tzinfo=UTC)
    assert bucket_start(t, Interval.H4) == datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def test_bucket_start_1d() -> None:
    t = datetime(2026, 10, 8, 13, 37, 45, tzinfo=UTC)
    assert bucket_start(t, Interval.D1) == datetime(2026, 10, 8, 0, 0, tzinfo=UTC)


def test_bucket_start_1w_is_monday() -> None:
    # 2026-10-08은 목요일 → 같은 주의 월요일(10-05)
    t = datetime(2026, 10, 8, 13, 37, 45, tzinfo=UTC)
    assert bucket_start(t, Interval.W1) == datetime(2026, 10, 5, 0, 0, tzinfo=UTC)


def test_bucket_start_1m() -> None:
    t = datetime(2026, 10, 8, 13, 37, 45, tzinfo=UTC)
    assert bucket_start(t, Interval.MN) == datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


def test_naive_datetime_treated_as_utc() -> None:
    naive = datetime(2026, 10, 8, 13, 37, 45)  # noqa: DTZ001 — 의도적 naive 입력 테스트
    assert bucket_start(naive, Interval.M15) == datetime(2026, 10, 8, 13, 30, tzinfo=UTC)


def test_is_new_bucket() -> None:
    last = datetime(2026, 10, 8, 13, 30, tzinfo=UTC)
    # 13:30 캔들은 13:30~13:44:59 구간 → 같은 구간 내 틱은 새 캔들이 아님
    assert not is_new_bucket(datetime(2026, 10, 8, 13, 44, tzinfo=UTC), last, Interval.M15)
    # 13:45부터는 다음 구간
    assert is_new_bucket(datetime(2026, 10, 8, 13, 45, tzinfo=UTC), last, Interval.M15)


def test_interval_seconds() -> None:
    assert interval_seconds(Interval.M15) == 900
    assert interval_seconds(Interval.H4) == 14400
    assert interval_seconds(Interval.D1) == 86400
    assert interval_seconds(Interval.W1) == 7 * 86400


def test_bucket_start_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="지원하지 않는 주기"):
        bucket_start(datetime(2026, 10, 8, 13, 30, tzinfo=UTC), "1m")  # type: ignore[arg-type]
