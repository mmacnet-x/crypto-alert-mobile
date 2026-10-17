"""알림 발송 설정 저장/불러오기 (notify_settings.json).

봇 토큰은 이 파일에 평문으로 저장된다 (PC 본인만 보는 로컬 파일 전제).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_alert.paths import app_data_dir

__all__ = [
    "NotifySettings",
    "NotifySettingsError",
    "load_notify_settings",
    "notify_settings_path",
    "save_notify_settings",
]


class NotifySettingsError(ValueError):
    """설정 파일이 깨졌을 때 발생."""


@dataclass(slots=True)
class NotifySettings:
    """발송 채널 on/off + 텔레그램 접속 정보."""

    popup_enabled: bool = True
    sound_enabled: bool = True
    telegram_enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""

    @property
    def telegram_ready(self) -> bool:
        """텔레그램 발송 가능 여부 (토큰·챗ID 모두 입력됨)."""
        return bool(self.bot_token.strip() and self.chat_id.strip())

    def to_dict(self) -> dict[str, Any]:
        """JSON 저장용 딕셔너리."""
        return {
            "popup_enabled": self.popup_enabled,
            "sound_enabled": self.sound_enabled,
            "telegram_enabled": self.telegram_enabled,
            "bot_token": self.bot_token,
            "chat_id": self.chat_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotifySettings:
        """딕셔너리에서 설정을 복원한다 (없는 키는 기본값)."""
        if not isinstance(data, dict):
            raise NotifySettingsError(f"설정 형식이 잘못되었습니다: {data!r}")
        return cls(
            popup_enabled=bool(data.get("popup_enabled", True)),
            sound_enabled=bool(data.get("sound_enabled", True)),
            telegram_enabled=bool(data.get("telegram_enabled", False)),
            bot_token=str(data.get("bot_token", "")),
            chat_id=str(data.get("chat_id", "")),
        )


def notify_settings_path() -> Path:
    """설정 JSON 파일 경로 (alert_rules.json과 같은 폴더)."""
    return app_data_dir() / "notify_settings.json"


def load_notify_settings(path: Path | None = None) -> NotifySettings:
    """발송 설정을 읽는다. 파일이 없으면 기본값을 반환한다."""
    target = path or notify_settings_path()
    if not target.exists():
        return NotifySettings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotifySettingsError(f"설정 파일을 읽을 수 없습니다: {target} ({exc})") from exc
    try:
        return NotifySettings.from_dict(raw)
    except NotifySettingsError as exc:
        raise NotifySettingsError(f"설정 파일 오류: {target} ({exc})") from exc


def save_notify_settings(settings: NotifySettings, path: Path | None = None) -> None:
    """발송 설정을 파일에 저장한다."""
    target = path or notify_settings_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise NotifySettingsError(f"설정 저장 실패: {target} ({exc})") from exc
