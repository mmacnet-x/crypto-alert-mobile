"""exe 패키징 대응 경로 해결 (PyInstaller --onefile).

- 개발 실행: 패키지 폴더 기준 (기존 동작 유지)
- frozen exe: 사용자 수정 JSON은 exe 옆 폴더(쓰기 가능),
  읽기 전용 번들(supplies.json)은 _MEIPASS에서 찾는다.
  exe 옆에 동명 파일이 있으면 그것을 우선한다(덮어쓰기용).
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["app_data_dir", "is_frozen", "resource_path"]


def is_frozen() -> bool:
    """PyInstaller로 패키징된 exe 실행 여부."""
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """사용자 수정 JSON을 둘 폴더 (개발: 패키지 폴더, exe: exe 옆)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    """읽기 전용 번들 파일 경로 (exe 옆 덮어쓰기 → _MEIPASS 순으로 탐색)."""
    override = app_data_dir() / name
    if override.exists():
        return override
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", app_data_dir()))
        return base / name
    return Path(__file__).resolve().parent / name
