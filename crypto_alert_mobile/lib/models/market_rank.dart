/// 시가총액 순위 항목 모델
class MarketRank {
  final String base; // 기본 심볼 (예: BTC)
  final String symbol; // 기준 심볼 (예: BTC/USDT)
  final String exchange; // 가격 근거 거래소
  final double priceUsd; // USD 환산가
  final double marketCapUsd; // 시가총액 (USD)
  final double changeRate; // 24h 변동률
  final double supply; // 유통량

  const MarketRank({
    required this.base,
    required this.symbol,
    required this.exchange,
    required this.priceUsd,
    required this.marketCapUsd,
    required this.changeRate,
    required this.supply,
  });
}
