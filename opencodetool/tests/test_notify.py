"""6단계 테스트: 발송 설정 저장 + 발송기 채널 + 설정 UI + 메인윈도우 연동."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_alert.alerts import (
    AlertEvent,
    Notifier,
    NotifySettings,
    NotifySettingsError,
    format_telegram_text,
    load_notify_settings,
    save_notify_settings,
)

BASE = datetime(2026, 10, 8, tzinfo=UTC)


def _event() -> AlertEvent:
    return AlertEvent(
        rule_id="r1",
        exchange="upbit",
        symbol="BTC/KRW",
        interval="15m",
        condition="price_above",
        message="BTC/KRW 가격 ≥ 목표: 현재가 115,000,000.00 (목표 100,000,000.00)",
        price=115_000_000.0,
        time=BASE,
    )


def test_settings_defaults_and_ready() -> None:
    settings = NotifySettings()
    assert (settings.popup_enabled, settings.sound_enabled) == (True, True)
    assert settings.telegram_enabled is False
    assert settings.telegram_ready is False
    ready = NotifySettings(telegram_enabled=True, bot_token="tok", chat_id="123")
    assert ready.telegram_ready is True
    assert NotifySettings(telegram_enabled=True, bot_token="tok").telegram_ready is False


def test_settings_roundtrip(tmp_path) -> None:
    path = tmp_path / "notify_settings.json"
    settings = NotifySettings(
        popup_enabled=False,
        sound_enabled=True,
        telegram_enabled=True,
        bot_token="tok",
        chat_id="123",
    )
    save_notify_settings(settings, path)
    assert load_notify_settings(path).to_dict() == settings.to_dict()
    assert load_notify_settings(tmp_path / "missing.json").to_dict() == NotifySettings().to_dict()


def test_settings_corrupt(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("깨진 내용 {{{", encoding="utf-8")
    with pytest.raises(NotifySettingsError):
        load_notify_settings(bad)
    wrong = tmp_path / "wrong.json"
    wrong.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(NotifySettingsError):
        load_notify_settings(wrong)


def test_telegram_text_has_no_secrets() -> None:
    text = format_telegram_text(_event())
    assert "BTC/KRW" in text and "115,000,000.00" in text
    assert "tok" not in text.replace("토큰", "")


def test_dispatch_channels(qapp) -> None:
    calls: list[tuple[str, str]] = []
    failures: list[str] = []
    settings = NotifySettings(
        popup_enabled=True,
        sound_enabled=True,
        telegram_enabled=True,
        bot_token="tok",
        chat_id="123",
    )
    notifier = Notifier(settings)
    notifier.set_test_hook(lambda event, channel, text: calls.append((channel, text)))
    notifier.delivery_failed.connect(failures.append)
    used = notifier.dispatch(_event())
    assert used == ["popup", "sound", "telegram"]
    assert [channel for channel, _text in calls] == ["popup", "sound", "telegram"]
    assert not failures


def test_dispatch_respects_switches(qapp) -> None:
    calls: list[str] = []
    notifier = Notifier(NotifySettings(popup_enabled=True, sound_enabled=False))
    notifier.set_test_hook(lambda event, channel, text: calls.append(channel))
    assert notifier.dispatch(_event()) == ["popup"]
    assert calls == ["popup"]


def test_dispatch_telegram_without_creds(qapp) -> None:
    calls: list[str] = []
    failures: list[str] = []
    notifier = Notifier(NotifySettings(telegram_enabled=True))
    notifier.set_test_hook(lambda event, channel, text: calls.append(channel))
    notifier.delivery_failed.connect(failures.append)
    used = notifier.dispatch(_event())
    assert "telegram" not in used
    assert "telegram" not in calls
    assert len(failures) == 1 and "토큰" in failures[0]


def test_send_test_requires_creds(qapp) -> None:
    results: list[tuple[bool, str]] = []
    notifier = Notifier(NotifySettings())
    notifier.test_finished.connect(lambda ok, detail: results.append((ok, detail)))
    notifier.send_test()
    assert len(results) == 1 and results[0][0] is False


def test_send_test_with_hook(qapp) -> None:
    calls: list[tuple[str, str]] = []
    results: list[tuple[bool, str]] = []
    settings = NotifySettings(telegram_enabled=True, bot_token="tok", chat_id="123")
    notifier = Notifier(settings)
    notifier.set_test_hook(lambda event, channel, text: calls.append((channel, text)))
    notifier.test_finished.connect(lambda ok, detail: results.append((ok, detail)))
    notifier.send_test()
    assert [channel for channel, _text in calls] == ["telegram"]
    assert "테스트" in calls[0][1]
    assert len(results) == 1 and results[0][0] is True


def test_notify_dialog_build(qapp) -> None:
    from crypto_alert.ui.notify_dialog import NotifySettingsDialog

    dialog = NotifySettingsDialog(NotifySettings())
    assert dialog.build_settings().to_dict() == NotifySettings().to_dict()

    # 텔레그램을 켜면 토큰·챗ID가 필수
    dialog._telegram_check.setChecked(True)
    with pytest.raises(ValueError):
        dialog.build_settings()
    dialog._token_edit.setText("tok")
    dialog._chat_edit.setText("123")
    settings = dialog.build_settings()
    assert settings.telegram_enabled and settings.telegram_ready
    dialog.close()


def test_main_window_dispatch(qapp) -> None:
    from crypto_alert.ui.main_window import MainWindow

    window = MainWindow(start_engine=False)
    calls: list[str] = []
    window._notifier.set_test_hook(lambda event, channel, text: calls.append(channel))
    window._dispatch_alert(_event())
    assert window._alerts._table.rowCount() == 1
    assert calls == ["popup", "sound"]  # 기본값: 텔레그램 꺼짐
    window.close()


def test_notifier_settings_property_and_update(qapp) -> None:
    notifier = Notifier()
    assert notifier.settings.to_dict() == NotifySettings().to_dict()
    custom = NotifySettings(popup_enabled=False, sound_enabled=False)
    notifier.update_settings(custom)
    assert notifier.settings is custom
    assert notifier.dispatch(_event()) == []


def test_safe_deliver_swallows_hook_error(qapp, caplog) -> None:
    import logging

    def bad_hook(event, channel, text) -> None:
        raise RuntimeError("갈고리 고장")

    notifier = Notifier(NotifySettings(sound_enabled=False, telegram_enabled=False))
    notifier.set_test_hook(bad_hook)
    with caplog.at_level(logging.ERROR):
        assert notifier.dispatch(_event()) == ["popup"]  # 예외 없이 통과


def test_real_popup_and_sound(qapp, monkeypatch) -> None:
    """갈고리 없이 실제 채널 호출 (offscreen, 소리 대체)."""
    import winsound

    beeps: list[tuple[int, int]] = []
    monkeypatch.setattr(winsound, "Beep", lambda f, d: beeps.append((f, d)))
    notifier = Notifier(NotifySettings(sound_enabled=True, telegram_enabled=False))
    notifier._sound(_event())
    assert beeps == [(880, 300)]
    notifier._popup(_event())  # offscreen 토스트 표시 (예외 없어야 함)


def test_safe_deliver_without_hook(qapp) -> None:
    """갈고리 없이도 채널 함수가 직접 호출된다."""
    seen: list[str] = []
    notifier = Notifier(NotifySettings(sound_enabled=False, telegram_enabled=False))
    notifier._safe_deliver("popup", _event(), lambda e: seen.append(e.symbol))
    assert seen == ["BTC/KRW"]


def test_sound_fallback_without_winsound(qapp, monkeypatch) -> None:
    import winsound

    from PyQt6.QtWidgets import QApplication

    rung: list[bool] = []
    monkeypatch.setattr(winsound, "Beep", lambda f, d: (_ for _ in ()).throw(OSError("no")))
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: rung.append(True)))
    Notifier(NotifySettings())._sound(_event())
    assert rung == [True]


def test_post_telegram_success_and_failure(qapp, monkeypatch) -> None:
    import requests

    from crypto_alert.alerts import notify as notify_mod

    calls: list[dict] = []

    class _FakeResp:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        notify_mod.requests, "post", lambda url, json, timeout: calls.append(json) or _FakeResp()
    )
    settings = NotifySettings(telegram_enabled=True, bot_token="tok", chat_id="123")
    notifier = Notifier(settings)
    done: list[tuple[bool, str]] = []
    notifier.test_finished.connect(lambda ok, detail: done.append((ok, detail)))
    notifier._post_telegram(settings, "hi", True)
    assert calls == [{"chat_id": "123", "text": "hi"}]
    assert done == [(True, "테스트 메시지를 텔레그램으로 보냈습니다.")]

    def _boom(url, json, timeout):
        raise requests.ConnectionError("끊김")

    monkeypatch.setattr(notify_mod.requests, "post", _boom)
    failed: list[str] = []
    notifier.delivery_failed.connect(failed.append)
    notifier._post_telegram(settings, "hi", True)
    assert done[-1][0] is False and "끊김" in done[-1][1]
    notifier._post_telegram(settings, "hi", False)
    assert len(failed) == 1 and "끊김" in failed[0]
    assert "tok" not in failed[0]  # 토큰은 오류 메시지에 노출 금지


def test_send_paths_use_background_thread(qapp, monkeypatch) -> None:
    """스레드 생성 경로는 동기 실행 스텁으로 검증한다."""
    import threading

    from crypto_alert.alerts import notify as notify_mod

    started: list[str] = []

    class _SyncThread:
        def __init__(self, target=None, args=(), kwargs=None, **kw) -> None:
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self) -> None:
            started.append("go")
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(threading, "Thread", _SyncThread)
    posted: list[dict] = []

    class _FakeResp:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        notify_mod.requests, "post", lambda url, json, timeout: posted.append(json) or _FakeResp()
    )
    settings = NotifySettings(telegram_enabled=True, bot_token="tok", chat_id="123")
    notifier = Notifier(settings)
    done: list[tuple[bool, str]] = []
    notifier.test_finished.connect(lambda ok, detail: done.append((ok, detail)))
    notifier.send_test()
    assert started == ["go"] and done and done[0][0] is True
    notifier._send_telegram(_event(), is_test=False)
    assert started == ["go", "go"] and len(posted) == 2


def test_toast_show_and_click_close(qapp) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from crypto_alert.ui.alert_toast import Toast

    toast = Toast("BTC/KRW", "가격 ≥ 목표")
    toast.show_anchored()
    assert toast.isVisible()
    QTest.mouseClick(toast, Qt.MouseButton.LeftButton)
    assert not toast.isVisible()


def test_notify_dialog_test_and_accept(qapp, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from crypto_alert.ui.notify_dialog import NotifySettingsDialog

    warnings: list[str] = []
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[1]))

    dialog = NotifySettingsDialog(NotifySettings())
    assert dialog.result is None
    requested: list[object] = []
    dialog.test_requested.connect(requested.append)

    # 입력 오류 → 경고만
    dialog._telegram_check.setChecked(True)
    dialog._on_test()
    assert warnings and not requested

    # 텔레그램 꺼짐 → 안내만
    dialog._telegram_check.setChecked(False)
    dialog._on_test()
    assert infos and not requested

    # 정상 → 요청 신호
    dialog._telegram_check.setChecked(True)
    dialog._token_edit.setText("tok")
    dialog._chat_edit.setText("123")
    dialog._on_test()
    assert len(requested) == 1

    # accept 실패 → 닫히지 않음
    dialog._token_edit.setText("")
    dialog._on_test()  # requested 그대로
    assert len(requested) == 1
    dialog.accept()
    assert dialog.result is None

    dialog._token_edit.setText("tok")
    dialog.accept()
    assert dialog.result is not None and dialog.result.telegram_ready
    dialog.close()


def test_notify_settings_save_error(tmp_path) -> None:
    from pathlib import Path

    from crypto_alert.alerts import NotifySettingsError, save_notify_settings

    def _boom(self, *args, **kwargs):
        raise OSError("쓰기 금지")

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(Path, "write_text", _boom)
        with pytest.raises(NotifySettingsError):
            save_notify_settings(NotifySettings(), tmp_path / "s.json")


def test_store_save_error(tmp_path) -> None:
    from pathlib import Path

    from crypto_alert.alerts import RulesError, save_rules

    def _boom(self, *args, **kwargs):
        raise OSError("쓰기 금지")

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(Path, "write_text", _boom)
        with pytest.raises(RulesError):
            save_rules([], tmp_path / "r.json")
