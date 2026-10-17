import 'dart:math';

/// 지표 연산 결과 모델
class MacdResult {
  final List<double> line;
  final List<double> signal;
  final List<double> histogram;

  MacdResult({
    required this.line,
    required this.signal,
    required this.histogram,
  });
}

class BollingerResult {
  final List<double> middle;
  final List<double> upper;
  final List<double> lower;

  BollingerResult({
    required this.middle,
    required this.upper,
    required this.lower,
  });
}

/// 순수 수학적 보조지표 연산 (SMA, EMA, Wilder RSI, MACD, Bollinger Bands)
class IndicatorCalculator {
  /// 단순이동평균 (SMA) - 웜업 구간 NaN
  static List<double> sma(List<double> values, int period) {
    if (period < 1) throw ArgumentError('period는 1 이상이어야 합니다.');
    final result = List<double>.filled(values.length, double.nan);
    if (values.length < period) return result;

    double sum = 0.0;
    for (int i = 0; i < period; i++) {
      sum += values[i];
    }
    result[period - 1] = sum / period;

    for (int i = period; i < values.length; i++) {
      sum += values[i] - values[i - period];
      result[i] = sum / period;
    }
    return result;
  }

  /// 지수이동평균 (EMA) - SMA로 시드 후 지수 가중
  static List<double> ema(List<double> values, int period) {
    if (period < 1) throw ArgumentError('period는 1 이상이어야 합니다.');
    final result = List<double>.filled(values.length, double.nan);
    if (values.length < period) return result;

    double sum = 0.0;
    for (int i = 0; i < period; i++) {
      sum += values[i];
    }
    result[period - 1] = sum / period;

    final alpha = 2.0 / (period + 1.0);
    for (int i = period; i < values.length; i++) {
      result[i] = alpha * values[i] + (1.0 - alpha) * result[i - 1];
    }
    return result;
  }

  /// Wilder 방식 RSI (14주기)
  static List<double> rsi(List<double> values, {int period = 14}) {
    if (period < 1) throw ArgumentError('period는 1 이상이어야 합니다.');
    final result = List<double>.filled(values.length, double.nan);
    if (values.length <= period) return result;

    double gainSum = 0.0;
    double lossSum = 0.0;

    for (int i = 1; i <= period; i++) {
      final change = values[i] - values[i - 1];
      if (change > 0) {
        gainSum += change;
      } else {
        lossSum += -change;
      }
    }

    double avgGain = gainSum / period;
    double avgLoss = lossSum / period;

    result[period] = _calcRsi(avgGain, avgLoss);

    for (int i = period + 1; i < values.length; i++) {
      final change = values[i] - values[i - 1];
      final gain = change > 0 ? change : 0.0;
      final loss = change < 0 ? -change : 0.0;

      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;

      result[i] = _calcRsi(avgGain, avgLoss);
    }

    return result;
  }

  static double _calcRsi(double avgGain, double avgLoss) {
    if (avgGain == 0.0 && avgLoss == 0.0) return double.nan;
    if (avgLoss == 0.0) return 100.0;
    if (avgGain == 0.0) return 0.0;
    final rs = avgGain / avgLoss;
    return 100.0 - (100.0 / (1.0 + rs));
  }

  /// MACD (기본: 12, 26, 9)
  static MacdResult macd(
    List<double> values, {
    int fast = 12,
    int slow = 26,
    int signal = 9,
  }) {
    final fastEma = ema(values, fast);
    final slowEma = ema(values, slow);

    final line = List<double>.filled(values.length, double.nan);
    for (int i = 0; i < values.length; i++) {
      if (!fastEma[i].isNaN && !slowEma[i].isNaN) {
        line[i] = fastEma[i] - slowEma[i];
      }
    }

    // 시그널 라인은 macd 라인의 EMA
    final validStart = line.indexWhere((v) => !v.isNaN);
    final signalLine = List<double>.filled(values.length, double.nan);
    final hist = List<double>.filled(values.length, double.nan);

    if (validStart != -1 && (values.length - validStart) >= signal) {
      final validMacd = line.sublist(validStart);
      final validSignal = ema(validMacd, signal);

      for (int i = 0; i < validSignal.length; i++) {
        final idx = validStart + i;
        signalLine[idx] = validSignal[i];
        if (!line[idx].isNaN && !signalLine[idx].isNaN) {
          hist[idx] = line[idx] - signalLine[idx];
        }
      }
    }

    return MacdResult(line: line, signal: signalLine, histogram: hist);
  }

  /// 볼린저 밴드 (20주기, 2.0 시그마)
  static BollingerResult bollinger(
    List<double> values, {
    int period = 20,
    double mult = 2.0,
  }) {
    final middle = sma(values, period);
    final upper = List<double>.filled(values.length, double.nan);
    final lower = List<double>.filled(values.length, double.nan);

    for (int i = period - 1; i < values.length; i++) {
      final mean = middle[i];
      if (mean.isNaN) continue;

      double varianceSum = 0.0;
      for (int j = i - period + 1; j <= i; j++) {
        final diff = values[j] - mean;
        varianceSum += diff * diff;
      }
      final std = sqrt(varianceSum / period); // ddof=0
      upper[i] = mean + mult * std;
      lower[i] = mean - mult * std;
    }

    return BollingerResult(middle: middle, upper: upper, lower: lower);
  }

  /// 최신 지점에서 골든크로스(a가 b를 상향돌파) 여부 판정
  static bool crossOver(List<double> a, List<double> b) {
    if (a.length < 2 || b.length < 2) return false;
    final aPrev = a[a.length - 2];
    final bPrev = b[b.length - 2];
    final aCurr = a.last;
    final bCurr = b.last;

    if (aPrev.isNaN || bPrev.isNaN || aCurr.isNaN || bCurr.isNaN) return false;
    return aPrev <= bPrev && aCurr > bCurr;
  }

  /// 최신 지점에서 데드크로스(a가 b를 하향돌파) 여부 판정
  static bool crossUnder(List<double> a, List<double> b) {
    if (a.length < 2 || b.length < 2) return false;
    final aPrev = a[a.length - 2];
    final bPrev = b[b.length - 2];
    final aCurr = a.last;
    final bCurr = b.last;

    if (aPrev.isNaN || bPrev.isNaN || aCurr.isNaN || bCurr.isNaN) return false;
    return aPrev >= bPrev && aCurr < bCurr;
  }
}
