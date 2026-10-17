/// 알림 규칙 모델
class AlertRule {
  final String id;
  final String exchange; // upbit, binance, okx
  final String symbol; // BTC/KRW, BTC/USDT 등
  final String interval; // 15m, 4h, 1d 등 (캔들 조건일 때)
  final String condition; // price_above, golden_cross 등
  final Map<String, dynamic> params; // {target: 100000000} 등
  final int cooldownMinutes; // 재알림 방지 쿨다운 (기본 30분)
  bool enabled;
  DateTime? lastTriggered;
  bool lastState; // 엣지 트리거(false -> true) 판단용

  AlertRule({
    required this.id,
    required this.exchange,
    required this.symbol,
    required this.interval,
    required this.condition,
    required this.params,
    this.cooldownMinutes = 30,
    this.enabled = true,
    this.lastTriggered,
    this.lastState = false,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'exchange': exchange,
    'symbol': symbol,
    'interval': interval,
    'condition': condition,
    'params': params,
    'cooldown_minutes': cooldownMinutes,
    'enabled': enabled,
    'last_triggered': lastTriggered?.toIso8601String(),
    'last_state': lastState,
  };

  factory AlertRule.fromJson(Map<String, dynamic> json) => AlertRule(
    id: json['id'] as String,
    exchange: json['exchange'] as String,
    symbol: json['symbol'] as String,
    interval: json['interval'] as String? ?? '15m',
    condition: json['condition'] as String,
    params: Map<String, dynamic>.from(json['params'] as Map? ?? {}),
    cooldownMinutes: (json['cooldown_minutes'] as num?)?.toInt() ?? 30,
    enabled: json['enabled'] as bool? ?? true,
    lastTriggered: json['last_triggered'] != null
        ? DateTime.tryParse(json['last_triggered'] as String)
        : null,
    lastState: json['last_state'] as bool? ?? false,
  );
}
