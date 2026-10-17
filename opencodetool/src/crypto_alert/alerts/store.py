"""알림 규칙 저장/불러오기 (alert_rules.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crypto_alert.alerts.rules import AlertRule, RuleError
from crypto_alert.paths import app_data_dir

__all__ = ["RulesError", "load_rules", "rules_path", "save_rules"]


class RulesError(ValueError):
    """규칙 파일이 깨졌을 때 발생."""


def rules_path() -> Path:
    """규칙 JSON 파일 경로 (watchlist.json과 같은 폴더)."""
    return app_data_dir() / "alert_rules.json"


def load_rules(path: Path | None = None) -> list[AlertRule]:
    """규칙 목록을 읽는다. 파일이 없으면 빈 목록을 반환한다."""
    target = path or rules_path()
    if not target.exists():
        return []
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RulesError(f"규칙 파일을 읽을 수 없습니다: {target} ({exc})") from exc
    if not isinstance(raw, list):
        raise RulesError(f"규칙 파일 형식이 잘못되었습니다: {target}")
    rules: list[AlertRule] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RulesError(f"규칙 #{index} 형식이 잘못되었습니다")
        try:
            rules.append(AlertRule.from_dict(item))
        except RuleError as exc:
            raise RulesError(f"규칙 #{index} 오류: {exc}") from exc
    return rules


def save_rules(rules: list[AlertRule], path: Path | None = None) -> None:
    """규칙 목록을 파일에 저장한다."""
    target = path or rules_path()
    payload: list[dict[str, Any]] = [rule.to_dict() for rule in rules]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise RulesError(f"규칙 저장 실패: {target} ({exc})") from exc
