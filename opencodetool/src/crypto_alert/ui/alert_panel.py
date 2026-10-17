"""알림 패널: 조건 규칙 목록(5단계) + 발동 이력 표."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.alerts import AlertRule, NotifySettings
from crypto_alert.watchlist_types import Watchlist

__all__ = ["AlertPanel"]

MAX_ROWS = 200
RULE_HEADERS = ("상태", "종목", "주기", "조건", "상세")
INTERVAL_LABELS = {"15m": "15분", "4h": "4시간", "1d": "1일", "1w": "1주", "1M": "1월"}


class AlertPanel(QWidget):
    """알림 조건 규칙 + 발동 이력을 표시하는 패널."""

    # 규칙이 바뀌면 MainWindow가 저장·엔진 반영을 한다
    rules_changed = pyqtSignal(list)
    # 발송 설정이 바뀌면 MainWindow가 저장·발송기 반영을 한다
    notify_settings_changed = pyqtSignal(object)
    # 다이얼로그의 테스트 버튼 → MainWindow가 Notifier로 발송한다
    notify_test_requested = pyqtSignal(object)

    def __init__(self, watchlist: Watchlist | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._watchlist: Watchlist = watchlist or {}
        self._rules: list[AlertRule] = []
        self._notify_settings = NotifySettings()

        # --- 규칙 목록 ---
        rules_title = QLabel("알림 조건")
        add_button = QPushButton("추가")
        edit_button = QPushButton("수정")
        delete_button = QPushButton("삭제")
        toggle_button = QPushButton("켜기/끄기")
        add_button.clicked.connect(self._on_add)
        edit_button.clicked.connect(self._on_edit)
        delete_button.clicked.connect(self._on_delete)
        toggle_button.clicked.connect(self._on_toggle)

        rules_header = QHBoxLayout()
        rules_header.addWidget(rules_title)
        rules_header.addStretch(1)
        rules_header.addWidget(add_button)
        rules_header.addWidget(edit_button)
        rules_header.addWidget(delete_button)
        rules_header.addWidget(toggle_button)

        self._rules_table = QTableWidget(0, len(RULE_HEADERS))
        self._rules_table.setHorizontalHeaderLabels(RULE_HEADERS)
        rules_head = self._rules_table.horizontalHeader()
        for col in range(len(RULE_HEADERS) - 1):
            rules_head.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        rules_head.setSectionResizeMode(len(RULE_HEADERS) - 1, QHeaderView.ResizeMode.Stretch)
        self._rules_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._rules_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._rules_table.verticalHeader().setVisible(False)

        # --- 발동 이력 ---
        history_title = QLabel("알림 이력")
        settings_button = QPushButton("발송 설정")
        settings_button.clicked.connect(self._on_notify_settings)
        history_header = QHBoxLayout()
        history_header.addWidget(history_title)
        history_header.addStretch(1)
        history_header.addWidget(settings_button)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["시각", "종목", "메시지"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(rules_header)
        layout.addWidget(self._rules_table, stretch=1)
        layout.addLayout(history_header)
        layout.addWidget(self._table, stretch=1)

    # ------------------------------------------------------------------
    # 규칙 목록
    # ------------------------------------------------------------------

    @property
    def rules(self) -> list[AlertRule]:
        """현재 규칙 목록 (복사본)."""
        return list(self._rules)

    def set_rules(self, rules: list[AlertRule]) -> None:
        """규칙 목록을 통째로 교체한다 (파일 로드 시, 시그널 없음)."""
        self._rules = list(rules)
        self._refresh_rules()

    def set_watchlist(self, watchlist: Watchlist) -> None:
        """감시 목록 변경 후 다이얼로그용 목록을 새로고침한다."""
        self._watchlist = watchlist

    def set_notify_settings(self, settings: NotifySettings) -> None:
        """발송 설정을 교체한다 (파일 로드 시, 시그널 없음)."""
        self._notify_settings = settings

    def _on_notify_settings(self) -> None:
        from crypto_alert.ui.notify_dialog import NotifySettingsDialog

        dialog = NotifySettingsDialog(self._notify_settings, parent=self)
        dialog.test_requested.connect(self.notify_test_requested.emit)
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.result is not None:
            self._notify_settings = dialog.result
            self.notify_settings_changed.emit(dialog.result)

    def _selected_index(self) -> int:
        row = self._rules_table.currentRow()
        return row if 0 <= row < len(self._rules) else -1

    def _refresh_rules(self) -> None:
        self._rules_table.setRowCount(len(self._rules))
        for row, rule in enumerate(self._rules):
            values = (
                "켜짐" if rule.enabled else "꺼짐",
                rule.symbol,
                INTERVAL_LABELS.get(rule.interval, rule.interval),
                rule.condition_label,
                rule.short(),
            )
            for col, text in enumerate(values):
                self._rules_table.setItem(row, col, QTableWidgetItem(text))

    def _emit_changed(self) -> None:
        self._refresh_rules()
        self.rules_changed.emit(list(self._rules))

    def _on_add(self) -> None:
        from crypto_alert.ui.alert_rule_dialog import AlertRuleDialog

        dialog = AlertRuleDialog(self._watchlist, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.result is not None:
            self._rules.append(dialog.result)
            self._emit_changed()

    def _on_edit(self) -> None:
        from crypto_alert.ui.alert_rule_dialog import AlertRuleDialog

        index = self._selected_index()
        if index < 0:
            QMessageBox.information(self, "선택 필요", "수정할 규칙을 선택해 주세요.")
            return
        dialog = AlertRuleDialog(self._watchlist, self._rules[index], parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.result is not None:
            self._rules[index] = dialog.result
            self._emit_changed()

    def _on_delete(self) -> None:
        index = self._selected_index()
        if index < 0:
            return
        del self._rules[index]
        self._emit_changed()

    def _on_toggle(self) -> None:
        index = self._selected_index()
        if index < 0:
            return
        rule = self._rules[index]
        rule.enabled = not rule.enabled
        self._emit_changed()

    # ------------------------------------------------------------------
    # 발동 이력
    # ------------------------------------------------------------------

    def add_alert(self, when: datetime, symbol: str, message: str) -> None:
        """발동한 알림 한 건을 맨 위에 추가한다."""
        self._table.insertRow(0)
        clock = when.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self._table.setItem(0, 0, QTableWidgetItem(clock))
        self._table.setItem(0, 1, QTableWidgetItem(symbol))
        self._table.setItem(0, 2, QTableWidgetItem(message))
        while self._table.rowCount() > MAX_ROWS:
            self._table.removeRow(self._table.rowCount() - 1)
