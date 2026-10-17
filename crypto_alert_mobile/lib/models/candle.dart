import 'interval.dart';

/// 표준 캔들 데이터 모델
class Candle {
  final String symbol;
  final CandleInterval interval;
  final DateTime time;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;

  const Candle({
    required this.symbol,
    required this.interval,
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
  });

  Candle copyWith({
    String? symbol,
    CandleInterval? interval,
    DateTime? time,
    double? open,
    double? high,
    double? low,
    double? close,
    double? volume,
  }) {
    return Candle(
      symbol: symbol ?? this.symbol,
      interval: interval ?? this.interval,
      time: time ?? this.time,
      open: open ?? this.open,
      high: high ?? this.high,
      low: low ?? this.low,
      close: close ?? this.close,
      volume: volume ?? this.volume,
    );
  }
}
