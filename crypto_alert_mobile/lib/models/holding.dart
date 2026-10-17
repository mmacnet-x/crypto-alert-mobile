/// 사용자 보유 종목 및 평가 모델
class Holding {
  final String symbol;
  final double quantity;
  final double avgPrice;

  const Holding({
    required this.symbol,
    required this.quantity,
    required this.avgPrice,
  });

  Map<String, dynamic> toJson() => {
    'symbol': symbol,
    'quantity': quantity,
    'avg_price': avgPrice,
  };

  factory Holding.fromJson(Map<String, dynamic> json) => Holding(
    symbol: json['symbol'] as String,
    quantity: (json['quantity'] as num).toDouble(),
    avgPrice: (json['avg_price'] as num).toDouble(),
  );
}

class PositionValue {
  final double currentPrice;
  final double valuation; // 평가금액
  final double pnl; // 손익금
  final double pnlRate; // 수익률 (0.05 = +5%)

  const PositionValue({
    required this.currentPrice,
    required this.valuation,
    required this.pnl,
    required this.pnlRate,
  });

  static PositionValue calculate(Holding holding, double currentPrice) {
    final val = holding.quantity * currentPrice;
    final cost = holding.quantity * holding.avgPrice;
    final pnl = val - cost;
    final rate = cost > 0 ? (pnl / cost) : 0.0;
    return PositionValue(
      currentPrice: currentPrice,
      valuation: val,
      pnl: pnl,
      pnlRate: rate,
    );
  }
}
