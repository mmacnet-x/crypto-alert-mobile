"""감시 목록 타입 별칭 (순환 import 방지용)."""

from __future__ import annotations

type Watchlist = dict[str, list[str]]
