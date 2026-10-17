"""시가총액 순위 패널 (자체 계산: 공급량 x 현재가)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.formatting import format_change, format_market_cap
from crypto_alert.marketcap import MarketRank

__all__ = ["MarketCapPanel"]


def _short_price(price_usd: float) -> str:
    """USD 가격을 짧게 표시한다 (좁은 표 폭 대응)."""
    if price_usd >= 100:
        text = f"{price_usd:,.2f}"
    elif price_usd >= 1:
        text = f"{price_usd:.4f}"
    elif price_usd >= 0.01:
        text = f"{price_usd:.6f}"
    else:
        text = f"{price_usd:.8f}".rstrip("0")
    return f"${text}"


class MarketCapPanel(QWidget):
    """감시 종목의 시가총액 순위표 (내림차순)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["#", "종목", "가격(USD)", "시가총액", "24h"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(0, 32)  # 순위 열 고정 폭
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)

        title = QLabel("시가총액 순위 (공급량 × 현재가 자체 계산)")
        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self._table, stretch=1)

    def update_ranks(self, ranks: list[MarketRank]) -> None:
        """순위 목록으로 표 전체를 갱신한다."""
        self._table.setRowCount(len(ranks))
        for row, rank in enumerate(ranks):
            rank_item = QTableWidgetItem(str(row + 1))
            rank_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            price_item = QTableWidgetItem(_short_price(rank.price_usd))
            cap_item = QTableWidgetItem(format_market_cap(rank.market_cap_usd))
            change_item = QTableWidgetItem(format_change(rank.change_rate))
            change_color = "#ef5350" if rank.change_rate >= 0 else "#2979ff"
            change_item.setForeground(QColor(change_color))
            self._table.setItem(row, 0, rank_item)
            self._table.setItem(row, 1, QTableWidgetItem(rank.symbol))
            self._table.setItem(row, 2, price_item)
            self._table.setItem(row, 3, cap_item)
            self._table.setItem(row, 4, change_item)
