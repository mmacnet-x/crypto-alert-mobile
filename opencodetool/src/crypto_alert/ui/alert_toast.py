"""발동 알림 토스트 팝업 (우하단, 클릭/시간 경과 시 닫힘)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

__all__ = ["TOAST_MS", "Toast"]

#: 팝업 표시 시간 (ms)
TOAST_MS = 6000


class Toast(QWidget):
    """작업 흐름을 막지 않는 작은 알림 창 (포커스를 뺏지 않는다)."""

    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(340)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setStyleSheet("font-size: 12px; color: #d1d4dc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        self.setStyleSheet(
            "Toast { background-color: #1e2530; border: 1px solid #42a5f5; border-radius: 6px; }"
        )
        QTimer.singleShot(TOAST_MS, self.close)

    def show_anchored(self) -> None:
        """주 화면 우하단에 붙여서 표시한다."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.adjustSize()
            self.move(
                available.right() - self.width() - 16,
                available.bottom() - self.height() - 16,
            )
        self.show()

    def mousePressEvent(self, event) -> None:
        """클릭하면 바로 닫는다."""
        self.close()
        super().mousePressEvent(event)
