"""보조지표 순수 계산: MA / 볼린저밴드 / RSI / MACD.

UI와 무관한 순수 함수로 구성한다 (5단계 알림 조건에서 신호 판정 재사용).
모든 함수는 앞부분 웜업 구간을 NaN으로 채워 같은 길이의 배열을 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

__all__ = [
    "DEFAULT_PARAMS",
    "IndicatorParams",
    "bollinger",
    "cross_over",
    "cross_under",
    "ema",
    "first_valid",
    "macd",
    "rsi",
    "sma",
]


@dataclass(frozen=True, slots=True)
class IndicatorParams:
    """지표 파라미터 (이후 설정 UI에서 교체 가능하도록 분리)."""

    ma_periods: tuple[int, ...] = (5, 20, 60)
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


DEFAULT_PARAMS = IndicatorParams()


def _as_array(values: npt.ArrayLike) -> FloatArray:
    return np.asarray(values, dtype=np.float64)


def _check_period(period: int, name: str) -> None:
    if period < 1:
        raise ValueError(f"{name}는 1 이상이어야 합니다: {period}")


def sma(values: npt.ArrayLike, period: int) -> FloatArray:
    """단순이동평균 (웜업 구간 NaN)."""
    _check_period(period, "sma period")
    arr = _as_array(values)
    series = pd.Series(arr)
    return series.rolling(window=period, min_periods=period).mean().to_numpy(dtype=np.float64)


def ema(values: npt.ArrayLike, period: int) -> FloatArray:
    """지수이동평균: SMA로 시드 후 지수 가중 (웜업 구간 NaN)."""
    _check_period(period, "ema period")
    arr = _as_array(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if arr.size < period:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = arr[:period].mean()
    for i in range(period, arr.size):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0.0 and avg_loss == 0.0:
        return float("nan")  # 변동 없음 → 판단 불가
    if avg_loss == 0.0:
        return 100.0
    if avg_gain == 0.0:
        return 0.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def rsi(values: npt.ArrayLike, period: int = 14) -> FloatArray:
    """RSI: Wilder 방식 (초기값은 앞 period개 평균으로 시드)."""
    _check_period(period, "rsi period")
    arr = _as_array(values)
    out = np.full(arr.shape, np.nan, dtype=np.float64)
    if arr.size <= period:
        return out
    changes = np.diff(arr)
    gains = np.clip(changes, 0.0, None)
    losses = np.clip(-changes, 0.0, None)
    avg_gain = float(gains[:period].mean())
    avg_loss = float(losses[:period].mean())
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, arr.size):
        avg_gain = (avg_gain * (period - 1) + float(gains[i - 1])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i - 1])) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def macd(
    values: npt.ArrayLike,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """MACD: (macd선, 시그널선, 히스토그램) 반환."""
    _check_period(fast, "macd fast")
    _check_period(slow, "macd slow")
    _check_period(signal, "macd signal")
    arr = _as_array(values)
    line = ema(arr, fast) - ema(arr, slow)
    sig = np.full(arr.shape, np.nan, dtype=np.float64)
    start = first_valid(line)
    if start is not None:
        sig[start:] = ema(line[start:], signal)
    hist = line - sig
    return line, sig, hist


def bollinger(
    values: npt.ArrayLike,
    period: int = 20,
    std_mult: float = 2.0,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """볼린저밴드: (중앙선, 상단, 하단) 반환. 표준편차는 모집단(ddof=0)."""
    _check_period(period, "bollinger period")
    arr = _as_array(values)
    mid = sma(arr, period)
    std = pd.Series(arr).rolling(window=period, min_periods=period).std(ddof=0)
    std_arr = std.to_numpy(dtype=np.float64)
    return mid, mid + std_mult * std_arr, mid - std_mult * std_arr


def first_valid(values: npt.ArrayLike) -> int | None:
    """처음으로 유한값이 나오는 인덱스 (없으면 None)."""
    arr = _as_array(values)
    finite = np.flatnonzero(np.isfinite(arr))
    return int(finite[0]) if finite.size else None


def cross_over(fast: npt.ArrayLike, slow: npt.ArrayLike) -> BoolArray:
    """fast가 slow를 위로 뚫는 지점(골든크로스) True."""
    f = _as_array(fast)
    s = _as_array(slow)
    if f.shape != s.shape:
        raise ValueError("교차 판정은 같은 길이 배열이 필요합니다")
    out = np.zeros(f.shape, dtype=bool)
    if f.size < 2:
        return out
    finite = np.isfinite(f) & np.isfinite(s)
    above = f > s
    out[1:] = finite[:-1] & finite[1:] & above[1:] & ~above[:-1]
    return out


def cross_under(fast: npt.ArrayLike, slow: npt.ArrayLike) -> BoolArray:
    """fast가 slow를 아래로 뚫는 지점(데드크로스) True."""
    f = _as_array(fast)
    s = _as_array(slow)
    if f.shape != s.shape:
        raise ValueError("교차 판정은 같은 길이 배열이 필요합니다")
    out = np.zeros(f.shape, dtype=bool)
    if f.size < 2:
        return out
    finite = np.isfinite(f) & np.isfinite(s)
    below = f < s
    out[1:] = finite[:-1] & finite[1:] & below[1:] & ~below[:-1]
    return out
