"""알림 발송기: 화면 팝업 + 사운드 + 텔레그램.

- GUI 스레드에서 :meth:`Notifier.dispatch` 한 줄로 호출한다
- 텔레그램 전송은 별도 스레드라 시세 처리가 멈추지 않는다
- 테스트에서는 :meth:`Notifier.set_test_hook` 으로 네트워크 없이 검증한다
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import requests
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from crypto_alert.alerts.engine import AlertEvent
from crypto_alert.alerts.notify_settings import NotifySettings

logger = logging.getLogger(__name__)

__all__ = ["Notifier", "format_telegram_text"]

TELEGRAM_TIMEOUT_SEC = 10

#: 테스트 갈고리: (이벤트, 채널, 본문). 설정 시 실제 발송 대신 호출된다.
#: 채널은 "popup" | "sound" | "telegram".
TestHook = Callable[[AlertEvent, str, str], None]


def format_telegram_text(event: AlertEvent) -> str:
    """텔레그램 전송용 한 줄 메시지 (토큰 등 비밀정보 미포함)."""
    when = event.time.astimezone().strftime("%m-%d %H:%M:%S")
    return f"[crypto-alert] {event.message} ({when})"


class Notifier(QObject):
    """발동 알림을 설정된 채널로 발송한다."""

    # 테스트 발송 결과 (성공 여부, 상세)
    test_finished = pyqtSignal(bool, str)
    # 실제 발동 건의 텔레그램 전송 실패 (상태표시줄용)
    delivery_failed = pyqtSignal(str)

    def __init__(
        self, settings: NotifySettings | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._settings = settings or NotifySettings()
        self._hook: TestHook | None = None

    @property
    def settings(self) -> NotifySettings:
        """현재 발송 설정 (복사본이 아니라 원본 참조 — 읽기 전용으로 쓸 것)."""
        return self._settings

    def update_settings(self, settings: NotifySettings) -> None:
        """발송 설정을 교체한다."""
        self._settings = settings

    def set_test_hook(self, hook: TestHook | None) -> None:
        """테스트 갈고리를 등록/해제한다."""
        self._hook = hook

    def dispatch(self, event: AlertEvent) -> list[str]:
        """발동 알림을 설정된 채널로 발송한다. 사용된 채널 목록을 반환한다."""
        used: list[str] = []
        if self._settings.popup_enabled:
            self._safe_deliver("popup", event, self._popup)
            used.append("popup")
        if self._settings.sound_enabled:
            self._safe_deliver("sound", event, self._sound)
            used.append("sound")
        if self._settings.telegram_enabled:
            if self._settings.telegram_ready:
                self._send_telegram(event, is_test=False)
                used.append("telegram")
            else:
                self.delivery_failed.emit("텔레그램 설정이 비어 있습니다 (토큰/챗ID 확인)")
        return used

    def send_test(self, settings: NotifySettings | None = None) -> None:
        """테스트 메시지를 텔레그램으로 발송한다 (결과는 test_finished)."""
        target = settings if settings is not None else self._settings
        if not target.telegram_ready:
            self.test_finished.emit(False, "봇 토큰과 챗ID를 입력해 주세요.")
            return
        event = AlertEvent(
            rule_id="test",
            exchange="",
            symbol="테스트",
            interval="",
            condition="test",
            message="테스트 알림입니다.",
            price=None,
            time=datetime.now(tz=UTC),
        )
        if self._hook is not None:
            self._hook(event, "telegram", format_telegram_text(event))
            self.test_finished.emit(True, "테스트 발송 완료 (갈고리)")
            return
        thread = threading.Thread(
            target=self._post_telegram,
            args=(target, format_telegram_text(event), True),
            name="telegram-test",
            daemon=True,
        )
        thread.start()

    # ------------------------------------------------------------------
    # 채널별 발송
    # ------------------------------------------------------------------

    def _safe_deliver(
        self, channel: str, event: AlertEvent, real: Callable[[AlertEvent], None]
    ) -> None:
        try:
            if self._hook is not None:
                self._hook(event, channel, event.message)
            else:
                real(event)
        except Exception:
            logger.exception("%s 발송 실패", channel)

    def _popup(self, event: AlertEvent) -> None:
        from crypto_alert.ui.alert_toast import Toast

        Toast(event.symbol, event.message).show_anchored()

    def _sound(self, _event: AlertEvent) -> None:
        try:
            import winsound

            winsound.Beep(880, 300)
        except Exception:  # noqa: BLE001 — winsound 부재/실패 시 기본 비프
            QApplication.beep()

    def _send_telegram(self, event: AlertEvent, *, is_test: bool) -> None:
        text = format_telegram_text(event)
        if self._hook is not None:
            self._hook(event, "telegram", text)
            return
        settings = self._settings
        thread = threading.Thread(
            target=self._post_telegram,
            args=(settings, text, is_test),
            name="telegram-send",
            daemon=True,
        )
        thread.start()

    def _post_telegram(self, settings: NotifySettings, text: str, is_test: bool) -> None:
        """별도 스레드에서 Bot API를 호출한다 (토큰은 로그에 남기지 않는다)."""
        url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={"chat_id": settings.chat_id, "text": text},
                timeout=TELEGRAM_TIMEOUT_SEC,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — 네트워크 오류는 신호로만 전달
            logger.warning("텔레그램 전송 실패: %s", exc)
            if is_test:
                self.test_finished.emit(False, f"전송 실패: {exc}")
            else:
                self.delivery_failed.emit(f"텔레그램 전송 실패: {exc}")
            return
        if is_test:
            self.test_finished.emit(True, "테스트 메시지를 텔레그램으로 보냈습니다.")
