"""7단계 테스트: exe 패키징 대응 경로 해결."""

from __future__ import annotations

import sys
from pathlib import Path

import crypto_alert.paths as paths_mod
from crypto_alert.paths import app_data_dir, is_frozen, resource_path


def test_not_frozen_uses_package_dir() -> None:
    assert is_frozen() is False
    package_dir = Path(paths_mod.__file__).resolve().parent
    assert app_data_dir() == package_dir
    assert resource_path("supplies.json") == package_dir / "supplies.json"
    assert resource_path("없는파일.json") == package_dir / "없는파일.json"


def test_frozen_uses_exe_dir(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "crypto-alert.exe"
    exe.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    assert is_frozen() is True
    assert app_data_dir() == tmp_path


def test_frozen_resource_override_first(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "crypto-alert.exe"
    exe.touch()
    meipass = tmp_path / "_MEI123"
    meipass.mkdir()
    (meipass / "supplies.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    # exe 옆 덮어쓰기 없음 → 번들 사용
    assert resource_path("supplies.json") == meipass / "supplies.json"
    # exe 옆 파일이 있으면 우선
    override = tmp_path / "supplies.json"
    override.write_text("{}", encoding="utf-8")
    assert resource_path("supplies.json") == override
