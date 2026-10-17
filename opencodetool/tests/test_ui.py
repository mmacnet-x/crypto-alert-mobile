"""3단계 테스트: UI 패널 생성/동작 (offscreen)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from crypto_alert.config import load_watchlist
from crypto_alert.exchanges.base import Candle, Interval, Ticker
from crypto_alert.marketcap import MarketRank
from crypto_alert.ui.alert_panel import AlertPanel
from crypto_alert.ui.chart_panel import ChartPanel
from crypto_alert.ui.holdings_panel import HoldingsPanel
from crypto_alert.ui.main_window import MainWindow
from crypto_alert.ui.marketcap_panel import MarketCapPanel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _candles(count: int = 20) -> list[Candle]:
    base = datetime(2026, 10, 8, tzinfo=UTC)
    out = []
    price = 100.0
    for i in range(count):
        out.append(
            Candle(
                symbol="BTC/KRW",
                interval=Interval.M15,
                time=base.replace(hour=i // 4, minute=(i % 4) * 15),
                open=price,
                high=price + 2,
                low=price - 2,
                close=price + 1,
                volume=10.0 + i,
            )
        )
        price += 1
    return out


def test_chart_panel_selection(qapp) -> None:
    panel = ChartPanel(load_watchlist())
    assert panel.exchange == "upbit"
    assert panel.symbol == "BTC/KRW"
    assert panel.interval is Interval.M15
    assert panel.request_key == "upbit:BTC/KRW:15m"

    # 거래소 전환 → 종목 목록도 전환
    panel._exchange_combo.setCurrentIndex(1)
    assert panel.exchange == "binance"
    assert panel.symbol.endswith("/USDT")
    panel.close()


def test_chart_panel_set_candles(qapp) -> None:
    panel = ChartPanel(load_watchlist())
    candles = _candles()
    panel.set_candles(candles)
    assert len(panel._candles) == len(candles)
    assert panel._candle_item is not None
    assert panel._volume_item is not None

    # 빈 데이터 → 항목 제거
    panel.set_candles([])
    assert panel._candle_item is None
    panel.close()


def test_chart_panel_ticker_updates_last_candle(qapp) -> None:
    panel = ChartPanel(load_watchlist())
    candles = _candles(3)
    panel.set_candles(candles)
    last = candles[-1]
    ticker = Ticker(
        symbol="BTC/KRW",
        price=last.high + 50,
        change_rate=0.01,
        volume=1.0,
        time=last.time,  # 같은 구간
    )
    panel.on_ticker(ticker)
    panel._flush_ticker()  # 스로틀 우회하여 즉시 반영
    updated = panel._candles[-1]
    assert updated.close == ticker.price
    assert updated.high == ticker.price
    panel.close()


def test_chart_panel_new_bucket_emits_stale(qapp) -> None:
    from datetime import timedelta

    from PyQt6.QtCore import QCoreApplication

    panel = ChartPanel(load_watchlist())
    candles = _candles(3)
    panel.set_candles(candles)
    last = candles[-1]
    fired: list[int] = []
    panel.candles_stale.connect(lambda: fired.append(1))
    ticker = Ticker(
        symbol="BTC/KRW",
        price=200.0,
        change_rate=0.0,
        volume=1.0,
        time=last.time + timedelta(minutes=20),  # 다음 15분 구간
    )
    panel.on_ticker(ticker)
    panel._flush_ticker()
    QCoreApplication.processEvents()
    assert fired, "구간이 바뀌면 candles_stale이 발생해야 한다"
    panel.close()


def test_chart_panel_indicator_toggles(qapp) -> None:
    import numpy as np

    from crypto_alert.indicators import rsi as rsi_calc
    from crypto_alert.indicators import sma as sma_calc

    panel = ChartPanel(load_watchlist())

    # 기본: MA만 켜져 있고 서브패널은 레이아웃에 없다
    assert panel._indicators == {"MA": True, "BB": False, "RSI": False, "MACD": False}
    assert panel._rsi_plot not in panel._glw.ci.items
    assert panel._macd_plot not in panel._glw.ci.items
    # 시간축은 최하단(거래량) 플롯에만 표시
    assert panel._candle_plot.getAxis("bottom").isVisible() is False
    assert panel._volume_plot.getAxis("bottom").isVisible() is True

    candles = _candles(60)
    panel.set_candles(candles)
    assert panel._macd_hist is not None
    # 강제 재계산: MACD y범위가 기본 [0,1]에서 데이터에 맞춰졌다
    assert tuple(panel._macd_plot.viewRange()[1]) != (0.0, 1.0)

    # MA 오버레이: 캔들 플롯에 붙어 있고 sma(8)와 값이 일치 (15분봉 기본 기간)
    ma8 = panel._ma_curves[8]
    assert ma8 in panel._candle_plot.items
    assert 5 not in panel._ma_curves  # 구 기간(5/20/60) 폐기
    closes = np.array([c.close for c in candles], dtype=float)
    xs = np.array([c.time.timestamp() for c in candles], dtype=float)
    got_x, got_y = ma8.getData()
    np.testing.assert_allclose(got_x, xs)
    np.testing.assert_allclose(got_y, sma_calc(closes, 8), equal_nan=True)

    # BB 토글 → 오버레이 추가 (상/중/하 모두 점선)
    panel._indicator_buttons["BB"].click()
    assert panel._indicators["BB"] is True
    assert panel._bb_curves["upper"] in panel._candle_plot.items
    assert panel._bb_curves["mid"] in panel._candle_plot.items
    for band in ("upper", "mid", "lower"):
        assert panel._bb_curves[band].opts["pen"].style() == Qt.PenStyle.DashLine

    # RSI 토글 → 서브패널(행 2) 추가 + 계산값 일치 + y 0..100 고정
    panel._indicator_buttons["RSI"].click()
    assert panel._rsi_plot in panel._glw.ci.items
    assert panel._volume_plot.getAxis("bottom").isVisible() is False
    assert panel._rsi_plot.getAxis("bottom").isVisible() is True
    got_rsi = panel._rsi_curve.getData()[1]
    np.testing.assert_allclose(got_rsi, rsi_calc(closes, 14), equal_nan=True)
    rsi_lo, rsi_hi = panel._rsi_plot.viewRange()[1]
    assert np.isclose(rsi_lo, 0.0) and np.isclose(rsi_hi, 100.0)

    # MACD 토글 → 서브패널(행 3) 추가, 시간축이 MACD로 이동
    panel._indicator_buttons["MACD"].click()
    assert panel._macd_plot in panel._glw.ci.items
    assert panel._rsi_plot.getAxis("bottom").isVisible() is False
    assert panel._macd_plot.getAxis("bottom").isVisible() is True

    # MA 끄기 → 오버레이만 분리 (캔들/보조 데이터는 유지)
    panel._indicator_buttons["MA"].click()
    assert panel._indicators["MA"] is False
    assert panel._ma_curves[8] not in panel._candle_plot.items
    assert panel._candle_item is not None

    # 실시간 갱신은 MACD 사용자 확대를 되돌리지 않는다 (expand-only)
    panel._macd_plot.setYRange(-50, 50, padding=0)
    last = panel._candles[-1]
    panel.on_ticker(
        Ticker(
            symbol="BTC/KRW",
            price=last.close + 1,
            change_rate=0.0,
            volume=1.0,
            time=last.time,
        )
    )
    panel._flush_ticker()
    macd_lo, macd_hi = panel._macd_plot.viewRange()[1]
    assert np.isclose(macd_lo, -50.0) and np.isclose(macd_hi, 50.0)

    # 빈 캔들 → 지표 데이터 비움
    panel.set_candles([])
    assert panel._macd_hist is None
    panel.close()


def test_chart_panel_ma_periods_by_interval(qapp) -> None:
    """주기별 MA 기간: 15분=8/96/192, 4시간=6/42/168, 일/주/월=60/120/200."""
    import numpy as np

    from crypto_alert.indicators import sma as sma_calc
    from crypto_alert.ui.chart_panel import ma_periods_for

    assert ma_periods_for("15m") == (8, 96, 192)
    assert ma_periods_for("4h") == (6, 42, 168)
    assert ma_periods_for("1d") == (60, 120, 200)
    assert ma_periods_for("1w") == (60, 120, 200)
    assert ma_periods_for("1M") == (60, 120, 200)
    assert ma_periods_for("??") == (60, 120, 200)  # 미등록 주기는 일봉 기본값

    panel = ChartPanel(load_watchlist())
    try:
        assert panel._active_periods == (8, 96, 192)
        assert "8/96/192" in panel._indicator_buttons["MA"].toolTip()

        base = datetime(2026, 10, 1, tzinfo=UTC)
        price = 100.0
        candles = []
        for i in range(210):
            candles.append(
                Candle(
                    symbol="BTC/KRW",
                    interval=Interval.M15,
                    time=base + timedelta(minutes=15 * i),
                    open=price,
                    high=price + 2,
                    low=price - 2,
                    close=price + 1,
                    volume=10.0,
                )
            )
            price += 0.5
        panel.set_candles(candles)
        closes = np.array([c.close for c in candles], dtype=float)
        assert panel._ma_curves[8] in panel._candle_plot.items
        np.testing.assert_allclose(
            panel._ma_curves[8].getData()[1], sma_calc(closes, 8), equal_nan=True
        )

        # 4시간 전환 → MA 6/42/168로 교체
        panel._interval_buttons["4h"].click()
        assert panel._active_periods == (6, 42, 168)
        assert "6/42/168" in panel._indicator_buttons["MA"].toolTip()
        assert panel._ma_curves[8] not in panel._candle_plot.items  # 15분 MA 분리
        panel.set_candles(candles)
        assert panel._ma_curves[6] in panel._candle_plot.items
        np.testing.assert_allclose(
            panel._ma_curves[6].getData()[1], sma_calc(closes, 6), equal_nan=True
        )

        # 일봉 전환 → MA 60/120/200
        panel._interval_buttons["1d"].click()
        assert panel._active_periods == (60, 120, 200)
        assert panel._ma_curves[6] not in panel._candle_plot.items
        panel.set_candles(candles)
        assert panel._ma_curves[200] in panel._candle_plot.items
    finally:
        panel.close()


def test_main_window_tabs_menus_capture(qapp, monkeypatch, tmp_path) -> None:
    """탭 구성(차트알림/종목/시가총액) + 메뉴(캡처/닫기/보기 전환)."""
    from PyQt6.QtWidgets import QFileDialog

    from crypto_alert.ui.main_window import TAB_CHART_ALERTS, TAB_HOLDINGS, TAB_MARKET

    window = MainWindow(start_engine=False)
    try:
        # 첫 화면: 차트+알림 탭 (시총·종목은 보이지 않음)
        assert window._tabs.count() == 3
        assert window._tabs.currentIndex() == TAB_CHART_ALERTS
        assert window._tabs.tabText(TAB_CHART_ALERTS) == "차트알림"
        assert window._tabs.tabText(TAB_HOLDINGS) == "종목"
        assert window._tabs.tabText(TAB_MARKET) == "시가총액"
        assert window._tabs.widget(TAB_HOLDINGS) is window._holdings
        assert window._tabs.widget(TAB_MARKET) is window._market

        # 보기 메뉴 → 탭 전환 (탭 클릭과 동일 기능)
        window._view_holdings_action.trigger()
        assert window._tabs.currentIndex() == TAB_HOLDINGS
        assert window._view_holdings_action.isChecked() is True
        window._view_market_action.trigger()
        assert window._tabs.currentIndex() == TAB_MARKET
        assert window._view_market_action.isChecked() is True
        assert window._view_holdings_action.isChecked() is False
        window._tabs.setCurrentIndex(TAB_CHART_ALERTS)
        assert window._view_market_action.isChecked() is False

        # 파일 > 캡처: 차트 픽셀을 PNG로 저장
        out = tmp_path / "shot.png"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(out), "PNG 이미지 (*.png)"),
        )
        window.capture_chart()
        assert out.exists() and out.stat().st_size > 0

        # 저장 취소("")는 무시
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
        window.capture_chart()
    finally:
        window.close()


def test_alert_panel_add(qapp) -> None:
    panel = AlertPanel()
    panel.add_alert(datetime.now(tz=UTC), "BTC/KRW", "테스트 알림")
    assert panel._table.rowCount() == 1
    panel.close()


def test_marketcap_panel_update(qapp) -> None:
    panel = MarketCapPanel()
    ranks = [
        MarketRank(
            base="BTC",
            symbol="BTC/USDT",
            exchange="binance",
            price_usd=83_000.0,
            market_cap_usd=1.65e12,
            change_rate=0.01,
            supply=19_900_000.0,
        )
    ]
    panel.update_ranks(ranks)
    assert panel._table.rowCount() == 1
    assert panel._table.item(0, 1).text() == "BTC/USDT"
    assert "$1.65T" in panel._table.item(0, 3).text()
    panel.close()


def test_holdings_panel_add_and_value(qapp) -> None:
    import tempfile
    from pathlib import Path

    from crypto_alert import holdings as holdings_mod

    tmp = Path(tempfile.mkdtemp()) / "holdings.json"
    original = holdings_mod.holdings_path
    try:
        holdings_mod.holdings_path = lambda: tmp  # type: ignore[assignment]
        panel = HoldingsPanel(load_watchlist())
        panel._symbol_combo.setEditText("BTC/KRW")
        panel._quantity_edit.setText("0.5")
        panel._avg_price_edit.setText("100000000")
        panel._on_add()
        assert panel._table.rowCount() == 1

        # 현재가 수신 → 평가 갱신
        ticker = Ticker(
            symbol="BTC/KRW",
            price=120_000_000.0,
            change_rate=0.2,
            volume=1.0,
            time=datetime.now(tz=UTC),
        )
        panel.on_ticker(ticker)
        panel.refresh_values()
        value_text = panel._table.item(0, 4).text().replace(",", "")
        assert float(value_text) == 0.5 * 120_000_000.0
        panel.close()
    finally:
        holdings_mod.holdings_path = original  # type: ignore[assignment]


def test_main_window_four_panels(qapp) -> None:
    window = MainWindow(start_engine=False)
    assert window.centralWidget() is not None
    assert window._chart is not None
    assert window._alerts is not None
    assert window._market is not None
    assert window._holdings is not None
    window.close()


def test_main_window_start_engine_bootstraps(qapp, monkeypatch) -> None:
    """엔진 시작 경로는 스레드 생성만 스텁으로 막고 검증한다 (네트워크 없음)."""
    from crypto_alert.engine import DataEngine

    started: list[bool] = []
    monkeypatch.setattr(DataEngine, "start", lambda self: started.append(True))
    window = MainWindow(start_engine=True)
    try:
        assert started == [True]
        assert window._refresh_timer.isActive()
        assert window._snapshot_timer.isActive()
        assert window._alert_timer.isActive()
        assert window._pending_key  # 초기 캔들 요청됨
    finally:
        _drain_pending(window)
        window.close()


def _drain_pending(window: MainWindow) -> None:
    for pending in window._engine._pending:
        pending.close()
    window._engine._pending.clear()


def test_main_window_ticker_routing_and_alert(qapp) -> None:
    from crypto_alert.alerts import new_rule

    window = MainWindow(start_engine=False)
    try:
        calls: list[str] = []
        window._notifier.set_test_hook(lambda e, c, t: calls.append(c))
        rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 50.0})
        window._alert_engine.set_rules([rule])
        ticker = Ticker(
            symbol="BTC/KRW",
            price=100.0,
            change_rate=0.01,
            volume=1.0,
            time=datetime.now(tz=UTC),
        )
        window._on_ticker("BTC/KRW", ticker)
        assert window._ticker_cache["BTC/KRW"] is ticker
        assert window._alerts._table.rowCount() == 1
        assert calls == ["popup", "sound"]
        other = Ticker(
            symbol="ETH/KRW",
            price=1.0,
            change_rate=0.0,
            volume=1.0,
            time=datetime.now(tz=UTC),
        )
        window._on_ticker("ETH/KRW", other)
        assert window._alerts._table.rowCount() == 1  # 규칙 미발동
    finally:
        _drain_pending(window)
        window.close()


def test_main_window_candles_routing(qapp) -> None:
    from crypto_alert.alerts.engine import alert_key

    window = MainWindow(start_engine=False)
    try:
        candles = _candles(20)
        window._pending_key = "k1"
        window._on_candles("k1", "BTC/KRW", Interval.M15, candles)
        assert len(window._chart._candles) == 20
        window._on_candles("k1", "BTC/KRW", Interval.M15, "깨짐")
        assert len(window._chart._candles) == 20  # 비목록 무시
        window._on_candles(alert_key("upbit", "BTC/KRW", "15m"), "BTC/KRW", Interval.M15, candles)
        window._on_candles("stale-key", "BTC/KRW", Interval.M15, candles)  # 오래된 응답 무시
        window._on_candles(alert_key("upbit", "BTC/KRW", "15m"), "BTC/KRW", Interval.M15, "깨짐")
    finally:
        window.close()


def test_main_window_snapshot_connection_error(qapp) -> None:
    window = MainWindow(start_engine=False)
    try:
        window._on_snapshot("x", "notalist")
        assert window._usd_krw > 0
        zero = Ticker(
            symbol="USDT/KRW", price=0.0, change_rate=0.0, volume=1.0, time=datetime.now(tz=UTC)
        )
        window._on_snapshot("fx", [zero])
        fx = Ticker(
            symbol="USDT/KRW",
            price=1400.0,
            change_rate=0.0,
            volume=1.0,
            time=datetime.now(tz=UTC),
        )
        window._on_snapshot("fx", [fx])
        assert window._usd_krw == 1400.0
        assert "1,400.0" in window._fx_status.text()
        tick = Ticker(
            symbol="BTC/KRW", price=100.0, change_rate=0.02, volume=1.0, time=datetime.now(tz=UTC)
        )
        window._on_snapshot("mc:upbit", [tick, "깨짐"])
        assert window._ticker_cache["BTC/KRW"] is tick
        window._on_connection("upbit", True)
        assert window._upbit_status.text() == "업비트: 연결"
        window._on_connection("upbit", False)
        assert window._upbit_status.text() == "업비트: 끊김"
        window._on_connection("binance", True)
        assert window._binance_status.text() == "바이낸스: 연결"
        window._on_error("테스트 오류")  # 상태표시줄에만 표시
    finally:
        window.close()


def test_main_window_requests_and_stale(qapp) -> None:
    import time

    window = MainWindow(start_engine=False)
    try:
        before = len(window._engine._pending)
        window._on_selection_changed("upbit", "BTC/KRW", Interval.M15)
        assert len(window._engine._pending) == before + 1
        window._last_candle_request = 0.0
        window._on_candles_stale()
        assert len(window._engine._pending) == before + 2
        window._last_candle_request = time.monotonic()
        window._on_candles_stale()  # 최소 간격 내 → 무시
        assert len(window._engine._pending) == before + 2
        window._on_holdings_symbol("BTC/KRW")
        window._on_holdings_symbol("BTC/USDT")
        assert len(window._engine._pending) == before + 4
        window._refresh_displays()
    finally:
        _drain_pending(window)
        window.close()


def test_main_window_rules_changed(qapp, monkeypatch) -> None:
    import crypto_alert.ui.main_window as mw_mod
    from crypto_alert.alerts import RulesError, new_rule

    window = MainWindow(start_engine=False)
    try:
        saved: list[list] = []
        monkeypatch.setattr(mw_mod, "save_rules", lambda rules: saved.append(list(rules)))
        rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0})
        window._on_rules_changed([rule])
        assert saved and window._alert_engine.rules == [rule]

        def _boom(rules: list) -> None:
            raise RulesError("저장 실패")

        monkeypatch.setattr(mw_mod, "save_rules", _boom)
        window._on_rules_changed([])
        assert window._alert_engine.rules == []
    finally:
        _drain_pending(window)
        window.close()


def test_main_window_request_alert_candles_bad_interval(qapp) -> None:
    from crypto_alert.alerts import AlertRule, new_rule

    window = MainWindow(start_engine=False)
    try:
        bad = AlertRule(
            id="x",
            exchange="upbit",
            symbol="BTC/KRW",
            interval="bogus",
            condition="golden_cross",
            params={"fast": 5, "slow": 20},
        )
        good = new_rule("upbit", "BTC/KRW", "15m", "golden_cross", {"fast": 5, "slow": 20})
        window._alert_engine.set_rules([bad, good])
        before = len(window._engine._pending)
        window._request_alert_candles()  # 잘못된 주기는 건너뜀, 정상은 요청
        assert len(window._engine._pending) == before + 1
        window._alert_engine.set_rules([bad])
        window._request_alert_candles()
        assert len(window._engine._pending) == before + 1
    finally:
        _drain_pending(window)
        window.close()


def test_main_window_notify_slots(qapp, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMessageBox

    import crypto_alert.ui.main_window as mw_mod
    from crypto_alert.alerts import NotifySettings, NotifySettingsError

    infos: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))

    window = MainWindow(start_engine=False)
    try:
        window._on_notify_settings_changed("문자열")  # 타입 불일치 → 무시
        assert window._notifier.settings.telegram_enabled is False
        saved: list[object] = []
        monkeypatch.setattr(mw_mod, "save_notify_settings", lambda s: saved.append(s))
        settings = NotifySettings(
            telegram_enabled=True, bot_token="tok", chat_id="123", sound_enabled=False
        )
        window._on_notify_settings_changed(settings)
        assert saved == [settings]
        assert window._notifier.settings is settings

        def _boom(s: object) -> None:
            raise NotifySettingsError("저장 실패")

        monkeypatch.setattr(mw_mod, "save_notify_settings", _boom)
        window._on_notify_settings_changed(settings)  # 저장 실패해도 반영은 계속
        assert window._notifier.settings is settings

        window._on_notify_test("문자열")  # 타입 불일치 → 무시
        calls: list[str] = []
        window._notifier.set_test_hook(lambda e, c, t: calls.append(c))
        window._on_notify_test(settings)
        assert calls == ["telegram"] and infos  # 테스트 성공 팝업
        window._on_notify_test_finished(False, "실패 사유")
        assert warnings == ["실패 사유"]
    finally:
        window.close()


def test_main_window_init_load_errors(qapp, monkeypatch) -> None:
    import crypto_alert.ui.main_window as mw_mod
    from crypto_alert.alerts import NotifySettingsError, RulesError

    def _boom_rules():  # type: ignore[no-untyped-def]
        raise RulesError("규칙 깨짐")

    def _boom_notify():  # type: ignore[no-untyped-def]
        raise NotifySettingsError("설정 깨짐")

    monkeypatch.setattr(mw_mod, "load_rules", _boom_rules)
    monkeypatch.setattr(mw_mod, "load_notify_settings", _boom_notify)
    window = MainWindow(start_engine=False)
    try:
        assert window._alert_engine.rules == []
        assert window._notifier.settings.telegram_enabled is False
    finally:
        window.close()


def test_main_window_reload_watchlist(qapp, monkeypatch) -> None:
    import crypto_alert.ui.main_window as mw_mod

    window = MainWindow(start_engine=False)
    try:
        fresh = {"upbit": ["BTC/KRW"], "binance": []}
        monkeypatch.setattr(mw_mod, "load_watchlist", lambda: fresh)
        window.reload_watchlist()
        assert window._watchlist is fresh
        assert window._chart._watchlist is fresh

        def _boom():  # type: ignore[no-untyped-def]
            raise RuntimeError("파일 깨짐")

        monkeypatch.setattr(mw_mod, "load_watchlist", _boom)
        window.reload_watchlist()  # 오류 표시 후 기존 목록 유지
        assert window._watchlist is fresh
    finally:
        _drain_pending(window)
        window.close()


def test_chart_paint_and_empty_bounds(qapp) -> None:
    import numpy as np
    from PyQt6.QtGui import QImage, QPainter

    from crypto_alert.ui.chart_panel import CandlestickItem, HistogramItem, VolumeBarsItem

    candles = _candles(5)
    items = [
        CandlestickItem(candles, 900.0),
        VolumeBarsItem(candles, 900.0),
        HistogramItem(np.arange(5.0), np.array([1.0, -2.0, 3.0, -4.0, 5.0]), 900.0),
    ]
    for item in items:
        image = QImage(64, 64, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        item.paint(painter, None)
        painter.end()
        assert not item.boundingRect().isNull()
    assert CandlestickItem([], 900.0).boundingRect().isNull()
    assert VolumeBarsItem([], 900.0).boundingRect().isNull()
    assert HistogramItem(np.empty(0), np.empty(0), 900.0).boundingRect().isNull()
    all_nan = HistogramItem(np.arange(3.0), np.array([np.nan] * 3), 900.0)
    assert not all_nan.boundingRect().isNull()


def test_chart_selection_and_misc(qapp) -> None:
    import pyqtgraph as pg

    panel = ChartPanel(load_watchlist())
    try:
        fired: list[tuple] = []
        panel.selection_changed.connect(lambda *a: fired.append(a))
        panel._symbol_combo.setCurrentIndex(1)
        assert fired and fired[-1][1] == panel.symbol
        panel._interval_buttons[Interval.H4.value].click()
        assert panel.interval is Interval.H4
        panel._on_interval_clicked()  # 발신자 없음 → 그래도 방출
        assert fired
        panel.set_watchlist(load_watchlist())
        assert panel._watchlist
        assert panel._indicator_tooltip("???") == "???"
        assert ChartPanel._finite_data(pg.PlotDataItem()) is None
        panel._reset_ranges()  # 빈 캔들 → 무시
        panel._flush_ticker()  # 대기 틱 없음 → 무시
        assert panel.last_candle_time() is None
        panel.set_candles(_candles(5))
        assert panel.last_candle_time() is not None
    finally:
        panel.close()


def test_chart_expand_view_and_old_ticker(qapp) -> None:
    panel = ChartPanel(load_watchlist())
    try:
        ChartPanel._expand_view(panel._candle_plot, [])  # 빈 값 → 무시
        panel._candle_plot.setYRange(1000.0, 2000.0, padding=0)
        ChartPanel._expand_view(panel._candle_plot, [10.0])
        lo, hi = panel._candle_plot.viewRange()[1]
        assert lo < 1000.0 and hi == 2000.0  # 아래로만 확장
        base = datetime(2026, 10, 8, 10, 30, 30, tzinfo=UTC)
        panel.set_candles(
            [
                Candle(
                    symbol="BTC/KRW",
                    interval=Interval.M15,
                    time=base,
                    open=100.0,
                    high=102.0,
                    low=98.0,
                    close=101.0,
                    volume=1.0,
                )
            ]
        )
        old = Ticker(
            symbol="BTC/KRW",
            price=50.0,
            change_rate=0.0,
            volume=1.0,
            time=datetime(2026, 10, 8, 10, 30, 10, tzinfo=UTC),
        )
        panel.on_ticker(old)
        panel._flush_ticker()  # 같은 구간 과거 틱 → 무시
        assert panel._candles[-1].close == 101.0
    finally:
        panel.close()


def test_holdings_panel_edge_paths(qapp, tmp_path, monkeypatch) -> None:
    import json

    from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

    from crypto_alert import holdings as holdings_mod

    monkeypatch.setattr(holdings_mod, "holdings_path", lambda: tmp_path / "holdings.json")
    (tmp_path / "holdings.json").write_text(
        json.dumps([{"symbol": "BTC/KRW", "quantity": 1.0, "avg_price": 100.0}]),
        encoding="utf-8",
    )
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))

    panel = HoldingsPanel(load_watchlist())
    try:
        assert panel._table.rowCount() == 1  # 기존 파일 로드
        panel._symbol_combo.setEditText("BTC/KRW")
        panel._quantity_edit.setText("")
        panel._avg_price_edit.setText("x")
        panel._on_add()
        assert warnings and panel._table.rowCount() == 1
        panel._quantity_edit.setText("0")
        panel._avg_price_edit.setText("1")
        panel._on_add()
        assert len(warnings) == 2 and panel._table.rowCount() == 1
        panel._table.setCurrentCell(0, 0)
        panel._on_remove()
        assert panel._table.rowCount() == 0
        panel._on_remove()  # 선택 없음 → 무시
        panel._symbol_combo.setEditText("BTC/KRW")
        panel._quantity_edit.setText("1")
        panel._avg_price_edit.setText("100")
        panel._on_add()
        assert panel._table.rowCount() == 1
        panel._table.item(0, 1).setText("망가짐")
        assert panel._read_holdings() == []  # 잘못된 행 건너뜀
        panel.set_watchlist({"upbit": ["BTC/KRW"], "binance": []})
        assert panel._symbol_combo.count() == 1
        panel._table.setRowCount(0)
        panel._table.insertRow(0)  # 빈 행 (아이템 없음)
        panel.refresh_values()
        panel.on_ticker(
            Ticker(
                symbol="BTC/KRW",
                price=200.0,
                change_rate=0.0,
                volume=1.0,
                time=datetime.now(tz=UTC),
            )
        )
        panel.refresh_values()  # 종목 셀 없음 → 무시
        panel._table.setItem(0, 0, QTableWidgetItem("BTC/KRW"))
        panel.refresh_values()  # 수량 셀 없음 → 무시
        panel._table.setItem(0, 1, QTableWidgetItem("1"))
        panel._table.setItem(0, 2, QTableWidgetItem("100"))
        panel.refresh_values()
        assert panel._table.item(0, 3).text() == "200.00"
        panel._table.takeItem(0, 3)
        panel.refresh_values()  # 셀 재생성 분기
        assert panel._table.item(0, 3).text() == "200.00"
    finally:
        panel.close()


def test_short_price_units(qapp) -> None:
    from crypto_alert.ui.marketcap_panel import _short_price

    assert _short_price(83_000.0) == "$83,000.00"
    assert _short_price(2.5678) == "$2.5678"
    assert _short_price(0.335) == "$0.335000"
    assert _short_price(0.000054) == "$0.000054"


def test_alert_panel_add_edit_delete(qapp, monkeypatch) -> None:
    from PyQt6.QtWidgets import QDialog, QMessageBox

    import crypto_alert.ui.alert_rule_dialog as dlg_mod
    from crypto_alert.alerts import new_rule

    rule = new_rule("upbit", "BTC/KRW", "15m", "price_above", {"target": 100.0})

    class _StubDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, *args, **kwargs) -> None:
            self.result = rule

        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dlg_mod, "AlertRuleDialog", _StubDialog)
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[1]))

    panel = AlertPanel({"upbit": ["BTC/KRW"], "binance": []})
    try:
        panel._on_add()
        assert panel._rules_table.rowCount() == 1
        assert panel.rules == [rule]
        panel._on_edit()  # 선택 없음 → 안내
        assert infos
        panel._rules_table.setCurrentCell(0, 0)
        panel._on_edit()
        assert panel.rules == [rule]
        panel._on_delete()
        assert panel.rules == []
        panel._on_delete()  # 선택 없음 → 무시
        panel._on_toggle()  # 선택 없음 → 무시
        panel.set_watchlist({"upbit": ["BTC/KRW"], "binance": []})
        panel.set_notify_settings(panel._notify_settings)
    finally:
        panel.close()


def test_alert_panel_notify_settings_dialog(qapp, monkeypatch) -> None:
    from PyQt6.QtWidgets import QDialog

    import crypto_alert.ui.notify_dialog as notify_dlg_mod
    from crypto_alert.alerts import NotifySettings

    settings = NotifySettings(bot_token="tok", chat_id="123")

    class _Signal:
        def __init__(self) -> None:
            self.slots: list = []

        def connect(self, slot) -> None:  # type: ignore[no-untyped-def]
            self.slots.append(slot)

        def emit(self, value: object) -> None:
            for slot in self.slots:
                slot(value)

    class _StubDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, *args, **kwargs) -> None:
            self.result = settings
            self.test_requested = _Signal()

        def exec(self) -> int:
            self.test_requested.emit(settings)  # 테스트 버튼 경로 검증
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(notify_dlg_mod, "NotifySettingsDialog", _StubDialog)
    panel = AlertPanel({"upbit": ["BTC/KRW"], "binance": []})
    try:
        changed: list[object] = []
        tested: list[object] = []
        panel.notify_settings_changed.connect(changed.append)
        panel.notify_test_requested.connect(tested.append)
        panel._on_notify_settings()
        assert changed == [settings] and tested == [settings]

        class _Rejected(_StubDialog):
            def exec(self) -> int:
                return QDialog.DialogCode.Rejected

        monkeypatch.setattr(notify_dlg_mod, "NotifySettingsDialog", _Rejected)
        panel._on_notify_settings()  # 취소 → 방출 없음
        assert len(changed) == 1 and len(tested) == 1
    finally:
        panel.close()


def test_alert_panel_trims_history(qapp) -> None:
    from crypto_alert.ui.alert_panel import MAX_ROWS

    panel = AlertPanel({"upbit": ["BTC/KRW"], "binance": []})
    try:
        when = datetime.now(tz=UTC)
        for i in range(MAX_ROWS + 5):
            panel.add_alert(when, "BTC/KRW", f"m{i}")
        assert panel._table.rowCount() == MAX_ROWS
        assert panel._table.item(0, 2).text() == f"m{MAX_ROWS + 4}"
    finally:
        panel.close()


def test_okx_wiring(qapp) -> None:
    """OKX 배선: 콤보 선택지 + 심볼 판별 + 연결 상태 + 시총 새로고침."""
    from crypto_alert.ui.alert_rule_dialog import DIALOG_EXCHANGES

    assert ("OKX", "okx") in DIALOG_EXCHANGES

    panel = ChartPanel(load_watchlist())
    try:
        values = [panel._exchange_combo.itemData(i) for i in range(panel._exchange_combo.count())]
        assert values == ["upbit", "binance", "okx"]
        panel._exchange_combo.setCurrentIndex(2)
        assert panel.exchange == "okx"
        assert panel._symbol_combo.currentText() == "PI/USDT"
    finally:
        panel.close()

    window = MainWindow(start_engine=False)
    try:
        assert window._exchange_for_symbol("PI/USDT") == "okx"
        assert window._exchange_for_symbol("BTC/KRW") == "upbit"
        assert window._exchange_for_symbol("BTC/USDT") == "binance"
        assert window._exchange_for_symbol("XXX/YYY") == "binance"  # 추정 폴백
        window._on_connection("okx", True)
        assert window._okx_status.text() == "OKX: 연결"
        window._on_connection("okx", False)
        assert window._okx_status.text() == "OKX: 끊김"
        window._on_connection("unknown", True)  # 미등록 거래소 무시
        window._refresh_displays()
    finally:
        window.close()


def test_holdings_resolve_okx(qapp, tmp_path, monkeypatch) -> None:
    """보유종목 입력이 감시 목록 기준으로 OKX로 판별된다."""
    from crypto_alert import holdings as holdings_mod

    monkeypatch.setattr(holdings_mod, "holdings_path", lambda: tmp_path / "holdings.json")
    watchlist = {"upbit": ["BTC/KRW"], "binance": [], "okx": ["PI/USDT"]}
    panel = HoldingsPanel(watchlist)
    try:
        assert panel._resolve_symbol("PI/USDT") == "PI/USDT"
        assert panel._resolve_symbol("pi-usdt") == "PI/USDT"
        assert panel._resolve_symbol("BTC/KRW") == "BTC/KRW"
        assert panel._resolve_symbol("ETHUSDT") == "ETH/USDT"  # 목록 밖 → 추정 폴백
    finally:
        panel.close()


def test_main_window_candle_alert_fires(qapp) -> None:
    from datetime import timedelta

    from crypto_alert.alerts import new_rule
    from crypto_alert.alerts.engine import alert_key
    from crypto_alert.indicators import cross_over, sma

    closes = [100.0] * 30 + [101.0 + i for i in range(10)]
    flags = cross_over(sma(closes, 5), sma(closes, 20))
    index = next(i for i, flag in enumerate(flags) if bool(flag))
    base = datetime(2026, 10, 8, tzinfo=UTC)
    candles = [
        Candle(
            symbol="BTC/KRW",
            interval=Interval.M15,
            time=base + timedelta(minutes=15 * i),
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1.0,
        )
        for i, c in enumerate(closes[: index + 1])
    ]

    window = MainWindow(start_engine=False)
    try:
        calls: list[str] = []
        window._notifier.set_test_hook(lambda e, c, t: calls.append(c))
        rule = new_rule("upbit", "BTC/KRW", "15m", "golden_cross", {"fast": 5, "slow": 20})
        window._alert_engine.set_rules([rule])
        window._pending_key = "k"
        window._on_candles("k", "BTC/KRW", Interval.M15, candles)
        assert window._alerts._table.rowCount() == 1  # 차트 경로 발동
        fresh = new_rule("upbit", "BTC/KRW", "15m", "golden_cross", {"fast": 5, "slow": 20})
        window._alert_engine.set_rules([fresh])
        window._on_candles(
            alert_key("upbit", "BTC/KRW", "15m"), "BTC/KRW", Interval.M15, candles
        )  # 지표 키 경로 발동
        assert window._alerts._table.rowCount() == 2
        assert calls == ["popup", "sound", "popup", "sound"]
    finally:
        window.close()


def test_holdings_refresh_skips_unknown_symbol(qapp, tmp_path, monkeypatch) -> None:
    from crypto_alert import holdings as holdings_mod
    from crypto_alert.holdings import Holding

    monkeypatch.setattr(holdings_mod, "holdings_path", lambda: tmp_path / "h.json")
    panel = HoldingsPanel(load_watchlist())
    try:
        panel._append_row(Holding(symbol="ETH/KRW", quantity=1.0, avg_price=100.0))
        panel.on_ticker(
            Ticker(
                symbol="BTC/KRW",
                price=200.0,
                change_rate=0.0,
                volume=1.0,
                time=datetime.now(tz=UTC),
            )
        )
        panel.refresh_values()  # ETH 티커 없음 → 유지
        assert panel._table.item(0, 3).text() == "—"
    finally:
        panel.close()
