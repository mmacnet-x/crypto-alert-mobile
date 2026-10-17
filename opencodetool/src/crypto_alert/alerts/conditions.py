"""알림 조건 레지스트리: 가격 돌파 + 지표 신호.

새 조건을 추가하려면 ``CONDITIONS``에 :class:`ConditionSpec` 한 줄을 등록하면
된다 (평가 함수 + 파라미터 정의 + 설명). UI 다이얼로그와 규칙 저장은 이
레지스트리만 보고 동작하므로 다른 파일을 고칠 필요가 없다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crypto_alert.exchanges.base import Candle
from crypto_alert.formatting import format_price
from crypto_alert.indicators import bollinger, cross_over, macd, rsi, sma

__all__ = [
    "CONDITIONS",
    "ConditionError",
    "ConditionSpec",
    "ParamDef",
    "describe_rule",
    "evaluate",
    "validate_params",
]

# 평가 함수가 받는 형태: 가격 조건은 현재가, 캔들 조건은 캔들 목록.
# 반환: (발동 여부, 상세 설명).
PriceEval = Callable[[float, dict[str, float | int]], tuple[bool, str]]
CandlesEval = Callable[["list[Candle]", dict[str, float | int]], tuple[bool, str]]


class ConditionError(ValueError):
    """알 수 없는 조건이거나 파라미터가 잘못되었을 때 발생."""


@dataclass(frozen=True, slots=True)
class ParamDef:
    """조건 파라미터 한 개의 정의 (UI 입력칸 자동 생성용)."""

    key: str
    label: str
    kind: str  # "price" | "int" | "float"
    default: float | int
    minimum: float | int
    maximum: float | int


@dataclass(frozen=True, slots=True)
class ConditionSpec:
    """알림 조건 한 종류의 정의."""

    key: str
    label: str
    needs: str  # "price" (실시간가) | "candles" (지표 계산용)
    params: tuple[ParamDef, ...] = ()
    short: Callable[[dict[str, float | int]], str] | None = None
    eval_price: PriceEval | None = None
    eval_candles: CandlesEval | None = None


def _closes(candles: list[Candle]) -> list[float]:
    return [c.close for c in candles]


def _eval_price_above(price: float, p: dict[str, float | int]) -> tuple[bool, str]:
    target = float(p["target"])
    return price >= target, f"현재가 {format_price(price)} (목표 {format_price(target)})"


def _eval_price_below(price: float, p: dict[str, float | int]) -> tuple[bool, str]:
    target = float(p["target"])
    return price <= target, f"현재가 {format_price(price)} (목표 {format_price(target)})"


def _ma_values(closes: list[float], fast: int, slow: int) -> tuple[float | None, float | None]:
    """마지막 봉의 단기/장기 이동평균 (웜업 중이면 None)."""
    import numpy as np

    fast_arr = sma(closes, fast)
    slow_arr = sma(closes, slow)
    fast_last = fast_arr[-1] if fast_arr.size else float("nan")
    slow_last = slow_arr[-1] if slow_arr.size else float("nan")
    if not (np.isfinite(fast_last) and np.isfinite(slow_last)):
        return None, None
    return float(fast_last), float(slow_last)


def _eval_golden_cross(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    import numpy as np

    closes = _closes(candles)
    fast, slow = int(p["fast"]), int(p["slow"])
    if len(closes) < slow + 1:
        return False, "캔들 부족"
    crossed = cross_over(sma(closes, fast), sma(closes, slow))
    fast_last, slow_last = _ma_values(closes, fast, slow)
    state = f"MA{fast} {format_price(fast_last or 0)} / MA{slow} {format_price(slow_last or 0)}"
    if fast_last is None:
        return False, "지표 웜업 중"
    if bool(crossed[-1]):
        return True, f"골든크로스 발생 ({state})"
    arrow = "↑" if np.isfinite(fast_last) and fast_last > (slow_last or 0) else "↓"
    return False, f"{state} {arrow}"


def _eval_dead_cross(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    import numpy as np

    closes = _closes(candles)
    fast, slow = int(p["fast"]), int(p["slow"])
    if len(closes) < slow + 1:
        return False, "캔들 부족"
    from crypto_alert.indicators import cross_under

    crossed = cross_under(sma(closes, fast), sma(closes, slow))
    fast_last, slow_last = _ma_values(closes, fast, slow)
    state = f"MA{fast} {format_price(fast_last or 0)} / MA{slow} {format_price(slow_last or 0)}"
    if fast_last is None:
        return False, "지표 웜업 중"
    if bool(crossed[-1]):
        return True, f"데드크로스 발생 ({state})"
    arrow = "↓" if np.isfinite(fast_last) and fast_last < (slow_last or 0) else "↑"
    return False, f"{state} {arrow}"


def _rsi_last(closes: list[float], period: int) -> float | None:
    import numpy as np

    values = rsi(closes, period)
    last = values[-1] if values.size else float("nan")
    return float(last) if np.isfinite(last) else None


def _eval_rsi_overbought(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    closes = _closes(candles)
    period, threshold = int(p["period"]), float(p["threshold"])
    if len(closes) <= period:
        return False, "캔들 부족"
    value = _rsi_last(closes, period)
    if value is None:
        return False, "지표 웜업 중"
    return value >= threshold, f"RSI({period}) {value:.1f} (기준 {threshold:g})"


def _eval_rsi_oversold(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    closes = _closes(candles)
    period, threshold = int(p["period"]), float(p["threshold"])
    if len(closes) <= period:
        return False, "캔들 부족"
    value = _rsi_last(closes, period)
    if value is None:
        return False, "지표 웜업 중"
    return value <= threshold, f"RSI({period}) {value:.1f} (기준 {threshold:g})"


def _macd_last(
    closes: list[float], fast: int, slow: int, signal: int
) -> tuple[float | None, float | None]:
    import numpy as np

    line, sig, _hist = macd(closes, fast, slow, signal)
    line_last = line[-1] if line.size else float("nan")
    sig_last = sig[-1] if sig.size else float("nan")
    if not (np.isfinite(line_last) and np.isfinite(sig_last)):
        return None, None
    return float(line_last), float(sig_last)


def _eval_macd_bullish(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    closes = _closes(candles)
    fast, slow, signal = int(p["fast"]), int(p["slow"]), int(p["signal"])
    if len(closes) < slow + signal:
        return False, "캔들 부족"
    line, sig, _hist = macd(closes, fast, slow, signal)
    line_last, sig_last = _macd_last(closes, fast, slow, signal)
    if line_last is None or sig_last is None:
        return False, "지표 웜업 중"
    if bool(cross_over(line, sig)[-1]):
        return True, f"MACD 상향 돌파 (MACD {line_last:.2f} > 시그널 {sig_last:.2f})"
    return False, f"MACD {line_last:.2f} / 시그널 {sig_last:.2f}"


def _eval_macd_bearish(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    closes = _closes(candles)
    fast, slow, signal = int(p["fast"]), int(p["slow"]), int(p["signal"])
    if len(closes) < slow + signal:
        return False, "캔들 부족"
    from crypto_alert.indicators import cross_under

    line, sig, _hist = macd(closes, fast, slow, signal)
    line_last, sig_last = _macd_last(closes, fast, slow, signal)
    if line_last is None or sig_last is None:
        return False, "지표 웜업 중"
    if bool(cross_under(line, sig)[-1]):
        return True, f"MACD 하향 돌파 (MACD {line_last:.2f} < 시그널 {sig_last:.2f})"
    return False, f"MACD {line_last:.2f} / 시그널 {sig_last:.2f}"


def _eval_bb_breakout_up(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    import numpy as np

    closes = _closes(candles)
    period, mult = int(p["period"]), float(p["mult"])
    if len(closes) < period:
        return False, "캔들 부족"
    _mid, upper, _lower = bollinger(closes, period, mult)
    band = upper[-1] if upper.size else float("nan")
    if not np.isfinite(band):
        return False, "지표 웜업 중"
    close = closes[-1]
    detail = f"종가 {format_price(close)} (상단 {format_price(float(band))})"
    return close > float(band), detail


def _eval_bb_breakout_down(candles: list[Candle], p: dict[str, float | int]) -> tuple[bool, str]:
    import numpy as np

    closes = _closes(candles)
    period, mult = int(p["period"]), float(p["mult"])
    if len(closes) < period:
        return False, "캔들 부족"
    _mid, _upper, lower = bollinger(closes, period, mult)
    band = lower[-1] if lower.size else float("nan")
    if not np.isfinite(band):
        return False, "지표 웜업 중"
    close = closes[-1]
    detail = f"종가 {format_price(close)} (하단 {format_price(float(band))})"
    return close < float(band), detail


CONDITIONS: dict[str, ConditionSpec] = {
    "price_above": ConditionSpec(
        key="price_above",
        label="가격 ≥ 목표",
        needs="price",
        params=(ParamDef("target", "목표가", "price", 0.0, 0.0, 1e15),),
        short=lambda p: f"≥ {format_price(float(p['target']))}",
        eval_price=_eval_price_above,
    ),
    "price_below": ConditionSpec(
        key="price_below",
        label="가격 ≤ 목표",
        needs="price",
        params=(ParamDef("target", "목표가", "price", 0.0, 0.0, 1e15),),
        short=lambda p: f"≤ {format_price(float(p['target']))}",
        eval_price=_eval_price_below,
    ),
    "golden_cross": ConditionSpec(
        key="golden_cross",
        label="골든크로스",
        needs="candles",
        params=(
            ParamDef("fast", "단기 MA", "int", 5, 2, 200),
            ParamDef("slow", "장기 MA", "int", 20, 3, 200),
        ),
        short=lambda p: f"MA{int(p['fast'])}↑MA{int(p['slow'])}",
        eval_candles=_eval_golden_cross,
    ),
    "dead_cross": ConditionSpec(
        key="dead_cross",
        label="데드크로스",
        needs="candles",
        params=(
            ParamDef("fast", "단기 MA", "int", 5, 2, 200),
            ParamDef("slow", "장기 MA", "int", 20, 3, 200),
        ),
        short=lambda p: f"MA{int(p['fast'])}↓MA{int(p['slow'])}",
        eval_candles=_eval_dead_cross,
    ),
    "rsi_overbought": ConditionSpec(
        key="rsi_overbought",
        label="RSI 과매수",
        needs="candles",
        params=(
            ParamDef("period", "RSI 기간", "int", 14, 2, 100),
            ParamDef("threshold", "기준", "float", 70.0, 0.0, 100.0),
        ),
        short=lambda p: f"RSI({int(p['period'])})≥{float(p['threshold']):g}",
        eval_candles=_eval_rsi_overbought,
    ),
    "rsi_oversold": ConditionSpec(
        key="rsi_oversold",
        label="RSI 과매도",
        needs="candles",
        params=(
            ParamDef("period", "RSI 기간", "int", 14, 2, 100),
            ParamDef("threshold", "기준", "float", 30.0, 0.0, 100.0),
        ),
        short=lambda p: f"RSI({int(p['period'])})≤{float(p['threshold']):g}",
        eval_candles=_eval_rsi_oversold,
    ),
    "macd_bullish": ConditionSpec(
        key="macd_bullish",
        label="MACD 상향",
        needs="candles",
        params=(
            ParamDef("fast", "단기", "int", 12, 2, 100),
            ParamDef("slow", "장기", "int", 26, 3, 200),
            ParamDef("signal", "시그널", "int", 9, 2, 100),
        ),
        short=lambda p: "MACD↑시그널",
        eval_candles=_eval_macd_bullish,
    ),
    "macd_bearish": ConditionSpec(
        key="macd_bearish",
        label="MACD 하향",
        needs="candles",
        params=(
            ParamDef("fast", "단기", "int", 12, 2, 100),
            ParamDef("slow", "장기", "int", 26, 3, 200),
            ParamDef("signal", "시그널", "int", 9, 2, 100),
        ),
        short=lambda p: "MACD↓시그널",
        eval_candles=_eval_macd_bearish,
    ),
    "bb_breakout_up": ConditionSpec(
        key="bb_breakout_up",
        label="BB 상단돌파",
        needs="candles",
        params=(
            ParamDef("period", "기간", "int", 20, 2, 200),
            ParamDef("mult", "표준편차 배수", "float", 2.0, 0.1, 5.0),
        ),
        short=lambda p: f"종가>BB상단({int(p['period'])},{float(p['mult']):g}σ)",
        eval_candles=_eval_bb_breakout_up,
    ),
    "bb_breakout_down": ConditionSpec(
        key="bb_breakout_down",
        label="BB 하단돌파",
        needs="candles",
        params=(
            ParamDef("period", "기간", "int", 20, 2, 200),
            ParamDef("mult", "표준편차 배수", "float", 2.0, 0.1, 5.0),
        ),
        short=lambda p: f"종가<BB하단({int(p['period'])},{float(p['mult']):g}σ)",
        eval_candles=_eval_bb_breakout_down,
    ),
}


def validate_params(condition: str, params: dict[str, float | int]) -> dict[str, float | int]:
    """파라미터를 검증·보정한다 (기본값 채움 + 범위 확인)."""
    spec = CONDITIONS.get(condition)
    if spec is None:
        raise ConditionError(f"알 수 없는 조건: {condition!r}")
    result: dict[str, float | int] = {}
    for param in spec.params:
        raw = params.get(param.key, param.default)
        try:
            value: float | int = int(raw) if param.kind == "int" else float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ConditionError(f"[{param.label}] 숫자가 아닙니다: {raw!r}") from exc
        if isinstance(value, bool) or not (param.minimum <= value <= param.maximum):
            raise ConditionError(
                f"[{param.label}] 범위를 벗어났습니다: {raw!r} "
                f"(가능: {param.minimum}~{param.maximum})"
            )
        if param.kind == "price" and value <= 0:
            raise ConditionError(f"[{param.label}] 목표가는 0보다 커야 합니다: {raw!r}")
        result[param.key] = value
    if condition in ("golden_cross", "dead_cross") and result["fast"] >= result["slow"]:
        raise ConditionError("단기 MA는 장기 MA보다 작아야 합니다")
    if condition in ("macd_bullish", "macd_bearish") and result["fast"] >= result["slow"]:
        raise ConditionError("MACD 단기는 장기보다 작아야 합니다")
    return result


def evaluate(
    condition: str,
    params: dict[str, float | int],
    price: float | None = None,
    candles: list[Candle] | None = None,
) -> tuple[bool, str]:
    """조건 하나를 평가한다. 반환: (발동 여부, 상세 설명)."""
    spec = CONDITIONS.get(condition)
    if spec is None:
        raise ConditionError(f"알 수 없는 조건: {condition!r}")
    checked = validate_params(condition, params)
    if spec.needs == "price":
        if price is None or spec.eval_price is None:
            raise ConditionError(f"[{condition}] 현재가가 필요합니다")
        return spec.eval_price(price, checked)
    if not candles or spec.eval_candles is None:
        return False, "캔들 없음"
    return spec.eval_candles(candles, checked)


def describe_rule(condition: str, params: dict[str, float | int]) -> str:
    """규칙 목록에 표시할 짧은 설명 (예: ≥ 115,000,000.00)."""
    spec = CONDITIONS.get(condition)
    if spec is None or spec.short is None:
        return condition
    try:
        return spec.short(validate_params(condition, params))
    except ConditionError:
        return condition
