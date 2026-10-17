import '../models/candle.dart';
import '../utils/formatting.dart';
import '../indicators/indicator_calculator.dart';

class ConditionEvaluation {
  final bool triggered;
  final String message;

  const ConditionEvaluation(this.triggered, this.message);
}

class AlertConditions {
  static const Map<String, String> conditionLabels = {
    'price_above': '가격 ≥ 목표',
    'price_below': '가격 ≤ 목표',
    'golden_cross': '골든크로스 (단기 MA > 장기 MA)',
    'dead_cross': '데드크로스 (단기 MA < 장기 MA)',
    'rsi_overbought': 'RSI 과매수 (≥ 기준값)',
    'rsi_oversold': 'RSI 과매도 (≤ 기준값)',
    'macd_bullish': 'MACD 골든크로스 (상향 돌파)',
    'macd_bearish': 'MACD 데드크로스 (하향 돌파)',
    'bb_breakout_up': '볼린저 밴드 상단 돌파',
    'bb_breakout_down': '볼린저 밴드 하단 이탈',
  };

  static ConditionEvaluation evaluatePrice(
    String condition,
    double price,
    Map<String, dynamic> params,
  ) {
    final target = (params['target'] as num?)?.toDouble() ?? 0.0;
    if (condition == 'price_above') {
      final triggered = price >= target;
      final msg = '현재가 ${Formatting.formatPrice(price)} (목표 ${Formatting.formatPrice(target)})';
      return ConditionEvaluation(triggered, msg);
    }
    if (condition == 'price_below') {
      final triggered = price <= target;
      final msg = '현재가 ${Formatting.formatPrice(price)} (목표 ${Formatting.formatPrice(target)})';
      return ConditionEvaluation(triggered, msg);
    }
    return const ConditionEvaluation(false, '미지원 가격 조건');
  }

  static ConditionEvaluation evaluateCandles(
    String condition,
    List<Candle> candles,
    Map<String, dynamic> params,
  ) {
    if (candles.isEmpty) {
      return const ConditionEvaluation(false, '캔들 데이터 없음');
    }
    final closes = candles.map((c) => c.close).toList();

    switch (condition) {
      case 'golden_cross': {
        final fast = (params['fast'] as num?)?.toInt() ?? 5;
        final slow = (params['slow'] as num?)?.toInt() ?? 20;
        if (closes.length < slow + 1) return const ConditionEvaluation(false, '캔들 부족');
        final fastMa = IndicatorCalculator.sma(closes, fast);
        final slowMa = IndicatorCalculator.sma(closes, slow);
        final crossed = IndicatorCalculator.crossOver(fastMa, slowMa);
        final fVal = fastMa.last;
        final sVal = slowMa.last;
        final state = 'MA$fast ${Formatting.formatPrice(fVal)} / MA$slow ${Formatting.formatPrice(sVal)}';
        if (crossed) {
          return ConditionEvaluation(true, '골든크로스 발생 ($state)');
        }
        return ConditionEvaluation(false, '$state ${fVal > sVal ? "↑" : "↓"}');
      }

      case 'dead_cross': {
        final fast = (params['fast'] as num?)?.toInt() ?? 5;
        final slow = (params['slow'] as num?)?.toInt() ?? 20;
        if (closes.length < slow + 1) return const ConditionEvaluation(false, '캔들 부족');
        final fastMa = IndicatorCalculator.sma(closes, fast);
        final slowMa = IndicatorCalculator.sma(closes, slow);
        final crossed = IndicatorCalculator.crossUnder(fastMa, slowMa);
        final fVal = fastMa.last;
        final sVal = slowMa.last;
        final state = 'MA$fast ${Formatting.formatPrice(fVal)} / MA$slow ${Formatting.formatPrice(sVal)}';
        if (crossed) {
          return ConditionEvaluation(true, '데드크로스 발생 ($state)');
        }
        return ConditionEvaluation(false, '$state ${fVal < sVal ? "↓" : "↑"}');
      }

      case 'rsi_overbought': {
        final period = (params['period'] as num?)?.toInt() ?? 14;
        final threshold = (params['threshold'] as num?)?.toDouble() ?? 70.0;
        if (closes.length <= period) return const ConditionEvaluation(false, '캔들 부족');
        final rsiList = IndicatorCalculator.rsi(closes, period: period);
        final last = rsiList.last;
        if (last.isNaN) return const ConditionEvaluation(false, '지표 웜업 중');
        final triggered = last >= threshold;
        return ConditionEvaluation(
          triggered,
          'RSI($period) ${last.toStringAsFixed(1)} (기준 ${threshold.toStringAsFixed(0)})',
        );
      }

      case 'rsi_oversold': {
        final period = (params['period'] as num?)?.toInt() ?? 14;
        final threshold = (params['threshold'] as num?)?.toDouble() ?? 30.0;
        if (closes.length <= period) return const ConditionEvaluation(false, '캔들 부족');
        final rsiList = IndicatorCalculator.rsi(closes, period: period);
        final last = rsiList.last;
        if (last.isNaN) return const ConditionEvaluation(false, '지표 웜업 중');
        final triggered = last <= threshold;
        return ConditionEvaluation(
          triggered,
          'RSI($period) ${last.toStringAsFixed(1)} (기준 ${threshold.toStringAsFixed(0)})',
        );
      }

      case 'macd_bullish': {
        final fast = (params['fast'] as num?)?.toInt() ?? 12;
        final slow = (params['slow'] as num?)?.toInt() ?? 26;
        final signal = (params['signal'] as num?)?.toInt() ?? 9;
        if (closes.length < slow + signal) return const ConditionEvaluation(false, '캔들 부족');
        final macd = IndicatorCalculator.macd(closes, fast: fast, slow: slow, signal: signal);
        final crossed = IndicatorCalculator.crossOver(macd.line, macd.signal);
        final lVal = macd.line.last;
        final sVal = macd.signal.last;
        if (crossed) {
          return ConditionEvaluation(true, 'MACD 상향 돌파 (MACD ${lVal.toStringAsFixed(2)} > 시그널 ${sVal.toStringAsFixed(2)})');
        }
        return ConditionEvaluation(false, 'MACD ${lVal.toStringAsFixed(2)} / 시그널 ${sVal.toStringAsFixed(2)}');
      }

      case 'macd_bearish': {
        final fast = (params['fast'] as num?)?.toInt() ?? 12;
        final slow = (params['slow'] as num?)?.toInt() ?? 26;
        final signal = (params['signal'] as num?)?.toInt() ?? 9;
        if (closes.length < slow + signal) return const ConditionEvaluation(false, '캔들 부족');
        final macd = IndicatorCalculator.macd(closes, fast: fast, slow: slow, signal: signal);
        final crossed = IndicatorCalculator.crossUnder(macd.line, macd.signal);
        final lVal = macd.line.last;
        final sVal = macd.signal.last;
        if (crossed) {
          return ConditionEvaluation(true, 'MACD 하향 돌파 (MACD ${lVal.toStringAsFixed(2)} < 시그널 ${sVal.toStringAsFixed(2)})');
        }
        return ConditionEvaluation(false, 'MACD ${lVal.toStringAsFixed(2)} / 시그널 ${sVal.toStringAsFixed(2)}');
      }

      case 'bb_breakout_up': {
        final period = (params['period'] as num?)?.toInt() ?? 20;
        final mult = (params['mult'] as num?)?.toDouble() ?? 2.0;
        if (closes.length < period) return const ConditionEvaluation(false, '캔들 부족');
        final bb = IndicatorCalculator.bollinger(closes, period: period, mult: mult);
        final upper = bb.upper.last;
        final close = closes.last;
        final triggered = close > upper;
        return ConditionEvaluation(
          triggered,
          '종가 ${Formatting.formatPrice(close)} (상단 ${Formatting.formatPrice(upper)})',
        );
      }

      case 'bb_breakout_down': {
        final period = (params['period'] as num?)?.toInt() ?? 20;
        final mult = (params['mult'] as num?)?.toDouble() ?? 2.0;
        if (closes.length < period) return const ConditionEvaluation(false, '캔들 부족');
        final bb = IndicatorCalculator.bollinger(closes, period: period, mult: mult);
        final lower = bb.lower.last;
        final close = closes.last;
        final triggered = close < lower;
        return ConditionEvaluation(
          triggered,
          '종가 ${Formatting.formatPrice(close)} (하단 ${Formatting.formatPrice(lower)})',
        );
      }

      default:
        return const ConditionEvaluation(false, '미지원 지표 조건');
    }
  }
}
