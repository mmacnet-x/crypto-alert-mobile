"""보유종목 패널: 사용자가 직접 입력하는 수동 포지션 표."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.exchanges.base import Ticker
from crypto_alert.exchanges.symbols import SymbolError, normalize_symbol
from crypto_alert.formatting import format_change, format_price
from crypto_alert.holdings import Holding, load_holdings, save_holdings, value_of
from crypto_alert.watchlist_types import Watchlist

logger = logging.getLogger(__name__)

__all__ = ["HoldingsPanel"]

HEADERS = ("종목", "수량", "평균단가", "현재가", "평가금액", "손익", "손익률")
COLUMN_COUNT = len(HEADERS)


class HoldingsPanel(QWidget):
    """보유종목 수동 입력/평가 표 (JSON 자동 저장)."""

    # 감시 목록에 없는 종목도 직접 입력할 수 있다
    symbol_submitted = pyqtSignal(str)

    def __init__(self, watchlist: Watchlist, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._watchlist = watchlist
        self._prices: dict[str, Ticker] = {}

        # --- 입력 줄 ---
        self._symbol_combo = QComboBox()
        self._symbol_combo.setEditable(True)
        self._symbol_combo.setMinimumWidth(160)
        self._populate_symbols()

        self._quantity_edit = QLineEdit()
        self._quantity_edit.setPlaceholderText("수량")
        self._avg_price_edit = QLineEdit()
        self._avg_price_edit.setPlaceholderText("평균단가")

        add_button = QPushButton("추가")
        add_button.clicked.connect(self._on_add)
        remove_button = QPushButton("선택 삭제")
        remove_button.clicked.connect(self._on_remove)
        save_button = QPushButton("저장")
        save_button.clicked.connect(self._save)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("종목:"))
        input_row.addWidget(self._symbol_combo)
        input_row.addWidget(self._quantity_edit)
        input_row.addWidget(self._avg_price_edit)
        input_row.addWidget(add_button)
        input_row.addWidget(remove_button)
        input_row.addWidget(save_button)
        input_row.addStretch(1)
        input_row.addWidget(QLabel("보유종목은 watchlist 없이도 직접 입력 가능"))

        # --- 표 ---
        self._table = QTableWidget(0, COLUMN_COUNT)
        self._table.setHorizontalHeaderLabels(HEADERS)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(input_row)
        layout.addWidget(self._table, stretch=1)

        for holding in load_holdings():
            self._append_row(holding)

    # ------------------------------------------------------------------
    # 입력/삭제/저장
    # ------------------------------------------------------------------

    def _populate_symbols(self) -> None:
        seen: set[str] = set()
        for symbols in self._watchlist.values():
            for symbol in symbols:
                if symbol not in seen:
                    seen.add(symbol)
                    self._symbol_combo.addItem(symbol)

    def _on_add(self) -> None:
        raw_symbol = self._symbol_combo.currentText().strip()
        quantity_text = self._quantity_edit.text().strip().replace(",", "")
        avg_text = self._avg_price_edit.text().strip().replace(",", "")
        try:
            symbol = self._resolve_symbol(raw_symbol)
            quantity = float(quantity_text)
            avg_price = float(avg_text)
        except (ValueError, SymbolError) as exc:
            QMessageBox.warning(self, "입력 오류", f"입력을 확인해 주세요: {exc}")
            return
        if quantity <= 0 or avg_price < 0:
            QMessageBox.warning(self, "입력 오류", "수량은 0 초과, 단가는 0 이상이어야 합니다.")
            return
        self._append_row(Holding(symbol=symbol, quantity=quantity, avg_price=avg_price))
        self.symbol_submitted.emit(symbol)
        self._quantity_edit.clear()
        self._avg_price_edit.clear()
        self._save()

    def _resolve_symbol(self, raw: str) -> str:
        """사용자 입력을 표준 심볼으로 변환한다 (감시 목록 우선, 없으면 접미사 추정)."""
        text = raw.strip().upper().replace(" ", "")
        for exchange, symbols in self._watchlist.items():
            for listed in symbols:
                if listed.replace("/", "") == text.replace("/", "").replace("-", ""):
                    return normalize_symbol(exchange, text)
        is_binance = text.endswith("USDT") or ("/" in text and not text.endswith("KRW"))
        exchange = "binance" if is_binance else "upbit"
        return normalize_symbol(exchange, text)

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        self._save()

    def _save(self) -> None:
        save_holdings(self._read_holdings())

    def _append_row(self, holding: Holding) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = (
            holding.symbol,
            f"{holding.quantity:g}",
            format_price(holding.avg_price),
            "—",
            "—",
            "—",
            "—",
        )
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            if col > 0:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                )
            self._table.setItem(row, col, item)

    def _read_holdings(self) -> list[Holding]:
        holdings: list[Holding] = []
        for row in range(self._table.rowCount()):
            try:
                symbol = self._table.item(row, 0).text()
                quantity = float(self._table.item(row, 1).text().replace(",", ""))
                avg_price = float(self._table.item(row, 2).text().replace(",", ""))
            except (AttributeError, ValueError):
                logger.warning("%d행 파싱 실패 — 건너뜀", row)
                continue
            holdings.append(Holding(symbol=symbol, quantity=quantity, avg_price=avg_price))
        return holdings

    # ------------------------------------------------------------------
    # 평가 갱신
    # ------------------------------------------------------------------

    def set_watchlist(self, watchlist: Watchlist) -> None:
        self._watchlist = watchlist
        self._symbol_combo.clear()
        self._populate_symbols()

    def on_ticker(self, ticker: Ticker) -> None:
        """티커 수신 시 가격 캐시만 갱신하고 표는 배치로 다시 그린다."""
        self._prices[ticker.symbol] = ticker

    def refresh_values(self) -> None:
        """캐시된 현재가로 평가금액/손익 열을 갱신한다."""
        for row in range(self._table.rowCount()):
            symbol_item = self._table.item(row, 0)
            if symbol_item is None:
                continue
            symbol = symbol_item.text()
            ticker = self._prices.get(symbol)
            if ticker is None:
                continue
            try:
                quantity = float(self._table.item(row, 1).text().replace(",", ""))
                avg_price = float(self._table.item(row, 2).text().replace(",", ""))
            except (AttributeError, ValueError, TypeError):
                continue
            result = value_of(
                Holding(symbol=symbol, quantity=quantity, avg_price=avg_price), ticker.price
            )
            pnl_color = "#ef5350" if result.pnl >= 0 else "#2979ff"
            cells = (
                format_price(ticker.price),
                format_price(result.value),
                format_price(result.pnl),
                format_change(result.pnl_rate),
            )
            for offset, text in enumerate(cells, start=3):
                item = self._table.item(row, offset)
                if item is None:
                    item = QTableWidgetItem(text)
                    self._table.setItem(row, offset, item)
                else:
                    item.setText(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setForeground(QColor(pnl_color))
