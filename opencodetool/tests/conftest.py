"""pytest 공용 설정: QApplication을 한 번만 생성한다."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_APP = None


@pytest.fixture(scope="session")
def qapp():
    """세션 전체에서 공유되는 QApplication 인스턴스."""
    global _APP
    from PyQt6.QtWidgets import QApplication

    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP
