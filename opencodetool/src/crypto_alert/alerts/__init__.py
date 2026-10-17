"""5단계: 알림 조건 레지스트리 (가격 돌파 + 지표 신호, 무한 확장 구조).

6단계: 발송 설정/발송기 (팝업 + 사운드 + 텔레그램).
"""

from __future__ import annotations

from crypto_alert.alerts.conditions import (
    CONDITIONS,
    ConditionError,
    ConditionSpec,
    ParamDef,
    describe_rule,
    evaluate,
    validate_params,
)
from crypto_alert.alerts.engine import (
    ALERT_KEY_PREFIX,
    AlertEngine,
    AlertEvent,
    alert_key,
    parse_alert_key,
)
from crypto_alert.alerts.notify import Notifier, format_telegram_text
from crypto_alert.alerts.notify_settings import (
    NotifySettings,
    NotifySettingsError,
    load_notify_settings,
    notify_settings_path,
    save_notify_settings,
)
from crypto_alert.alerts.rules import DEFAULT_COOLDOWN_SEC, AlertRule, RuleError, new_rule
from crypto_alert.alerts.store import RulesError, load_rules, rules_path, save_rules

__all__ = [
    "ALERT_KEY_PREFIX",
    "CONDITIONS",
    "DEFAULT_COOLDOWN_SEC",
    "AlertEngine",
    "AlertEvent",
    "AlertRule",
    "ConditionError",
    "ConditionSpec",
    "Notifier",
    "NotifySettings",
    "NotifySettingsError",
    "ParamDef",
    "RuleError",
    "RulesError",
    "alert_key",
    "describe_rule",
    "evaluate",
    "format_telegram_text",
    "load_notify_settings",
    "load_rules",
    "new_rule",
    "notify_settings_path",
    "parse_alert_key",
    "rules_path",
    "save_notify_settings",
    "save_rules",
    "validate_params",
]
