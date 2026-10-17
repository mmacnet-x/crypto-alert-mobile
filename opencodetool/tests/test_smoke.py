"""1단계 스모크 테스트: 패키지 임포트와 메인 윈도우 생성 확인."""

from __future__ import annotations

from crypto_alert import __version__
from crypto_alert.main import create_main_window


def test_version_is_set() -> None:
    """패키지 버전이 정의되어 있는지 확인한다."""
    assert __version__
    assert __version__.count(".") == 2


def test_main_window_created(qapp) -> None:
    """네트워크 엔진 없이도 메인 윈도우가 생성되는지 확인한다."""
    window = create_main_window(start_engine=False)
    try:
        assert window.windowTitle().startswith("코인 차트 알림")
        assert window.width() >= 1280
        assert window.centralWidget() is not None
    finally:
        window.close()
