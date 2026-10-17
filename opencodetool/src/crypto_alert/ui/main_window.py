"""메인 윈도우: 탭(차트알림 / 종목 / 시가총액) + 메뉴(파일: 캡처·닫기, 보기: 탭 전환).

첫 화면은 차트+알림 탭이며, 시가총액·종목은 탭/메뉴로 전환해 본다.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.alerts import (
    AlertEngine,
    AlertEvent,
    Notifier,
    NotifySettings,
    NotifySettingsError,
    RulesError,
    alert_key,
    load_notify_settings,
    load_rules,
    parse_alert_key,
    save_notify_settings,
    save_rules,
)
from crypto_alert.config import load_watchlist
from crypto_alert.engine import DataEngine
from crypto_alert.exchanges.base import Interval, Ticker
from crypto_alert.marketcap import DEFAULT_USD_KRW, compute_ranking, load_supplies
from crypto_alert.ui.alert_panel import AlertPanel
from crypto_alert.ui.chart_panel import ChartPanel
from crypto_alert.ui.holdings_panel import HoldingsPanel
from crypto_alert.ui.marketcap_panel import MarketCapPanel
from crypto_alert.watchlist_types import Watchlist

logger = logging.getLogger(__name__)

__all__ = ["MainWindow"]

SNAPSHOT_INTERVAL_MS = 60_000  # 시총/환율 스냅샷 주기
REFRESH_INTERVAL_MS = 2_000  # 시총/보유 평가 갱신 주기
STALE_REFETCH_MIN_SECONDS = 10.0  # 구간 경계 어긋남 시 재요청 최소 간격 (폭주 방지)
ALERT_CANDLE_REFRESH_MS = 60_000  # 지표 규칙용 캔들 재조회 주기

# 탭 인덱스
TAB_CHART_ALERTS = 0  # 첫 화면: 차트 + 알림(조건/이력)
TAB_HOLDINGS = 1  # 종목 (보유종목)
TAB_MARKET = 2  # 시가총액 순위


class MainWindow(QMainWindow):
    """4패널 메인 윈도우."""

    def __init__(self, parent: QWidget | None = None, start_engine: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("코인 차트 알림 - Upbit / Binance / OKX")
        self.resize(1600, 950)

        self._watchlist: Watchlist = load_watchlist()
        self._ticker_cache: dict[str, Ticker] = {}
        self._usd_krw: float = DEFAULT_USD_KRW
        self._supplies = load_supplies()
        self._pending_key = ""
        self._last_candle_request = 0.0

        # --- 패널 ---
        self._chart = ChartPanel(self._watchlist)
        self._alerts = AlertPanel(self._watchlist)
        self._market = MarketCapPanel()
        self._holdings = HoldingsPanel(self._watchlist)

        # 첫 화면(차트알림 탭): 차트 | (알림 조건 / 알림 이력) — 절반씩
        chart_split = QSplitter(Qt.Orientation.Horizontal)
        chart_split.addWidget(self._chart)
        chart_split.addWidget(self._alerts)
        chart_split.setStretchFactor(0, 1)
        chart_split.setStretchFactor(1, 1)
        chart_split.setSizes([800, 800])

        # --- 탭: 차트알림 / 종목 / 시가총액 ---
        self._tabs = QTabWidget()
        self._tabs.addTab(chart_split, "차트알림")
        self._tabs.addTab(self._holdings, "종목")
        self._tabs.addTab(self._market, "시가총액")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        # --- 메뉴 (파일: 캡처/닫기, 보기: 종목/시가총액) ---
        self._build_menus()

        # --- 상태표시 ---
        self._upbit_status = QLabel("업비트: 대기")
        self._binance_status = QLabel("바이낸스: 대기")
        self._okx_status = QLabel("OKX: 대기")
        self._fx_status = QLabel(f"USD/KRW {self._usd_krw:,.1f}")
        status = self.statusBar()
        status.addWidget(self._upbit_status)
        status.addWidget(self._binance_status)
        status.addWidget(self._okx_status)
        status.addPermanentWidget(self._fx_status)

        # --- 엔진 ---
        self._engine = DataEngine(self)
        self._engine.ticker_received.connect(self._on_ticker)
        self._engine.candles_received.connect(self._on_candles)
        self._engine.snapshot_received.connect(self._on_snapshot)
        self._engine.connection_changed.connect(self._on_connection)
        self._engine.error_occurred.connect(self._on_error)

        # --- 알림 규칙 (5단계: 감지, 6단계: 발송) ---
        self._alert_engine = AlertEngine()
        try:
            initial_rules = load_rules()
        except RulesError as exc:
            logger.warning("%s", exc)
            self._on_error(f"알림 규칙 로드 실패: {exc}")
            initial_rules = []
        self._alert_engine.set_rules(initial_rules)
        self._alerts.set_rules(initial_rules)
        self._alerts.rules_changed.connect(self._on_rules_changed)

        # --- 알림 발송 (6단계: 팝업 + 사운드 + 텔레그램) ---
        try:
            initial_notify = load_notify_settings()
        except NotifySettingsError as exc:
            logger.warning("%s", exc)
            self._on_error(f"발송 설정 로드 실패: {exc}")
            initial_notify = NotifySettings()
        self._notifier = Notifier(initial_notify, parent=self)
        self._notifier.test_finished.connect(self._on_notify_test_finished)
        self._notifier.delivery_failed.connect(self._on_error)
        self._alerts.set_notify_settings(initial_notify)
        self._alerts.notify_settings_changed.connect(self._on_notify_settings_changed)
        self._alerts.notify_test_requested.connect(self._on_notify_test)

        # --- 시그널 연결 ---
        self._chart.selection_changed.connect(self._on_selection_changed)
        self._chart.candles_stale.connect(self._on_candles_stale)
        self._holdings.symbol_submitted.connect(self._on_holdings_symbol)

        # --- 타이머 ---
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh_displays)

        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.setInterval(SNAPSHOT_INTERVAL_MS)
        self._snapshot_timer.timeout.connect(self._request_snapshots)

        self._alert_timer = QTimer(self)
        self._alert_timer.setInterval(ALERT_CANDLE_REFRESH_MS)
        self._alert_timer.timeout.connect(self._request_alert_candles)

        if start_engine:
            self._engine.start()
            self._initial_load()
            self._refresh_timer.start()
            self._snapshot_timer.start()
            self._alert_timer.start()

    # ------------------------------------------------------------------
    # 메뉴 / 탭 전환
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        """상단 메뉴: 파일(캡처·닫기), 보기(종목·시가총액 = 탭 전환)."""
        file_menu = self.menuBar().addMenu("파일")
        capture_action = file_menu.addAction("캡처 (차트만)")
        capture_action.triggered.connect(self.capture_chart)
        file_menu.addSeparator()
        close_action = file_menu.addAction("닫기")
        close_action.triggered.connect(self.close)

        view_menu = self.menuBar().addMenu("보기")
        self._view_holdings_action = view_menu.addAction("종목")
        self._view_holdings_action.setCheckable(True)
        self._view_holdings_action.triggered.connect(
            lambda: self._tabs.setCurrentIndex(TAB_HOLDINGS)
        )
        self._view_market_action = view_menu.addAction("시가총액")
        self._view_market_action.setCheckable(True)
        self._view_market_action.triggered.connect(lambda: self._tabs.setCurrentIndex(TAB_MARKET))
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """보기 메뉴의 체크 표시를 현재 탭에 맞춘다."""
        self._view_holdings_action.setChecked(index == TAB_HOLDINGS)
        self._view_market_action.setChecked(index == TAB_MARKET)

    def capture_chart(self) -> None:
        """차트 패널만 PNG로 캡처해 저장한다 (파일 > 캡처)."""
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        default_name = (
            f"chart_{self._chart.symbol.replace('/', '-')}_{self._chart.interval.value}_{stamp}.png"
        )
        path, _selected = QFileDialog.getSaveFileName(
            self, "차트 캡처 저장", default_name, "PNG 이미지 (*.png)"
        )
        if not path:
            return
        pixmap = self._chart.grab()
        if pixmap.save(path):
            self.statusBar().showMessage(f"캡처 저장 완료: {path}", 10_000)
        else:
            QMessageBox.warning(self, "캡처", "캡처 이미지를 저장하지 못했습니다.")

    # ------------------------------------------------------------------
    # 초기 로드 / 주기적 요청
    # ------------------------------------------------------------------

    def _initial_load(self) -> None:
        self._request_candles()
        self._request_snapshots()
        self._request_alert_candles()

    def _request_snapshots(self) -> None:
        for exchange, symbols in self._watchlist.items():
            self._engine.request_snapshot(f"mc:{exchange}", exchange, list(symbols))
        self._engine.request_snapshot("fx", "upbit", ["USDT/KRW"])

    def _request_candles(self) -> None:
        self._pending_key = self._chart.request_key
        self._last_candle_request = time.monotonic()
        self._engine.request_candles(
            self._pending_key,
            self._chart.exchange,
            self._chart.symbol,
            self._chart.interval,
        )

    # ------------------------------------------------------------------
    # 엔진 시그널
    # ------------------------------------------------------------------

    def _on_ticker(self, symbol: str, ticker: Ticker) -> None:
        self._ticker_cache[symbol] = ticker
        if symbol == self._chart.symbol:
            self._chart.on_ticker(ticker)
        self._holdings.on_ticker(ticker)
        for event in self._alert_engine.check_ticker(ticker):
            self._dispatch_alert(event)

    def _on_candles(self, key: str, _symbol: str, _interval: object, candles: object) -> None:
        if key == self._pending_key:
            if isinstance(candles, list):
                self._chart.set_candles(candles)
                for event in self._alert_engine.check_candles(
                    self._chart.exchange,
                    self._chart.symbol,
                    self._chart.interval.value,
                    candles,
                ):
                    self._dispatch_alert(event)
            return
        parsed = parse_alert_key(key)
        if parsed is None:
            return  # 오래된 응답 무시
        if isinstance(candles, list):
            exchange, symbol, interval_value = parsed
            for event in self._alert_engine.check_candles(
                exchange, symbol, interval_value, candles
            ):
                self._dispatch_alert(event)

    def _on_snapshot(self, key: str, tickers: object) -> None:
        if not isinstance(tickers, list):
            return
        if key == "fx":
            for item in tickers:
                if isinstance(item, Ticker) and item.price > 0:
                    self._usd_krw = item.price
                    self._fx_status.setText(f"USD/KRW {self._usd_krw:,.1f}")
            return
        for item in tickers:
            if isinstance(item, Ticker):
                self._ticker_cache[item.symbol] = item
        self._refresh_displays()

    def _on_connection(self, exchange: str, connected: bool) -> None:
        labels = {"upbit": "업비트", "binance": "바이낸스", "okx": "OKX"}
        targets = {
            "upbit": self._upbit_status,
            "binance": self._binance_status,
            "okx": self._okx_status,
        }
        label = labels.get(exchange, exchange)
        target = targets.get(exchange)
        if target is None:
            return
        state = "연결" if connected else "끊김"
        target.setText(f"{label}: {state}")

    def _on_error(self, message: str) -> None:
        logger.warning("%s", message)
        self.statusBar().showMessage(message, 10_000)

    # ------------------------------------------------------------------
    # 패널 시그널
    # ------------------------------------------------------------------

    def _on_selection_changed(self, _exchange: str, _symbol: str, _interval: object) -> None:
        self._request_candles()

    def _on_candles_stale(self) -> None:
        """캔들이 구간을 넘겨 재조회 필요 (최소 간격 보장으로 폭주 방지)."""
        now = time.monotonic()
        if now - self._last_candle_request < STALE_REFETCH_MIN_SECONDS:
            return
        self._request_candles()

    def _on_holdings_symbol(self, symbol: str) -> None:
        """보유종목에 새 종목이 추가되면 해당 심볼 스냅샷을 받아온다."""
        exchange = self._exchange_for_symbol(symbol)
        self._engine.request_snapshot(f"holding:{symbol}", exchange, [symbol])

    def _exchange_for_symbol(self, symbol: str) -> str:
        """감시 목록에서 심볼이 속한 거래소를 찾는다 (없으면 접미사로 추정)."""
        for exchange, symbols in self._watchlist.items():
            if symbol in symbols:
                return exchange
        return "upbit" if symbol.endswith("/KRW") else "binance"

    # ------------------------------------------------------------------
    # 알림 규칙 (5단계 감지 / 6단계 발송)
    # ------------------------------------------------------------------

    def _on_rules_changed(self, rules: list) -> None:
        """규칙 추가/수정/삭제/토글 후 저장 + 엔진 반영 + 캔들 요청."""
        try:
            save_rules(rules)
        except RulesError as exc:
            self._on_error(f"알림 규칙 저장 실패: {exc}")
        self._alert_engine.set_rules(rules)
        self._request_alert_candles()

    def _request_alert_candles(self) -> None:
        """지표 규칙이 보는 (거래소, 종목, 주기)의 캔들을 요청한다 (60초 주기)."""
        for exchange, symbol, interval_value in self._alert_engine.needs_candles():
            try:
                interval = Interval(interval_value)
            except ValueError:
                continue
            self._engine.request_candles(
                alert_key(exchange, symbol, interval_value), exchange, symbol, interval
            )

    def _dispatch_alert(self, event: AlertEvent) -> None:
        """발동한 알림을 이력에 남기고 설정된 채널로 발송한다."""
        logger.info("알림 발동: %s", event.message)
        self.show_alert(event.symbol, event.message)
        self._notifier.dispatch(event)

    def _on_notify_settings_changed(self, settings: object) -> None:
        """발송 설정 변경 후 저장 + 발송기 반영."""
        if not isinstance(settings, NotifySettings):
            return
        try:
            save_notify_settings(settings)
        except NotifySettingsError as exc:
            self._on_error(f"발송 설정 저장 실패: {exc}")
        self._notifier.update_settings(settings)

    def _on_notify_test(self, settings: object) -> None:
        """다이얼로그의 테스트 버튼 → 입력 중인 값으로 테스트 발송."""
        if isinstance(settings, NotifySettings):
            self._notifier.send_test(settings)

    def _on_notify_test_finished(self, ok: bool, detail: str) -> None:
        """테스트 발송 결과를 팝업으로 보여준다."""
        if ok:
            QMessageBox.information(self, "테스트 발송", detail)
        else:
            QMessageBox.warning(self, "테스트 발송", detail)

    def _refresh_displays(self) -> None:
        exchanges = {
            symbol: exchange for exchange, symbols in self._watchlist.items() for symbol in symbols
        }
        ranks = compute_ranking(
            self._ticker_cache, self._supplies, self._usd_krw, exchanges=exchanges
        )
        self._market.update_ranks(ranks)
        self._holdings.refresh_values()

    # ------------------------------------------------------------------
    # 수명주기
    # ------------------------------------------------------------------

    def reload_watchlist(self) -> None:
        """감시 목록 변경 후 패널/엔진을 새로고침한다."""
        try:
            self._watchlist = load_watchlist()
        except Exception as exc:  # noqa: BLE001 — 사용자 편집 파일 방어
            self._on_error(f"감시 목록 로드 실패: {exc}")
            return
        self._chart.set_watchlist(self._watchlist)
        self._holdings.set_watchlist(self._watchlist)
        self._alerts.set_watchlist(self._watchlist)
        self._engine.reload_watchlist()
        self._initial_load()

    def show_alert(self, symbol: str, message: str) -> None:
        """알림 패널에 이력을 남긴다 (5단계 알림 엔진에서 호출)."""
        self._alerts.add_alert(datetime.now(tz=UTC), symbol, message)

    def closeEvent(self, event) -> None:
        self._refresh_timer.stop()
        self._snapshot_timer.stop()
        self._alert_timer.stop()
        self._engine.stop()
        super().closeEvent(event)
