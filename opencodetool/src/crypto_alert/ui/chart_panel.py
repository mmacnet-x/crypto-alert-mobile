"""차트 패널: 캔들차트 + 거래량 + 보조지표(MA/BB/RSI/MACD) + 선택 툴바."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPicture
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.buckets import interval_seconds, is_new_bucket
from crypto_alert.exchanges.base import Interval, Ticker
from crypto_alert.formatting import format_change, format_price
from crypto_alert.indicators import DEFAULT_PARAMS, bollinger, macd, rsi, sma
from crypto_alert.watchlist_types import Watchlist

__all__ = [
    "MA_PERIODS_BY_INTERVAL",
    "CandlestickItem",
    "ChartPanel",
    "HistogramItem",
    "VolumeBarsItem",
    "ma_periods_for",
]

# 업비트 관행: 상승=빨강, 하락=파랑
COLOR_UP = QColor("#ef5350")
COLOR_DOWN = QColor("#2979ff")
BG = "#131722"
FG = "#d1d4dc"

# (버튼 라벨, Interval 값)
INTERVALS: tuple[tuple[str, str], ...] = (
    ("15분", Interval.M15.value),
    ("4시간", Interval.H4.value),
    ("1일", Interval.D1.value),
    ("1주", Interval.W1.value),
    ("1월", Interval.MN.value),
)

# 주기별 MA 기간 (15분=8/96/192, 4시간=6/42/168, 일/주/월=60/120/200)
MA_PERIODS_BY_INTERVAL: dict[str, tuple[int, ...]] = {
    Interval.M15.value: (8, 96, 192),
    Interval.H4.value: (6, 42, 168),
    Interval.D1.value: (60, 120, 200),
    Interval.W1.value: (60, 120, 200),
    Interval.MN.value: (60, 120, 200),
}


def ma_periods_for(interval_value: str) -> tuple[int, ...]:
    """주기별 MA 기간 (미등록 주기는 일봉 기본값)."""
    return MA_PERIODS_BY_INTERVAL.get(interval_value, MA_PERIODS_BY_INTERVAL[Interval.D1.value])


# 보조지표 라벨(툴바)과 내부 키
INDICATORS: tuple[tuple[str, str], ...] = (
    ("MA", "MA"),
    ("BB", "BB"),
    ("RSI", "RSI"),
    ("MACD", "MACD"),
)

# 지표 선 색상 (MA는 주기별 3개 — 짧은/중간/긴 순으로 동일 색상 배정)
COLOR_MA: dict[int, str] = {
    # 15분봉: 8 / 96 / 192
    8: "#ffa726",
    96: "#42a5f5",
    192: "#ab47bc",
    # 4시간봉: 6 / 42 / 168
    6: "#ffa726",
    42: "#42a5f5",
    168: "#ab47bc",
    # 일/주/월봉: 60 / 120 / 200
    60: "#ffa726",
    120: "#42a5f5",
    200: "#ab47bc",
}
COLOR_BB_EDGE = "#607d8b"
COLOR_BB_MID = "#ffca28"
COLOR_RSI = "#7c4dff"
COLOR_RSI_GUIDE = "#5c6370"
COLOR_MACD_LINE = "#42a5f5"
COLOR_MACD_SIGNAL = "#ef5350"

# 패널 높이 제한: 캔들 차트가 대부분을 차지하도록 (px)
VOLUME_MAX_HEIGHT = 110
SUBPLOT_MAX_HEIGHT = 100
CANDLE_MIN_HEIGHT = 160

pg.setConfigOptions(background=BG, foreground=FG)


class CandlestickItem(pg.GraphicsObject):
    """QPicture 기반 캔들(심지+몸통) 한 벌."""

    def __init__(self, candles: list, width_seconds: float) -> None:
        super().__init__()
        self._candles = candles
        self._width_seconds = width_seconds
        self._picture = QPicture()
        self._draw()

    def _draw(self) -> None:
        painter = QPainter(self._picture)
        body_width = max(self._width_seconds * 0.6, 1e-9)
        span = max((c.high - c.low for c in self._candles), default=0.0)
        doji_height = max(span * 0.004, 1e-9)
        for candle in self._candles:
            x = candle.time.timestamp()
            color = COLOR_UP if candle.close >= candle.open else COLOR_DOWN
            pen = QPen(color)
            pen.setWidthF(0)  # 0 = 헤어라인
            painter.setPen(pen)
            painter.setBrush(QBrush(color))
            painter.drawLine(QLineF(QPointF(x, candle.low), QPointF(x, candle.high)))
            top = max(candle.open, candle.close)
            bottom = min(candle.open, candle.close)
            height = bottom - top
            if height <= 0:  # 도지: 아주 얇은 막대로 표시
                height = doji_height
            painter.drawRect(QRectF(x - body_width / 2, top, body_width, height))
        painter.end()

    def paint(self, painter: QPainter, option: object, widget: object = None) -> None:
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:
        # QPicture 경계는 정밀도가 낮아 수동 계산한다 (timestamp는 초 단위)
        if not self._candles:
            return QRectF()
        xs = [c.time.timestamp() for c in self._candles]
        lo = min(c.low for c in self._candles)
        hi = max(c.high for c in self._candles)
        half = max(self._width_seconds * 0.6, 1e-9) / 2
        width = max(xs) - min(xs) + 2 * half
        return QRectF(min(xs) - half, lo, width, max(hi - lo, 1e-9))


class VolumeBarsItem(pg.GraphicsObject):
    """QPicture 기반 거래량 막대 한 벌."""

    def __init__(self, candles: list, width_seconds: float) -> None:
        super().__init__()
        self._candles = candles
        self._width_seconds = width_seconds
        self._picture = QPicture()
        self._draw()

    def _draw(self) -> None:
        painter = QPainter(self._picture)
        body_width = max(self._width_seconds * 0.6, 1e-9)
        for candle in self._candles:
            x = candle.time.timestamp()
            color = QColor(COLOR_UP if candle.close >= candle.open else COLOR_DOWN)
            color.setAlpha(150)
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(color))
            painter.drawRect(QRectF(x - body_width / 2, 0, body_width, max(candle.volume, 0.0)))
        painter.end()

    def paint(self, painter: QPainter, option: object, widget: object = None) -> None:
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:
        if not self._candles:
            return QRectF()
        xs = [c.time.timestamp() for c in self._candles]
        hi = max((c.volume for c in self._candles), default=0.0)
        half = max(self._width_seconds * 0.6, 1e-9) / 2
        width = max(xs) - min(xs) + 2 * half
        return QRectF(min(xs) - half, 0, width, max(hi, 1e-9))


class HistogramItem(pg.GraphicsObject):
    """QPicture 기반 MACD 히스토그램 막대 한 벌 (0 기준 위/아래)."""

    def __init__(self, xs: np.ndarray, values: np.ndarray, width_seconds: float) -> None:
        super().__init__()
        self._xs = xs
        self._values = values
        self._width_seconds = width_seconds
        self._picture = QPicture()
        self._draw()

    def _draw(self) -> None:
        painter = QPainter(self._picture)
        body_width = max(self._width_seconds * 0.6, 1e-9)
        for x, value in zip(self._xs, self._values, strict=True):
            if not np.isfinite(value):
                continue
            color = QColor(COLOR_UP if value >= 0 else COLOR_DOWN)
            color.setAlpha(170)
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(color))
            painter.drawRect(QRectF(x - body_width / 2, 0.0, body_width, value))
        painter.end()

    def paint(self, painter: QPainter, option: object, widget: object = None) -> None:
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:
        if self._xs.size == 0:
            return QRectF()
        finite = self._values[np.isfinite(self._values)]
        lo = min(0.0, float(finite.min())) if finite.size else 0.0
        hi = max(0.0, float(finite.max())) if finite.size else 0.0
        half = max(self._width_seconds * 0.6, 1e-9) / 2
        width = float(self._xs.max() - self._xs.min()) + 2 * half
        return QRectF(float(self._xs.min()) - half, lo, width, max(hi - lo, 1e-9))


class ChartPanel(QWidget):
    """캔들/거래량 차트 + 보조지표 + 선택 툴바."""

    # (거래소, 심볼, Interval)
    selection_changed = pyqtSignal(str, str, object)
    # 현재 캔들이 구간을 넘어 재조회가 필요함
    candles_stale = pyqtSignal()

    def __init__(self, watchlist: Watchlist, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._watchlist = watchlist
        self._candles: list = []
        self._interval: str = Interval.M15.value
        self._active_periods: tuple[int, ...] = ma_periods_for(self._interval)
        self._pending_ticker: Ticker | None = None

        # --- 툴바 ---
        self._exchange_combo = QComboBox()
        self._exchange_combo.addItem("업비트", "upbit")
        self._exchange_combo.addItem("바이낸스", "binance")
        self._exchange_combo.addItem("OKX", "okx")

        self._symbol_combo = QComboBox()

        self._interval_group = QButtonGroup(self)
        self._interval_group.setExclusive(True)
        self._interval_buttons: dict[str, QToolButton] = {}
        for label, value in INTERVALS:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("interval", value)
            self._interval_group.addButton(button)
            self._interval_buttons[value] = button
            button.clicked.connect(self._on_interval_clicked)
        self._interval_buttons[Interval.M15.value].setChecked(True)

        self._price_label = QLabel("—")
        self._price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._price_label.setMinimumWidth(260)

        # 보조지표 토글 (각 지표 독립 on/off, 무한 확장 구조)
        self._indicators: dict[str, bool] = {key: key == "MA" for _label, key in INDICATORS}
        self._indicator_buttons: dict[str, QToolButton] = {}
        for label, key in INDICATORS:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("indicator", key)
            button.setToolTip(self._indicator_tooltip(key))
            button.setChecked(self._indicators[key])
            button.clicked.connect(self._on_indicator_clicked)
            self._indicator_buttons[key] = button

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("거래소:"))
        toolbar.addWidget(self._exchange_combo)
        toolbar.addWidget(QLabel("종목:"))
        toolbar.addWidget(self._symbol_combo)
        toolbar.addSpacing(12)
        for _label, value in INTERVALS:
            toolbar.addWidget(self._interval_buttons[value])
        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("지표:"))
        for _label, key in INDICATORS:
            toolbar.addWidget(self._indicator_buttons[key])
        toolbar.addStretch(1)
        toolbar.addWidget(self._price_label)

        # --- 차트 (위: 캔들, 그 아래: 거래량, 끝: RSI/MACD 서브패널) ---
        self._time_axis = pg.DateAxisItem(orientation="bottom")
        self._glw = pg.GraphicsLayoutWidget()
        self._candle_plot = self._glw.addPlot(axisItems={"bottom": self._time_axis})
        self._candle_plot.showGrid(x=True, y=True, alpha=0.15)
        self._candle_plot.setLabel("left", "가격")
        self._candle_plot.setMouseEnabled(x=True, y=True)

        self._volume_plot = self._glw.addPlot(
            row=1, col=0, axisItems={"bottom": pg.DateAxisItem(orientation="bottom")}
        )
        self._volume_plot.showGrid(x=True, y=True, alpha=0.15)
        self._volume_plot.setLabel("left", "거래량")
        self._volume_plot.setXLink(self._candle_plot)
        self._volume_plot.setMouseEnabled(x=True, y=True)
        self._volume_plot.setMaximumHeight(VOLUME_MAX_HEIGHT)

        # 오버레이 곡선 (MA/BB) — 캔들 플롯에 겹쳐 그림
        # MA는 주기별 3기간을 미리 만들어 두고 현재 주기의 3개만 표시한다
        self._ma_curves: dict[int, pg.PlotDataItem] = {
            period: pg.PlotDataItem(pen=pg.mkPen(COLOR_MA[period], width=1.5), connect="finite")
            for period in sorted(COLOR_MA)
        }
        self._bb_curves: dict[str, pg.PlotDataItem] = {
            "upper": pg.PlotDataItem(
                pen=pg.mkPen(COLOR_BB_EDGE, width=1, style=Qt.PenStyle.DashLine),
                connect="finite",
            ),
            "mid": pg.PlotDataItem(
                pen=pg.mkPen(COLOR_BB_MID, width=1, style=Qt.PenStyle.DashLine),
                connect="finite",
            ),
            "lower": pg.PlotDataItem(
                pen=pg.mkPen(COLOR_BB_EDGE, width=1, style=Qt.PenStyle.DashLine),
                connect="finite",
            ),
        }

        # 서브패널 (미리 만들어 두었다가 토글 시 ci에 add/remove)
        self._rsi_plot = self._make_subplot("RSI", (30.0, 70.0))
        self._rsi_curve = pg.PlotDataItem(pen=pg.mkPen(COLOR_RSI, width=1.5), connect="finite")
        self._rsi_plot.addItem(self._rsi_curve)
        self._rsi_plot.setYRange(0, 100, padding=0)

        self._macd_plot = self._make_subplot("MACD", (0.0,))
        self._macd_curve = pg.PlotDataItem(
            pen=pg.mkPen(COLOR_MACD_LINE, width=1.5), connect="finite"
        )
        self._macd_signal_curve = pg.PlotDataItem(
            pen=pg.mkPen(COLOR_MACD_SIGNAL, width=1.5), connect="finite"
        )
        self._macd_plot.addItem(self._macd_curve)
        self._macd_plot.addItem(self._macd_signal_curve)
        self._macd_hist: HistogramItem | None = None

        self._candle_item: CandlestickItem | None = None
        self._volume_item: VolumeBarsItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._glw, stretch=1)

        self._exchange_combo.currentIndexChanged.connect(self._on_exchange_changed)
        self._symbol_combo.currentIndexChanged.connect(self._on_symbol_changed)

        # 실시간 갱신 스로틀 (초당 수십 회 수신 대비)
        self._throttle = QTimer(self)
        self._throttle.setInterval(250)
        self._throttle.timeout.connect(self._flush_ticker)

        self._relayout_subplots()
        self._sync_time_axis()
        self._populate_symbols()

    # ------------------------------------------------------------------
    # 선택 상태
    # ------------------------------------------------------------------

    @property
    def exchange(self) -> str:
        return str(self._exchange_combo.currentData())

    @property
    def symbol(self) -> str:
        return str(self._symbol_combo.currentText())

    @property
    def interval(self) -> Interval:
        return Interval(self._interval)

    @property
    def request_key(self) -> str:
        return f"{self.exchange}:{self.symbol}:{self._interval}"

    def _populate_symbols(self) -> None:
        self._symbol_combo.blockSignals(True)
        self._symbol_combo.clear()
        self._symbol_combo.addItems(self._watchlist.get(self.exchange, []))
        self._symbol_combo.blockSignals(False)

    def _on_exchange_changed(self, _index: int) -> None:
        self._populate_symbols()
        self._emit_selection()

    def _on_symbol_changed(self, _index: int) -> None:
        self._emit_selection()

    def _on_interval_clicked(self) -> None:
        sender = self.sender()
        if isinstance(sender, QToolButton):
            value = sender.property("interval")
            if isinstance(value, str):
                self._interval = value
                self._active_periods = ma_periods_for(value)
                self._indicator_buttons["MA"].setToolTip(self._indicator_tooltip("MA"))
                if self._indicators["MA"]:
                    # 이전 주기 MA선을 분리 (새 주기선은 캔들 수신 시 표시)
                    self._sync_overlay_curves()
        self._emit_selection()

    def _emit_selection(self) -> None:
        self.selection_changed.emit(self.exchange, self.symbol, self._interval)

    def set_watchlist(self, watchlist: Watchlist) -> None:
        """감시 목록 변경 후 콤보를 새로고침한다."""
        self._watchlist = watchlist
        self._populate_symbols()

    # ------------------------------------------------------------------
    # 보조지표 (MA / BB 오버레이 + RSI / MACD 서브패널)
    # ------------------------------------------------------------------

    def _indicator_tooltip(self, key: str) -> str:
        """지표 버튼 툴팁 (MA는 현재 주기의 기간을 표시)."""
        p = DEFAULT_PARAMS
        if key == "MA":
            periods = "/".join(str(n) for n in self._active_periods)
            return f"이동평균 ({periods})"
        if key == "BB":
            return f"볼린저밴드 ({p.bollinger_period}, {p.bollinger_std:g}σ)"
        if key == "RSI":
            return f"RSI ({p.rsi_period})"
        if key == "MACD":
            return f"MACD ({p.macd_fast}, {p.macd_slow}, {p.macd_signal})"
        return key

    def _make_subplot(self, label: str, guides: tuple[float, ...]) -> pg.PlotItem:
        """서브패널 하나를 만든다 (토글 전까지 레이아웃에는 넣지 않는다)."""
        plot = pg.PlotItem(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        plot.showGrid(x=True, y=True, alpha=0.15)
        plot.setLabel("left", label)
        plot.setXLink(self._candle_plot)  # x축 동기화 (연결 시 x autrange 자동 off)
        plot.vb.enableAutoRange(axis="y", enable=False)  # y범위는 코드에서만 조절
        plot.setMouseEnabled(x=True, y=True)
        plot.setMaximumHeight(SUBPLOT_MAX_HEIGHT)
        pen = pg.mkPen(COLOR_RSI_GUIDE, width=1, style=Qt.PenStyle.DashLine)
        for level in guides:
            plot.addItem(pg.InfiniteLine(pos=level, angle=0, pen=pen, movable=False))
        plot.getAxis("bottom").setVisible(False)  # 최하단 여부는 _sync_time_axis가 결정
        return plot

    def _relayout_subplots(self) -> None:
        """토글 상태에 따라 RSI/MACD 서브패널을 레이아웃(행 2~)에 넣고 뺀다."""
        layout = self._glw.ci
        for plot in (self._rsi_plot, self._macd_plot):
            if plot in layout.items:
                layout.removeItem(plot)
        row = 2
        if self._indicators["RSI"]:
            layout.addItem(self._rsi_plot, row, 0)
            row += 1
        if self._indicators["MACD"]:
            layout.addItem(self._macd_plot, row, 0)

    def _sync_time_axis(self) -> None:
        """시간축 라벨은 최하단에 표시된 플롯에만 보여준다."""
        bottom = self._volume_plot
        if self._indicators["RSI"]:
            bottom = self._rsi_plot
        if self._indicators["MACD"]:
            bottom = self._macd_plot
        for plot in (self._candle_plot, self._volume_plot, self._rsi_plot, self._macd_plot):
            plot.getAxis("bottom").setVisible(plot is bottom)

    def _on_indicator_clicked(self) -> None:
        sender = self.sender()
        if isinstance(sender, QToolButton):
            key = sender.property("indicator")
            if isinstance(key, str) and key in self._indicators:
                self._indicators[key] = sender.isChecked()
        self._relayout_subplots()
        self._sync_time_axis()
        if self._candles:
            self._sync_overlay_curves()
            self._expand_for_overlays()  # 새로 켠 오버레이를 뷰에 포함

    def _update_indicators(self, force: bool = False) -> None:
        """캔들 데이터로 지표 곡선과 MACD 히스토그램을 다시 계산한다."""
        if not self._candles:
            self._clear_indicator_data()
            return
        xs = np.fromiter(
            (c.time.timestamp() for c in self._candles),
            dtype=float,
            count=len(self._candles),
        )
        closes = np.fromiter(
            (c.close for c in self._candles), dtype=float, count=len(self._candles)
        )
        p = DEFAULT_PARAMS
        for period in self._active_periods:
            self._ma_curves[period].setData(xs, sma(closes, period))
        mid, upper, lower = bollinger(closes, p.bollinger_period, p.bollinger_std)
        self._bb_curves["mid"].setData(xs, mid)
        self._bb_curves["upper"].setData(xs, upper)
        self._bb_curves["lower"].setData(xs, lower)
        self._rsi_curve.setData(xs, rsi(closes, p.rsi_period))
        line, sig, hist = macd(closes, p.macd_fast, p.macd_slow, p.macd_signal)
        self._macd_curve.setData(xs, line)
        self._macd_signal_curve.setData(xs, sig)
        if self._macd_hist is not None:
            self._macd_plot.removeItem(self._macd_hist)
        self._macd_hist = HistogramItem(xs, hist, float(interval_seconds(self.interval)))
        self._macd_hist.setZValue(-1)  # 히스토그램은 MACD/시그널 선 아래에
        self._macd_plot.addItem(self._macd_hist)
        self._sync_overlay_curves()
        self._fit_macd_y(line, sig, hist, force=force)

    def _clear_indicator_data(self) -> None:
        """캔들이 없으면 지표 데이터를 비운다."""
        empty = np.empty(0)
        for curve in (
            *self._ma_curves.values(),
            *self._bb_curves.values(),
            self._rsi_curve,
            self._macd_curve,
            self._macd_signal_curve,
        ):
            curve.setData(empty, empty)
        if self._macd_hist is not None:
            self._macd_plot.removeItem(self._macd_hist)
            self._macd_hist = None
        self._sync_overlay_curves()

    def _sync_overlay_curves(self) -> None:
        """켜진 오버레이만 캔들 플롯에 붙인다 (clear() 후 재연결 포함)."""
        # 표시 대상이 된 주기의 MA선은 플롯에서 분리한다
        active = {self._ma_curves[period] for period in self._active_periods}
        for curve in self._ma_curves.values():
            if curve not in active and curve in self._candle_plot.items:
                self._candle_plot.removeItem(curve)
        groups = (
            ("MA", (self._ma_curves[period] for period in self._active_periods)),
            ("BB", self._bb_curves.values()),
        )
        for key, curves in groups:
            enabled = self._indicators[key]
            for curve in curves:
                present = curve in self._candle_plot.items
                if enabled and not present:
                    self._candle_plot.addItem(curve)
                elif not enabled and present:
                    self._candle_plot.removeItem(curve)

    def _enabled_overlay_curves(self) -> list[pg.PlotDataItem]:
        """현재 켜진 오버레이(MA/BB) 곡선 목록 (MA는 현재 주기 기간만)."""
        curves: list[pg.PlotDataItem] = []
        if self._indicators["MA"]:
            curves.extend(self._ma_curves[period] for period in self._active_periods)
        if self._indicators["BB"]:
            curves.extend(self._bb_curves.values())
        return curves

    def _overlay_bounds(self) -> tuple[float, float] | None:
        """켜진 오버레이의 전체 값 범위 (없으면 None)."""
        lows: list[float] = []
        highs: list[float] = []
        for curve in self._enabled_overlay_curves():
            finite = self._finite_data(curve)
            if finite is not None:
                lows.append(float(finite.min()))
                highs.append(float(finite.max()))
        if not lows:
            return None
        return min(lows), max(highs)

    def _overlay_last_values(self) -> list[float]:
        """켜진 오버레이의 마지막 유효값 (현재 시점 근사)."""
        out: list[float] = []
        for curve in self._enabled_overlay_curves():
            finite = self._finite_data(curve)
            if finite is not None and finite.size:
                out.append(float(finite[-1]))
        return out

    def _expand_for_overlays(self) -> None:
        """오버레이를 새로 켰을 때 오버레이 전체 범위가 뷰에 포함되게 확장."""
        bounds = self._overlay_bounds()
        if bounds is not None:
            self._expand_view(self._candle_plot, [bounds[0], bounds[1]])

    @staticmethod
    def _finite_data(curve: pg.PlotDataItem) -> np.ndarray | None:
        """곡선의 y값 중 유한한 값만 반환 (데이터 없으면 None)."""
        data = curve.yData
        if data is None or data.size == 0:
            return None
        finite = data[np.isfinite(data)]
        return finite if finite.size else None

    def _fit_macd_y(
        self,
        line: np.ndarray,
        sig: np.ndarray,
        hist: np.ndarray,
        *,
        force: bool = False,
    ) -> None:
        """MACD y축: 새 데이터이면 전체에 맞추고, 실시간에는 바깥으로만 넓힌다."""
        mins: list[float] = []
        maxs: list[float] = []
        lasts: list[float] = []
        for arr in (line, sig, hist):
            finite = arr[np.isfinite(arr)]
            if not finite.size:
                continue
            mins.append(float(finite.min()))
            maxs.append(float(finite.max()))
            lasts.append(float(finite[-1]))
        if force:
            if not mins:
                return
            lo, hi = min(mins), max(maxs)
            pad = max((hi - lo) * 0.1, 1e-12)
            self._macd_plot.setYRange(lo - pad, hi + pad, padding=0)
            return
        self._expand_view(self._macd_plot, lasts)

    # ------------------------------------------------------------------
    # 데이터 표시
    # ------------------------------------------------------------------

    def set_candles(self, candles: list) -> None:
        """캔들 전체를 교체하고 축 범위를 재설정한다."""
        self._candles = list(candles)
        self._pending_ticker = None
        if not self._candles:
            self._clear_items()
            return
        width = float(interval_seconds(self.interval))
        self._candle_item = CandlestickItem(self._candles, width)
        self._volume_item = VolumeBarsItem(self._candles, width)
        self._candle_plot.clear()
        self._volume_plot.clear()
        self._candle_plot.addItem(self._candle_item)
        self._volume_plot.addItem(self._volume_item)
        self._update_indicators(force=True)
        self._reset_ranges()

    def _clear_items(self) -> None:
        self._candle_plot.clear()
        self._volume_plot.clear()
        self._candle_item = None
        self._volume_item = None
        self._update_indicators()

    def _reset_ranges(self) -> None:
        if not self._candles:
            return
        first = self._candles[0].time.timestamp()
        last = self._candles[-1].time.timestamp()
        span = max(last - first, 60.0)
        self._candle_plot.setXRange(first - span * 0.02, last + span * 0.05, padding=0)

        lows = [c.low for c in self._candles]
        highs = [c.high for c in self._candles]
        bounds = self._overlay_bounds()
        if bounds is not None:
            lows.append(bounds[0])
            highs.append(bounds[1])
        lo, hi = min(lows), max(highs)
        margin = max((hi - lo) * 0.06, hi * 0.001)
        self._candle_plot.setYRange(lo - margin, hi + margin, padding=0)

        max_vol = max((c.volume for c in self._candles), default=0.0)
        self._volume_plot.setYRange(0, max_vol * 1.15, padding=0)

    def on_ticker(self, ticker: Ticker) -> None:
        """현재 종목 실시간 시세: 라벨 즉시 갱신, 캔들은 스로틀 적용."""
        self._update_price_label(ticker)
        self._pending_ticker = ticker
        if not self._throttle.isActive():
            self._throttle.start()

    def _flush_ticker(self) -> None:
        ticker = self._pending_ticker
        self._pending_ticker = None
        self._throttle.stop()
        if ticker is None or not self._candles:
            return
        last = self._candles[-1]
        if is_new_bucket(ticker.time, last.time, self.interval):
            self.candles_stale.emit()
            return
        if ticker.time < last.time:
            return
        updated = replace(
            last,
            close=ticker.price,
            high=max(last.high, ticker.price),
            low=min(last.low, ticker.price),
        )
        self._candles[-1] = updated
        width = float(interval_seconds(self.interval))
        self._candle_item = CandlestickItem(self._candles, width)
        self._candle_plot.clear()
        self._candle_plot.addItem(self._candle_item)
        self._update_indicators()
        self._expand_y(ticker.price)

    @staticmethod
    def _expand_view(plot: pg.PlotItem, values: list[float]) -> None:
        """values가 현재 y뷰 밖이면 y축을 넓힌다 (축소는 하지 않는다)."""
        if not values:
            return
        lo, hi = plot.viewRange()[1]
        span = max(hi - lo, 1e-12)
        v_lo, v_hi = min(values), max(values)
        new_lo = lo
        new_hi = hi
        if v_lo < new_lo:
            new_lo = v_lo - span * 0.05
        if v_hi > new_hi:
            new_hi = v_hi + span * 0.05
        if (new_lo, new_hi) != (lo, hi):
            plot.setYRange(new_lo, new_hi, padding=0)

    def _expand_y(self, price: float | None = None) -> None:
        """현재가와 오버레이 마지막 값이 뷰 밖이면 캔들 y축을 확장한다."""
        values = self._overlay_last_values()
        if price is not None:
            values.append(price)
        self._expand_view(self._candle_plot, values)

    def _update_price_label(self, ticker: Ticker) -> None:
        color = "#ef5350" if ticker.change_rate >= 0 else "#2979ff"
        text = f"{format_price(ticker.price)}  {format_change(ticker.change_rate)}"
        self._price_label.setText(text)
        self._price_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 15px;")

    def last_candle_time(self) -> datetime | None:
        return self._candles[-1].time if self._candles else None
