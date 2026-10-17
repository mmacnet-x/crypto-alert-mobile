/// 알림 발동 이벤트 모델
class AlertEvent {
  final String ruleId;
  final String exchange;
  final String symbol;
  final String interval;
  final String condition;
  final String message;
  final double? price;
  final DateTime time;

  const AlertEvent({
    required this.ruleId,
    required this.exchange,
    required this.symbol,
    required this.interval,
    required this.condition,
    required this.message,
    this.price,
    required this.time,
  });

  Map<String, dynamic> toJson() => {
    'ruleId': ruleId,
    'exchange': exchange,
    'symbol': symbol,
    'interval': interval,
    'condition': condition,
    'message': message,
    'price': price,
    'time': time.toIso8601String(),
  };

  factory AlertEvent.fromJson(Map<String, dynamic> json) => AlertEvent(
    ruleId: json['ruleId'] as String,
    exchange: json['exchange'] as String,
    symbol: json['symbol'] as String,
    interval: json['interval'] as String? ?? '',
    condition: json['condition'] as String,
    message: json['message'] as String,
    price: (json['price'] as num?)?.toDouble(),
    time: DateTime.parse(json['time'] as String),
  );
}
