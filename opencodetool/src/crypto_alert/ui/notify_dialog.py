"""발송 설정 다이얼로그 (팝업/사운드/텔레그램 + 테스트 발송)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from crypto_alert.alerts import NotifySettings

__all__ = ["NotifySettingsDialog"]


class NotifySettingsDialog(QDialog):
    """발송 채널 on/off와 텔레그램 접속 정보를 입력받는다."""

    # 테스트 버튼 클릭 시 현재 입력값으로 발송 요청 (MainWindow가 Notifier에 전달)
    test_requested = pyqtSignal(object)

    def __init__(
        self,
        settings: NotifySettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("알림 발송 설정")
        self._result: NotifySettings | None = None

        self._popup_check = QCheckBox("화면 팝업")
        self._popup_check.setChecked(settings.popup_enabled)
        self._sound_check = QCheckBox("사운드")
        self._sound_check.setChecked(settings.sound_enabled)
        self._telegram_check = QCheckBox("텔레그램 발송")
        self._telegram_check.setChecked(settings.telegram_enabled)

        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText("BotFather 발급 토큰")
        self._token_edit.setText(settings.bot_token)
        self._token_edit.setMinimumWidth(280)

        self._chat_edit = QLineEdit()
        self._chat_edit.setPlaceholderText("getUpdates로 확인한 chat.id")
        self._chat_edit.setText(settings.chat_id)

        test_button = QPushButton("테스트 발송")
        test_button.clicked.connect(self._on_test)
        hint = QLabel("텔레그램을 켜려면 봇 토큰·챗ID 입력 후 테스트 발송으로 확인하세요.")
        hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("채널:", self._channel_row())
        form.addRow("봇 토큰:", self._token_edit)
        form.addRow("챗 ID:", self._chat_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(test_button)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def _channel_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._popup_check)
        layout.addWidget(self._sound_check)
        layout.addWidget(self._telegram_check)
        layout.addStretch(1)
        return row

    def build_settings(self) -> NotifySettings:
        """입력값으로 설정을 만든다 (검증 실패 시 ValueError)."""
        telegram_on = self._telegram_check.isChecked()
        token = self._token_edit.text().strip()
        chat_id = self._chat_edit.text().strip()
        if telegram_on and (not token or not chat_id):
            raise ValueError("텔레그램을 켜려면 봇 토큰과 챗ID를 모두 입력해 주세요.")
        return NotifySettings(
            popup_enabled=self._popup_check.isChecked(),
            sound_enabled=self._sound_check.isChecked(),
            telegram_enabled=telegram_on,
            bot_token=token,
            chat_id=chat_id,
        )

    def _on_test(self) -> None:
        try:
            settings = self.build_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return
        if not settings.telegram_ready:
            QMessageBox.information(self, "테스트 불가", "봇 토큰과 챗ID를 입력해 주세요.")
            return
        self.test_requested.emit(settings)

    def accept(self) -> None:
        """확인 버튼: 검증 통과 시에만 닫는다."""
        try:
            self._result = self.build_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return
        super().accept()

    @property
    def result(self) -> NotifySettings | None:
        """accept()로 닫혔을 때의 설정 (취소 시 None)."""
        return self._result
