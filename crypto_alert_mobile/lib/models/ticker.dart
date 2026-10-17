/// 실시간 시세 / 스냅샷 데이터 모델
class Ticker {
  final String symbol;
  final double price;
  final double changeRate; // 등락률(소수): 0.021 -> +2.1%
  final double volume; // 24h 누적 거래량
  final DateTime time;

  const Ticker({
    required this.symbol,
    required this.price,
    required this.changeRate,
    required this.volume,
    required this.time,
  });

  Map<String, dynamic> toJson() => {
    'symbol': symbol,
    'price': price,
    'changeRate': changeRate,
    'volume': volume,
    'time': time.toIso8601String(),
  };

  factory Ticker.fromJson(Map<String, dynamic> json) => Ticker(
    symbol: json['symbol'] as String,
    price: (json['price'] as num).toDouble(),
    changeRate: (json['changeRate'] as num).toDouble(),
    volume: (json['volume'] as num).toDouble(),
    time: DateTime.parse(json['time'] as String),
  );
}
