/// 캔들 주기 표준 모델
enum CandleInterval {
  m15('15m', '15분'),
  h4('4h', '4시간'),
  d1('1d', '일봉'),
  w1('1w', '주봉'),
  mn('1M', '월봉');

  final String value;
  final String label;

  const CandleInterval(this.value, this.label);

  static CandleInterval fromString(String val) {
    for (final item in CandleInterval.values) {
      if (item.value == val) return item;
    }
    return CandleInterval.m15;
  }
}
