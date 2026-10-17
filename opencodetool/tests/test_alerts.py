"""5단계 테스트: 알림 조건 평가 + 감지 엔진 + 규칙 저장 + 규칙 UI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_alert.alerts import (
    CONDITIONS,
    AlertEngine,
    ConditionError,
    RuleError,
    RulesError,
    describe_rule,
    evaluate,
    load_rules,
    new_rule,
    save_rules,
    validate_params,
)
from crypto_alert.alerts.engine import alert_key, parse_alert_key
from crypto_alert.exchanges.base import Candle, Interval, Ticker

BASE = datetime(2026, 10, 8, tzinfo=UTC)


def _candles(
    closes: list[float],
    symbol: str = "BTC/KRW",
    interval: Interval = Interval.M15,
) -> list[Candle]:
    out = []
    for i, close in enumerate(closes):
        out.append(
            Candle(
                symbol=symbol,
                interval=interval,
                time=BASE + timedelta(minutes=15 * i),
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=10.0,
            )
        )
    return out


def _ticker(symbol: str, price: float) -> Ticker:
    return Ticker(symbol=symbol, price=price, change_rate=0.0, volume=1.0, time=BASE)


def _cross_index(closes: list[float], kind: str) -> int:
    """MA(5/20) 교차가 처음 일어나는 인덱스 (없으면 AssertionError)."""
    from crypto_alert.indicators import cross_over, cross_under, sma

    fast = sma(closes, 5)
    slow = sma(closes, 20)
    flags = cross_over(fast, slow) if kind == "golden" else cross_under(fast, slow)
    for i, flag in enumerate(flags):
        if bool(flag):
            return i
    raise AssertionError(f"{kind} 교차가 없음")


def test_price_conditions() -> None:
    fired, detail = evaluate("price_above", {"target": 100.0}, price=110.0)
    assert fired and "110" in detail
    fired, _detail = evaluate("price_above", {"target": 100.0}, price=90.0)
    assert not fired
    fired, _detail = evaluate("price_below", {"target": 100.0}, price=90.0)
    assert fired
    fired, _detail = evaluate("price_below", {"target": 100.0}, price=110.0)
    assert not fired


def test_validate_params_defaults_and_errors() -> None:
    assert validate_params("golden_cross", {}) == {"fast": 5, "slow": 20}
    with pytest.raises(ConditionError):
        validate_params("price_above", {})  # 목표가는 필수 (기본값 0.0은 무효)
    with pytest.raises(ConditionError):
        validate_params("price_above", {"target": 0.0})  # 목표가는 0 초과
    with pytest.raises(ConditionError):
        validate_params("golden_cross", {"fast": 20, "slow": 5})  # 단기<장기 위반
    with pytest.raises(ConditionError):
        validate_params("rsi_overbought", {"period": 14, "threshold": 150.0})
    with pytest.raises(ConditionError):
        evaluate("unknown_condition", {}, price=1.0)


def test_golden_cross_last_bar() -> None:
    closes = [100.0] * 30 + [101.0 + i for i in range(10)]
    index = _cross_index(closes, "golden")
    fired, detail = evaluate(
        "golden_cross", {"fast": 5, "slow": 20}, candles=_candles(closes[: index + 1])
    )
    assert fired and "골든크로스" in detail
    fired, _detail = evaluate(
        "golden_cross", {"fast": 5, "slow": 20}, candles=_candles(closes[:index])
    )
    assert not fired


def test_dead_cross_last_bar() -> None:
    closes = [100.0] * 30 + [99.0 - i for i in range(10)]
    index = _cross_index(closes, "dead")
    fired, detail = evaluate(
        "dead_cross", {"fast": 5, "slow": 20}, candles=_candles(closes[: index + 1])
    )
    assert fired and "데드크로스" in detail


def test_rsi_conditions() -> None:
    rising = [100.0 + i for i in range(30)]
    fired, detail = evaluate(
        "rsi_overbought", {"period": 14, "threshold": 70.0}, candles=_candles(rising)
    )
    assert fired and "RSI" in detail
    fired, _detail = evaluate(
        "rsi_oversold", {"period": 14, "threshold": 30.0}, candles=_candles(rising)
    )
    assert not fired
    falling = [200.0 - i for i in range(30)]
    fired, _detail = evaluate(
        "rsi_oversold", {"period": 14, "threshold": 30.0}, candles=_candles(falling)
    )
    assert fired
    fired, _detail = evaluate(
        "rsi_overbought", {"period": 14, "threshold": 70.0}, candles=_candles(falling)
    )
    assert not fired


def test_macd_cross_last_bar() -> None:
    from crypto_alert.indicators import cross_over, cross_under, macd

    closes = [100.0] * 45 + [100.0 + i * 2 for i in range(15)]
    line, sig, _hist = macd(closes, 12, 26, 9)
    index = next(i for i, flag in enumerate(cross_over(line, sig)) if bool(flag))
    fired, detail = evaluate(
        "macd_bullish",
        {"fast": 12, "slow": 26, "signal": 9},
        candles=_candles(closes[: index + 1]),
    )
    assert fired and "상향" in detail

    closes_down = [200.0] * 45 + [200.0 - i * 2 for i in range(15)]
    line_d, sig_d, _h = macd(closes_down, 12, 26, 9)
    index_d = next(i for i, flag in enumerate(cross_under(line_d, sig_d)) if bool(flag))
    fired, _detail = evaluate(
        "macd_bearish",
        {"fast": 12, "slow": 26, "signal": 9},
        candles=_candles(closes_down[: index_d + 1]),
    )
    assert fired


def test_bb_breakout() -> None:
    closes = [100.0] * 20 + [200.0]
    fired, detail = evaluate(
        "bb_breakout_up", {"period": 20, "mult": 2.0}, candles=_candles(closes)
    )
    assert fired and "상단" in detail
    fired, _detail = evaluate(
        "bb_breakout_down", {"period": 20, "mult": 2.0}, candles=_candles(closes)
    )
    assert not fired
    closes_down = [100.0] * 20 + [50.0]
    fired, _detail = evaluate(
        "bb_breakout_down", {"period": 20, "mult": 2.0}, candles=_candles(closes_down)
    )
    assert fired


def test_registry_completeness() -> None:
    expected = {
        "price_above",
        "price_below",
        "golden_cross",
        "dead_cross",
        "rsi_overbought",
        "rsi_oversold",
        "macd_bullish",
        "macd_bearish",
        "bb_breakout_up",
        "bb_breakout_down",
    }
    assert set(CONDITIONS) == expected
    samples: dict[str, dict[str, float | int]] = {
        "price_above": {"target": 100.0},
        "price_below": {"target": 100.0},
        "golden_cross": {"fast": 5, "slow": 20},
        "dead_cross": {"fast": 5, "slow": 20},
        "rsi_overbought": {"period": 14, "threshold": 70.0},
        "rsi_oversold": {"period": 14, "threshold": 30.0},
        "macd_bullish": {"fast": 12, "slow": 26, "signal": 9},
        "macd_bearish": {"fast": 12, "slow": 26, "signal": 9},
        "bb_breakout_up": {"period": 20, "mult": 2.0},
        "bb_breakout_down": {"period": 20, "mult": 2.0},
    }
    for key, spec in CONDITIONS.items():
        assert spec.label and spec.needs in ("price", "candles"), key
        assert spec.params, key
        assert describe_rule(key, samples[key]) not in ("", key), key


def test_engine_edge_and_cooldown() -> None:
    rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0}, cooldown_sec=600)
    engine = AlertEngine([rule])
    assert engine.check_ticker(_ticker("BTC/KRW", 90.0), now=BASE) == []
    events = engine.check_ticker(_ticker("BTC/KRW", 110.0), now=BASE)
    assert len(events) == 1 and "BTC/KRW" in events[0].message
    # 같은 상태 유지 → 재발동 없음
    assert engine.check_ticker(_ticker("BTC/KRW", 120.0), now=BASE) == []
    # 거짓으로 돌아갔다가 쿨다운 내 재돌파 → 억제
    assert engine.check_ticker(_ticker("BTC/KRW", 90.0), now=BASE) == []
    assert engine.check_ticker(_ticker("BTC/KRW", 110.0), now=BASE + timedelta(seconds=60)) == []
    # 쿨다운 경과 후 재돌파 → 발동
    assert engine.check_ticker(_ticker("BTC/KRW", 90.0), now=BASE + timedelta(seconds=61)) == []
    events = engine.check_ticker(_ticker("BTC/KRW", 110.0), now=BASE + timedelta(seconds=700))
    assert len(events) == 1


def test_engine_ignores_disabled_and_mismatch() -> None:
    rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0}, enabled=False)
    engine = AlertEngine([rule])
    assert engine.check_ticker(_ticker("BTC/KRW", 110.0), now=BASE) == []

    rule2 = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0})
    engine2 = AlertEngine([rule2])
    assert engine2.check_ticker(_ticker("ETH/KRW", 10_000.0), now=BASE) == []


def test_engine_candle_routing_and_keys() -> None:
    rule = new_rule("upbit", "BTC/KRW", "15m", "golden_cross", {"fast": 5, "slow": 20})
    price_rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 1.0})
    engine = AlertEngine([rule, price_rule])
    assert engine.needs_candles() == [("upbit", "BTC/KRW", "15m")]

    closes = [100.0] * 30 + [101.0 + i for i in range(10)]
    index = _cross_index(closes, "golden")
    candles = _candles(closes[: index + 1])
    events = engine.check_candles("upbit", "BTC/KRW", "15m", candles, now=BASE)
    assert len(events) == 1 and "골든크로스" in events[0].message
    # 같은 상태 유지 → 재발동 없음
    assert engine.check_candles("upbit", "BTC/KRW", "15m", candles, now=BASE) == []
    # 다른 종목/주기 → 무시
    assert engine.check_candles("upbit", "ETH/KRW", "15m", candles, now=BASE) == []
    assert engine.check_candles("upbit", "BTC/KRW", "4h", candles, now=BASE) == []
    # 규칙 교체 시 사라진 규칙 상태 정리
    engine.set_rules([price_rule])
    assert engine.needs_candles() == []


def test_alert_key_roundtrip() -> None:
    key = alert_key("upbit", "BTC/KRW", "15m")
    assert key.startswith("alert:")
    assert parse_alert_key(key) == ("upbit", "BTC/KRW", "15m")
    assert parse_alert_key("upbit:BTC/KRW:15m") is None
    assert parse_alert_key("alert:broken") is None


def test_rule_validation() -> None:
    with pytest.raises(RuleError):
        new_rule("unknown", "BTC/KRW", "15m", "price_above", {"target": 1.0})
    with pytest.raises(RuleError):
        new_rule("upbit", "BTC/KRW", "99x", "price_above", {"target": 1.0})
    with pytest.raises(RuleError):
        new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 0.0})


def test_rule_from_dict_branches() -> None:
    from crypto_alert.alerts.rules import AlertRule

    with pytest.raises(RuleError):
        AlertRule.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(RuleError):
        AlertRule.from_dict(
            {
                "exchange": "upbit",
                "symbol": "BTC/KRW",
                "interval": "15m",
                "condition": "nope",
                "params": {},
            }
        )
    with pytest.raises(RuleError):
        AlertRule.from_dict(
            {
                "exchange": "upbit",
                "symbol": "BTC/KRW",
                "interval": "15m",
                "condition": "price_above",
                "params": ["target"],
            }
        )
    with pytest.raises(RuleError):
        AlertRule.from_dict(
            {
                "exchange": "upbit",
                "symbol": "BTC/KRW",
                "interval": "15m",
                "condition": "price_above",
                "params": {"target": "비쌈"},
            }
        )
    with pytest.raises(RuleError):
        AlertRule.from_dict(
            {
                "exchange": "upbit",
                "symbol": "BTC/KRW",
                "interval": "15m",
                "condition": "price_above",
                "params": {"target": 100.0},
                "cooldown_sec": "오래",
            }
        )
    with pytest.raises(RuleError):
        AlertRule.from_dict(
            {
                "exchange": "upbit",
                "symbol": "BTC/KRW",
                "interval": "15m",
                "condition": "price_above",
                "params": {"target": 100.0},
                "cooldown_sec": 99_999,
            }
        )


def test_engine_helpers() -> None:
    engine = AlertEngine()
    assert engine.rules == []
    assert engine.needs_candles() == []
    assert engine.check_candles("upbit", "BTC/KRW", "15m", []) == []


def test_evaluate_guards() -> None:
    with pytest.raises(ConditionError):
        evaluate("nope", {}, price=1.0)
    with pytest.raises(ConditionError):
        evaluate("price_above", {"target": 1.0})  # 현재가 없음
    assert evaluate("golden_cross", {"fast": 5, "slow": 20}) == (False, "캔들 없음")
    with pytest.raises(ConditionError):
        validate_params("nope", {})
    with pytest.raises(ConditionError):
        validate_params("golden_cross", {"fast": "빠름", "slow": 20})
    with pytest.raises(ConditionError):
        validate_params("macd_bullish", {"fast": 26, "slow": 12, "signal": 9})
    assert describe_rule("nope", {}) == "nope"
    assert describe_rule("price_above", {"target": 0.0}) == "price_above"


def test_condition_short_candles() -> None:
    short = _candles([100.0 + i for i in range(5)])
    assert evaluate("golden_cross", {"fast": 5, "slow": 20}, candles=short) == (
        False,
        "캔들 부족",
    )
    assert evaluate("dead_cross", {"fast": 5, "slow": 20}, candles=short) == (
        False,
        "캔들 부족",
    )
    assert evaluate("rsi_overbought", {"period": 14, "threshold": 70.0}, candles=short) == (
        False,
        "캔들 부족",
    )
    assert evaluate("rsi_oversold", {"period": 14, "threshold": 30.0}, candles=short) == (
        False,
        "캔들 부족",
    )
    tiny = _candles([100.0 + i for i in range(30)])
    assert evaluate("macd_bullish", {"fast": 12, "slow": 26, "signal": 9}, candles=tiny) == (
        False,
        "캔들 부족",
    )
    assert evaluate("macd_bearish", {"fast": 12, "slow": 26, "signal": 9}, candles=tiny) == (
        False,
        "캔들 부족",
    )
    assert evaluate("bb_breakout_up", {"period": 20, "mult": 2.0}, candles=short) == (
        False,
        "캔들 부족",
    )
    assert evaluate("bb_breakout_down", {"period": 20, "mult": 2.0}, candles=short) == (
        False,
        "캔들 부족",
    )


def test_condition_no_cross_arrows() -> None:
    """교차 없이 한쪽으로만 기울면 화살표 상태 문구로 끝난다."""
    falling = _candles([200.0 - i for i in range(30)])
    fired, detail = evaluate("golden_cross", {"fast": 5, "slow": 20}, candles=falling)
    assert not fired and detail.endswith("↓")
    rising = _candles([100.0 + i for i in range(30)])
    fired, detail = evaluate("dead_cross", {"fast": 5, "slow": 20}, candles=rising)
    assert not fired and detail.endswith("↑")
    long_rising = _candles([100.0 + i for i in range(60)])
    fired, detail = evaluate(
        "macd_bearish", {"fast": 12, "slow": 26, "signal": 9}, candles=long_rising
    )
    assert not fired and "시그널" in detail
    fired, detail = evaluate(
        "macd_bullish", {"fast": 12, "slow": 26, "signal": 9}, candles=long_rising
    )
    assert not fired and "시그널" in detail


def test_condition_flat_and_nan_warmup() -> None:
    """변동 없는 구간은 웜업으로 보고 발동하지 않는다."""
    from crypto_alert.alerts import conditions as cond_mod

    flat = _candles([100.0] * 20)
    assert evaluate("rsi_overbought", {"period": 14, "threshold": 70.0}, candles=flat) == (
        False,
        "지표 웜업 중",
    )
    assert evaluate("rsi_oversold", {"period": 14, "threshold": 30.0}, candles=flat) == (
        False,
        "지표 웜업 중",
    )
    assert cond_mod._ma_values([1.0, 2.0], 5, 20) == (None, None)
    assert cond_mod._macd_last([1.0, 2.0], 12, 26, 9) == (None, None)
    assert cond_mod._rsi_last([1.0, 2.0], 14) is None


def test_condition_private_warmup_paths() -> None:
    """공개 경로에선 닿지 않는 웜업 분기 (긴 캔들 + 큰 기간)."""
    from crypto_alert.alerts import conditions as cond_mod

    closes = [100.0 + i for i in range(30)]
    candles = _candles(closes)
    assert cond_mod._eval_golden_cross(candles, {"fast": 60, "slow": 20}) == (
        False,
        "지표 웜업 중",
    )
    assert cond_mod._eval_dead_cross(candles, {"fast": 60, "slow": 20}) == (
        False,
        "지표 웜업 중",
    )
    nan_candles = _candles([float("nan")] * 40)
    assert cond_mod._eval_macd_bullish(nan_candles, {"fast": 12, "slow": 26, "signal": 9}) == (
        False,
        "지표 웜업 중",
    )
    assert cond_mod._eval_macd_bearish(nan_candles, {"fast": 12, "slow": 26, "signal": 9}) == (
        False,
        "지표 웜업 중",
    )
    assert cond_mod._eval_bb_breakout_up(nan_candles, {"period": 20, "mult": 2.0})[0] is False
    assert cond_mod._eval_bb_breakout_down(nan_candles, {"period": 20, "mult": 2.0})[0] is False


def test_store_roundtrip(tmp_path) -> None:
    path = tmp_path / "alert_rules.json"
    rules = [
        new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 115_000_000.0}),
        new_rule("binance", "BTC/USDT", "4h", "golden_cross", {"fast": 5, "slow": 20}),
    ]
    save_rules(rules, path)
    loaded = load_rules(path)
    assert [r.to_dict() for r in loaded] == [r.to_dict() for r in rules]
    assert load_rules(tmp_path / "missing.json") == []


def test_store_corrupt(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("깨진 내용 {{{", encoding="utf-8")
    with pytest.raises(RulesError):
        load_rules(bad)
    wrong = tmp_path / "wrong.json"
    wrong.write_text('[{"exchange": "upbit"}]', encoding="utf-8")
    with pytest.raises(RulesError):
        load_rules(wrong)
    not_list = tmp_path / "not_list.json"
    not_list.write_text('{"upbit": []}', encoding="utf-8")
    with pytest.raises(RulesError):
        load_rules(not_list)
    not_dict = tmp_path / "not_dict.json"
    not_dict.write_text('["문자열"]', encoding="utf-8")
    with pytest.raises(RulesError):
        load_rules(not_dict)


def test_alert_panel_rules(qapp) -> None:
    from crypto_alert.ui.alert_panel import AlertPanel

    watchlist = {"upbit": ["BTC/KRW"], "binance": ["BTC/USDT"]}
    panel = AlertPanel(watchlist)
    fired: list[list] = []
    panel.rules_changed.connect(lambda rules: fired.append(rules))

    rules = [
        new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0}),
        new_rule("upbit", "BTC/KRW", "15m", "golden_cross", {"fast": 5, "slow": 20}),
    ]
    panel.set_rules(rules)
    assert panel._rules_table.rowCount() == 2
    assert not fired  # set_rules는 시그널 없음

    panel._rules_table.setCurrentCell(0, 0)
    panel._on_toggle()
    assert panel.rules[0].enabled is False
    assert len(fired) == 1 and fired[0][0].enabled is False
    assert panel._rules_table.item(0, 0).text() == "꺼짐"
    panel.close()


def test_alert_rule_dialog_build(qapp) -> None:
    from crypto_alert.ui.alert_rule_dialog import AlertRuleDialog

    watchlist = {"upbit": ["BTC/KRW", "ETH/KRW"], "binance": ["BTC/USDT"]}
    dialog = AlertRuleDialog(watchlist)
    dialog._param_widgets["target"].setText("115000000")
    rule = dialog.build_rule()
    assert rule.exchange == "upbit"
    assert rule.symbol == "BTC/KRW"
    assert rule.condition == "price_above"
    assert rule.params["target"] == 115_000_000.0

    # 조건 전환 → 파라미터 폼이 바뀌고 규칙 생성이 된다
    index = dialog._condition_combo.findData("golden_cross")
    dialog._condition_combo.setCurrentIndex(index)
    assert set(dialog._param_widgets) == {"fast", "slow"}
    rule = dialog.build_rule()
    assert rule.condition == "golden_cross"

    # 빈 목표가는 검증 실패
    index = dialog._condition_combo.findData("price_above")
    dialog._condition_combo.setCurrentIndex(index)
    dialog._param_widgets["target"].setText("")
    with pytest.raises(ValueError):
        dialog.build_rule()
    dialog.close()


def test_alert_rule_dialog_edit_and_branches(qapp, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from crypto_alert.ui.alert_rule_dialog import AlertRuleDialog

    watchlist = {"upbit": ["BTC/KRW", "ETH/KRW"], "binance": ["BTC/USDT"]}
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))

    # 편집 모드: 기존 값으로 콤보·파라미터가 채워진다 (지표 조건 툴팁 분기 포함)
    rule = new_rule("binance", "BTC/USDT", "4h", "golden_cross", {"fast": 5, "slow": 20})
    dialog = AlertRuleDialog(watchlist, rule)
    try:
        assert dialog._exchange_combo.currentData() == "binance"
        assert dialog._symbol_combo.currentText() == "BTC/USDT"
        built = dialog.build_rule()
        assert built.id == rule.id and built.condition == "golden_cross"
        # 콤보 선택 폴백 (data 불일치 → 텍스트 매칭, 둘 다 실패 → 유지)
        dialog._select_combo(dialog._interval_combo, "4시간")
        assert dialog._interval_combo.currentData() == "4h"
        before = dialog._interval_combo.currentIndex()
        dialog._select_combo(dialog._interval_combo, "없는주기")
        assert dialog._interval_combo.currentIndex() == before
    finally:
        dialog.close()

    # 가격 조건 툴팁 분기 + float 파라미터 위젯
    price_rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0})
    dialog = AlertRuleDialog(watchlist, price_rule)
    try:
        assert "실시간가" in dialog._interval_combo.toolTip()
        index = dialog._condition_combo.findData("rsi_overbought")
        dialog._condition_combo.setCurrentIndex(index)
        assert set(dialog._param_widgets) == {"period", "threshold"}
        built = dialog.build_rule()
        assert built.condition == "rsi_overbought"
    finally:
        dialog.close()

    # 빈 감시 목록 → 종목 없음 오류
    empty = AlertRuleDialog({"upbit": [], "binance": []})
    try:
        with pytest.raises(ValueError, match="종목"):
            empty.build_rule()
    finally:
        empty.close()

    # 잘못된 prefill → 기본값으로 복원
    from crypto_alert.alerts import ParamDef

    int_widget = AlertRuleDialog._make_param_widget(
        ParamDef("fast", "단기 MA", "int", 5, 2, 200), {"fast": "빠름"}
    )
    assert int_widget.value() == 5
    float_widget = AlertRuleDialog._make_param_widget(
        ParamDef("threshold", "기준", "float", 70.0, 0.0, 100.0), {"threshold": "높음"}
    )
    assert float_widget.value() == 70.0

    # 수집 오류 분기들
    dialog = AlertRuleDialog(watchlist)
    try:
        dialog._condition_combo.setCurrentIndex(-1)
        with pytest.raises(ValueError, match="조건을 선택"):
            dialog._collect_params()
        with pytest.raises(ValueError, match="조건을 선택"):
            dialog.build_rule()
        index = dialog._condition_combo.findData("price_above")
        dialog._condition_combo.setCurrentIndex(index)
        del dialog._param_widgets["target"]
        with pytest.raises(ValueError, match="입력칸"):
            dialog._collect_params()
        dialog._rebuild_params(None)
        dialog._param_widgets["target"].setText("비쌈")
        with pytest.raises(ValueError, match="숫자가 아닙니다"):
            dialog.build_rule()
        # RuleError 전달 (단기 ≥ 장기)
        index = dialog._condition_combo.findData("golden_cross")
        dialog._condition_combo.setCurrentIndex(index)
        dialog._param_widgets["fast"].setValue(20)
        dialog._param_widgets["slow"].setValue(5)
        with pytest.raises(ValueError, match="단기 MA"):
            dialog.build_rule()
        # accept 실패 → 닫히지 않고 result 없음
        dialog.accept()
        assert dialog.result is None and warnings
        # accept 성공
        dialog._param_widgets["fast"].setValue(5)
        dialog._param_widgets["slow"].setValue(20)
        dialog.accept()
        assert dialog.result is not None and dialog.result.condition == "golden_cross"
    finally:
        dialog.close()
