"""4단계 테스트: 보조지표 순수 계산 (MA/RSI/MACD/볼린저)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from crypto_alert.indicators import (
    DEFAULT_PARAMS,
    IndicatorParams,
    bollinger,
    cross_over,
    cross_under,
    ema,
    first_valid,
    macd,
    rsi,
    sma,
)


def test_default_params_periods() -> None:
    assert DEFAULT_PARAMS.ma_periods == (5, 20, 60)
    assert DEFAULT_PARAMS.rsi_period == 14
    assert DEFAULT_PARAMS.macd_fast < DEFAULT_PARAMS.macd_slow


def test_sma_values_and_warmup() -> None:
    got = sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert got[2:] == pytest.approx([2.0, 3.0, 4.0])


def test_sma_short_input_all_nan() -> None:
    got = sma([1.0, 2.0], 5)
    assert got.shape == (2,)
    assert np.isnan(got).all()


def test_ema_values() -> None:
    got = ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    # 시드 = 앞 period개 평균, alpha = 2/(3+1) = 0.5
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert got[2:] == pytest.approx([2.0, 3.0, 4.0])


def test_rsi_known_values() -> None:
    # period=2: 증감 변화로 수동 계산한 Wilder 값
    got = rsi([10.0, 11.0, 10.0, 11.0, 12.0], 2)
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert got[2] == pytest.approx(50.0)
    assert got[3] == pytest.approx(75.0)
    assert got[4] == pytest.approx(87.5)


def test_rsi_all_gains_is_100() -> None:
    got = rsi([1.0, 2.0, 3.0, 4.0, 5.0], 2)
    assert got[2:] == pytest.approx([100.0, 100.0, 100.0])


def test_rsi_short_input_all_nan() -> None:
    got = rsi([1.0, 2.0, 3.0], 14)
    assert np.isnan(got).all()


def test_macd_shapes_and_warmup() -> None:
    closes = np.linspace(100.0, 120.0, 60)
    line, sig, hist = macd(closes, fast=12, slow=26, signal=9)
    assert line.shape == sig.shape == hist.shape == closes.shape
    # slow(26) 전까지는 macd 라인 없음, 시그널은 그 이후 signal(9) 더 필요
    assert np.isnan(line[:25]).all()
    assert np.isfinite(line[25:]).all()
    assert np.isnan(sig[: 25 + 8]).all()
    assert np.isfinite(sig[25 + 8 :]).all()


def test_macd_hist_is_difference() -> None:
    closes = np.linspace(100.0, 130.0, 80)
    line, sig, hist = macd(closes)
    valid = np.isfinite(hist)
    assert np.allclose(hist[valid], (line - sig)[valid])


def test_bollinger_known_values() -> None:
    got_mid, got_up, got_low = bollinger([1.0, 2.0, 3.0, 4.0, 5.0], 3, 2.0)
    # idx2: 중앙=2, 모집단 표준편차 = sqrt(2/3)
    std = math.sqrt(2.0 / 3.0)
    assert got_mid[2] == pytest.approx(2.0)
    assert got_up[2] == pytest.approx(2.0 + 2.0 * std)
    assert got_low[2] == pytest.approx(2.0 - 2.0 * std)
    assert math.isnan(got_up[0])


def test_bollinger_width_matches_std() -> None:
    closes = np.linspace(100.0, 110.0, 40)
    mid, up, low = bollinger(closes, 20, 2.0)
    valid = np.isfinite(mid)
    assert np.allclose(up[valid] - mid[valid], mid[valid] - low[valid])


def test_cross_over_and_under() -> None:
    fast = [1.0, 3.0, 1.0]
    slow = [2.0, 2.0, 2.0]
    over = cross_over(fast, slow)
    under = cross_under(fast, slow)
    assert over.tolist() == [False, True, False]
    assert under.tolist() == [False, False, True]


def test_cross_ignores_nan_warmup() -> None:
    # 첫 유효값이 이미 돌파 상태여도 직전이 NaN이면 교차 아님
    first = cross_over([np.nan, np.nan, 3.0], [np.nan, np.nan, 2.0])
    assert first.tolist() == [False, False, False]
    # 유효 구간에서만 교차 판정
    over = cross_over([np.nan, np.nan, 1.0, 3.0], [np.nan, np.nan, 2.0, 2.0])
    assert over.tolist() == [False, False, False, True]


def test_first_valid() -> None:
    assert first_valid([np.nan, np.nan, 3.0]) == 2
    assert first_valid([1.0, 2.0]) == 0
    assert first_valid([np.nan]) is None


def test_param_validation() -> None:
    with pytest.raises(ValueError):
        sma([1.0, 2.0], 0)
    with pytest.raises(ValueError):
        ema([1.0, 2.0], -1)
    with pytest.raises(ValueError):
        rsi([1.0, 2.0], 0)
    with pytest.raises(ValueError):
        macd([1.0] * 30, fast=0)
    with pytest.raises(ValueError):
        bollinger([1.0] * 30, period=0)
    with pytest.raises(ValueError):
        cross_over([1.0, 2.0], [1.0])


def test_params_immutable() -> None:
    params = IndicatorParams()
    with pytest.raises(AttributeError):  # frozen dataclass
        params.rsi_period = 30  # type: ignore[misc]


def test_rsi_flat_series_is_nan() -> None:
    """변동 없으면 판단 불가(NaN) — 과매수/과매도 오판 방지."""
    got = rsi([100.0] * 20, 14)
    assert math.isnan(got[14])


def test_cross_shape_mismatch_and_short() -> None:
    with pytest.raises(ValueError):
        cross_under([1.0, 2.0], [1.0])
    assert cross_under([1.0], [1.0]).tolist() == [False]
    assert cross_over([1.0], [1.0]).tolist() == [False]
