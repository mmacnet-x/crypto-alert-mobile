"""프로그램 진입점: 4패널 메인 윈도우 실행."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from crypto_alert.ui.main_window import MainWindow


def create_main_window(start_engine: bool = True) -> MainWindow:
    """메인 윈도우를 생성해 반환한다 (테스트에서 재사용)."""
    return MainWindow(start_engine=start_engine)


def main() -> int:
    """Qt 애플리케이션을 실행하고 종료 코드를 반환한다."""
    if "--smoke" in sys.argv:
        return _smoke()
    app = QApplication(sys.argv)
    app.setApplicationName("crypto-alert")
    # 한글 폰트 명시 지정 (시스템 기본 폰트가 한글을 못 그리는 환경 대비)
    app.setFont(QFont("Malgun Gothic", 9))
    window = create_main_window()
    window.show()
    return app.exec()


def _smoke() -> int:
    """frozen exe 검증용: 엔진 없이 창을 구성하고 즉시 종료한다."""
    app = QApplication(sys.argv)
    app.setApplicationName("crypto-alert")
    window = create_main_window(start_engine=False)
    app.processEvents()
    rules = len(window._alerts.rules)
    supplies = len(window._supplies)
    print(f"SMOKE OK watchlist={window._watchlist} rules={rules} supplies={supplies}", flush=True)
    window.close()
    return 0


if __name__ == "__main__":  # pragma: no cover — 직접 실행 전용
    raise SystemExit(main())
