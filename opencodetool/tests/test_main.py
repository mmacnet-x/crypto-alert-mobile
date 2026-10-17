"""8단계 테스트: 진입점 --smoke (별도 프로세스, offscreen)."""

from __future__ import annotations

import os
import subprocess
import sys


def test_smoke_entry_point() -> None:
    """frozen exe와 동일한 경로(--smoke)로 창 구성이 되는지 확인한다."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(
        [sys.executable, "-m", "crypto_alert.main", "--smoke"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "SMOKE OK" in proc.stdout
    assert "supplies=" in proc.stdout


def test_main_wires_gui(monkeypatch) -> None:
    """일반 실행 경로의 배선 (실제 GUI 대신 가짜로 검증)."""
    import crypto_alert.main as main_mod

    created: dict[str, object] = {}
    shown: list[bool] = []

    class _FakeApp:
        def __init__(self, argv: list[str]) -> None:
            created["argv"] = argv

        def setApplicationName(self, name: str) -> None:
            created["name"] = name

        def setFont(self, font: object) -> None:
            created["font"] = font

        def exec(self) -> int:
            return 7

    class _FakeWindow:
        def show(self) -> None:
            shown.append(True)

    monkeypatch.setattr(main_mod, "QApplication", _FakeApp)
    monkeypatch.setattr(main_mod, "create_main_window", lambda: _FakeWindow())
    monkeypatch.setattr(sys, "argv", ["crypto-alert"])
    assert main_mod.main() == 7
    assert shown and created["name"] == "crypto-alert"


def test_main_dispatches_smoke_flag(monkeypatch) -> None:
    """--smoke 플래그 분기 (본체는 별도 프로세스 테스트에서 검증)."""
    import crypto_alert.main as main_mod

    monkeypatch.setattr(main_mod, "_smoke", lambda: 3)
    monkeypatch.setattr(sys, "argv", ["crypto-alert", "--smoke"])
    assert main_mod.main() == 3
