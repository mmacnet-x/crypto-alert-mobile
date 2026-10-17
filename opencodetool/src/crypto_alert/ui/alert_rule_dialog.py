"""알림 규칙 추가/수정 다이얼로그 (조건 레지스트리 기반 자동 생성)."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.alerts import CONDITIONS, AlertRule, ParamDef, new_rule
from crypto_alert.watchlist_types import Watchlist

__all__ = ["AlertRuleDialog"]

#: 시간봉 선택지 (차트와 동일한 5주기)
DIALOG_INTERVALS: tuple[tuple[str, str], ...] = (
    ("15분", "15m"),
    ("4시간", "4h"),
    ("1일", "1d"),
    ("1주", "1w"),
    ("1월", "1M"),
)

#: 거래소 선택지 (차트와 동일한 표기)
DIALOG_EXCHANGES: tuple[tuple[str, str], ...] = (
    ("업비트", "upbit"),
    ("바이낸스", "binance"),
    ("OKX", "okx"),
)


class AlertRuleDialog(QDialog):
    """규칙 하나를 입력받는다. 파라미터 칸은 조건에 따라 자동 생성된다."""

    def __init__(
        self,
        watchlist: Watchlist,
        rule: AlertRule | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("알림 조건 수정" if rule else "알림 조건 추가")
        self._watchlist = watchlist
        self._editing_id = rule.id if rule else None
        self._result: AlertRule | None = None

        self._exchange_combo = QComboBox()
        for label, value in DIALOG_EXCHANGES:
            self._exchange_combo.addItem(label, value)

        self._symbol_combo = QComboBox()
        self._symbol_combo.setMinimumWidth(160)

        self._interval_combo = QComboBox()
        for label, value in DIALOG_INTERVALS:
            self._interval_combo.addItem(label, value)

        self._condition_combo = QComboBox()
        self._condition_combo.setMinimumWidth(220)
        for key, spec in CONDITIONS.items():
            self._condition_combo.addItem(spec.label, key)
        if rule is not None:
            needs_price = rule.condition in ("price_above", "price_below")
            self._interval_combo.setToolTip(
                "가격 조건은 봉과 무관하게 실시간가로 판단한다"
                if needs_price
                else "이 봉의 캔들로 지표를 계산한다"
            )

        self._params_form = QFormLayout()
        self._params_box = QWidget()
        self._params_box.setLayout(self._params_form)
        self._param_widgets: dict[str, QLineEdit | QSpinBox | QDoubleSpinBox] = {}

        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(0, 86_400)
        self._cooldown_spin.setValue(rule.cooldown_sec if rule else 600)
        self._cooldown_spin.setSuffix("초")
        self._cooldown_spin.setToolTip("발동 후 같은 규칙이 다시 울리기까지 최소 간격")

        self._enabled_check = QCheckBox("사용함")
        self._enabled_check.setChecked(rule.enabled if rule else True)

        form = QFormLayout()
        form.addRow("거래소:", self._exchange_combo)
        form.addRow("종목:", self._symbol_combo)
        form.addRow("주기:", self._interval_combo)
        form.addRow("조건:", self._condition_combo)

        params_title = QLabel("조건 값:")
        hint = QLabel("가격 조건은 실시간가로, 지표 조건은 해당 봉의 캔들로 판단한다.")
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(params_title)
        layout.addWidget(self._params_box)
        layout.addWidget(hint)
        cooldown_row = QHBoxLayout()
        cooldown_row.addWidget(QLabel("재알림 간격:"))
        cooldown_row.addWidget(self._cooldown_spin)
        cooldown_row.addStretch(1)
        cooldown_row.addWidget(self._enabled_check)
        layout.addLayout(cooldown_row)
        layout.addWidget(buttons)

        self._exchange_combo.currentIndexChanged.connect(self._populate_symbols)
        self._condition_combo.currentIndexChanged.connect(
            lambda: self._rebuild_params(rule.params if rule else None)
        )

        # 초기값 채우기
        if rule is not None:
            self._select_combo(self._exchange_combo, rule.exchange)
        self._populate_symbols()
        if rule is not None:
            self._select_combo(self._symbol_combo, rule.symbol)
            self._select_combo(self._interval_combo, rule.interval)
            self._select_combo(self._condition_combo, rule.condition)
        self._rebuild_params(rule.params if rule else None)

    @staticmethod
    def _select_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _populate_symbols(self) -> None:
        exchange = str(self._exchange_combo.currentData())
        self._symbol_combo.blockSignals(True)
        self._symbol_combo.clear()
        self._symbol_combo.addItems(self._watchlist.get(exchange, []))
        self._symbol_combo.blockSignals(False)

    def _rebuild_params(self, prefill: dict[str, float | int] | None) -> None:
        while self._params_form.rowCount():
            self._params_form.removeRow(0)
        self._param_widgets = {}
        key = str(self._condition_combo.currentData())
        spec = CONDITIONS.get(key)
        if spec is None:
            return
        for param in spec.params:
            widget = self._make_param_widget(param, prefill)
            self._params_form.addRow(f"{param.label}:", widget)
            self._param_widgets[param.key] = widget

    @staticmethod
    def _make_param_widget(
        param: ParamDef, prefill: dict[str, float | int] | None
    ) -> QLineEdit | QSpinBox | QDoubleSpinBox:
        raw = (prefill or {}).get(param.key, param.default)
        if param.kind == "price":
            edit = QLineEdit()
            edit.setPlaceholderText("예: 115000000")
            edit.setText(str(raw))
            return edit
        if param.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(param.minimum), int(param.maximum))
            try:
                spin.setValue(int(raw))
            except (TypeError, ValueError):
                spin.setValue(int(param.default))
            return spin
        spin_float = QDoubleSpinBox()
        spin_float.setRange(float(param.minimum), float(param.maximum))
        spin_float.setDecimals(2)
        try:
            spin_float.setValue(float(raw))
        except (TypeError, ValueError):
            spin_float.setValue(float(param.default))
        return spin_float

    def _collect_params(self) -> dict[str, float | int]:
        key = str(self._condition_combo.currentData())
        spec = CONDITIONS.get(key)
        if spec is None:
            raise ValueError("조건을 선택해 주세요.")
        params: dict[str, float | int] = {}
        for param in spec.params:
            widget = self._param_widgets.get(param.key)
            if widget is None:
                raise ValueError(f"[{param.label}] 입력칸이 없습니다.")
            if isinstance(widget, QLineEdit):
                text = widget.text().strip().replace(",", "")
                if not text:
                    raise ValueError(f"[{param.label}] 값을 입력해 주세요.")
                try:
                    params[param.key] = float(text)
                except ValueError as exc:
                    raise ValueError(f"[{param.label}] 숫자가 아닙니다: {text!r}") from exc
            elif isinstance(widget, QSpinBox):
                params[param.key] = widget.value()
            else:
                params[param.key] = widget.value()
        return params

    def build_rule(self) -> AlertRule:
        """입력값으로 규칙을 만든다 (검증 실패 시 ValueError)."""
        from crypto_alert.alerts import RuleError

        exchange = str(self._exchange_combo.currentData())
        symbol = self._symbol_combo.currentText().strip()
        if not symbol:
            raise ValueError("종목을 선택해 주세요 (감시 목록이 비어 있을 수 있습니다).")
        interval = str(self._interval_combo.currentData())
        condition = str(self._condition_combo.currentData())
        params = self._collect_params()
        try:
            base = new_rule(
                exchange,
                symbol,
                interval,
                condition,
                params,
                enabled=self._enabled_check.isChecked(),
                cooldown_sec=self._cooldown_spin.value(),
            )
        except RuleError as exc:
            raise ValueError(str(exc)) from exc
        if self._editing_id is not None:
            base.id = self._editing_id
        return base

    def accept(self) -> None:
        """확인 버튼: 검증 통과 시에만 닫는다."""
        try:
            self._result = self.build_rule()
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return
        super().accept()

    @property
    def result(self) -> AlertRule | None:
        """accept()로 닫혔을 때의 규칙 (취소 시 None)."""
        return self._result
