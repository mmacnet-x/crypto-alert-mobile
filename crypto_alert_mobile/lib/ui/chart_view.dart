import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../indicators/indicator_calculator.dart';
import '../models/candle.dart';
import '../models/interval.dart';
import '../services/crypto_engine.dart';
import '../utils/formatting.dart';
import 'theme.dart';

class ChartView extends StatefulWidget {
  const ChartView({super.key});

  @override
  State<ChartView> createState() => _ChartViewState();
}

class _ChartViewState extends State<ChartView> {
  String _selectedExchange = 'upbit';
  String _selectedSymbol = 'BTC/KRW';
  CandleInterval _selectedInterval = CandleInterval.m15;

  bool _showMa = true;
  bool _showBb = true;
  bool _showRsi = false;
  bool _showMacd = false;

  List<Candle> _candles = [];
  bool _isLoading = false;
  double _candleWidth = 8.0;
  double _scrollOffset = 0.0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadCandles();
    });
  }

  Future<void> _loadCandles() async {
    setState(() => _isLoading = true);
    final engine = context.read<CryptoEngine>();
    try {
      final candles = await engine.fetchCandles(
        _selectedExchange,
        _selectedSymbol,
        _selectedInterval,
      );
      if (mounted) {
        setState(() {
          _candles = candles;
          _isLoading = false;
          _scrollOffset = 0; // 최신 캔들로 리셋
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  // 주기별 MA 사양 (9단계 반영)
  List<int> get _maPeriods {
    switch (_selectedInterval) {
      case CandleInterval.m15:
        return [8, 96, 192];
      case CandleInterval.h4:
        return [6, 42, 168];
      case CandleInterval.d1:
      case CandleInterval.w1:
      case CandleInterval.mn:
        return [60, 120, 200];
    }
  }

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<CryptoEngine>();
    final ticker = engine.getTicker(_selectedExchange, _selectedSymbol);
    final watchlist = engine.watchlist[_selectedExchange] ?? [];

    return Column(
      children: [
        // 상단 컨트롤 바 (거래소, 심볼, 주기)
        Container(
          color: AppTheme.surface,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Column(
            children: [
              Row(
                children: [
                  // 거래소 드롭다운
                  DropdownButton<String>(
                    value: _selectedExchange,
                    dropdownColor: AppTheme.surfaceLight,
                    underline: const SizedBox(),
                    items: const [
                      DropdownMenuItem(value: 'upbit', child: Text('업비트')),
                      DropdownMenuItem(value: 'binance', child: Text('바이낸스')),
                      DropdownMenuItem(value: 'okx', child: Text('OKX')),
                    ],
                    onChanged: (val) {
                      if (val != null && val != _selectedExchange) {
                        setState(() {
                          _selectedExchange = val;
                          final list = engine.watchlist[val] ?? [];
                          _selectedSymbol = list.isNotEmpty
                              ? (val == 'upbit' ? '${list.first}/KRW' : list.first)
                              : 'BTC/KRW';
                        });
                        _loadCandles();
                      }
                    },
                  ),
                  const SizedBox(width: 8),
                  // 심볼 드롭다운
                  Expanded(
                    child: DropdownButton<String>(
                      value: watchlist.contains(_selectedSymbol) ||
                              watchlist.contains(_selectedSymbol.split('/')[0])
                          ? _selectedSymbol
                          : (watchlist.isNotEmpty ? (_selectedExchange == 'upbit' ? '${watchlist.first}/KRW' : watchlist.first) : null),
                      isExpanded: true,
                      dropdownColor: AppTheme.surfaceLight,
                      underline: const SizedBox(),
                      items: watchlist.map((s) {
                        final sym = _selectedExchange == 'upbit' ? (s.contains('/') ? s : '$s/KRW') : s;
                        return DropdownMenuItem(
                          value: sym,
                          child: Text(sym, style: const TextStyle(fontWeight: FontWeight.bold)),
                        );
                      }).toList(),
                      onChanged: (val) {
                        if (val != null) {
                          setState(() => _selectedSymbol = val);
                          _loadCandles();
                        }
                      },
                    ),
                  ),
                  // 새로고침 버튼
                  IconButton(
                    icon: const Icon(Icons.refresh, size: 20),
                    onPressed: _loadCandles,
                  ),
                ],
              ),
              const SizedBox(height: 4),
              // 실시간 시세 및 등락률 요약
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Text(
                        ticker != null ? Formatting.formatPrice(ticker.price) : '-',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: ticker == null
                              ? AppTheme.textPrimary
                              : (ticker.changeRate >= 0 ? AppTheme.upColor : AppTheme.downColor),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        ticker != null ? Formatting.formatChange(ticker.changeRate) : '-',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: ticker == null
                              ? AppTheme.textSecondary
                              : (ticker.changeRate >= 0 ? AppTheme.upColor : AppTheme.downColor),
                        ),
                      ),
                    ],
                  ),
                  Text(
                    ticker != null ? '24h 거래량: ${Formatting.formatVolume(ticker.volume)}' : '',
                    style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                  ),
                ],
              ),
              const Divider(color: AppTheme.border, height: 12),
              // 주기 선택 버튼 및 지표 토글 버튼
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // 주기 (15m, 4h, 1d, 1w, 1M)
                  Row(
                    children: CandleInterval.values.map((interval) {
                      final isSelected = _selectedInterval == interval;
                      return InkWell(
                        onTap: () {
                          setState(() => _selectedInterval = interval);
                          _loadCandles();
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
                          margin: const EdgeInsets.only(right: 4),
                          decoration: BoxDecoration(
                            color: isSelected ? const Color(0xFF2962FF) : Colors.transparent,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            interval.label,
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                              color: isSelected ? Colors.white : AppTheme.textSecondary,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  // 지표 토글 (MA, BB, RSI, MACD)
                  Row(
                    children: [
                      _buildIndicatorChip('MA', _showMa, () => setState(() => _showMa = !_showMa)),
                      _buildIndicatorChip('BB', _showBb, () => setState(() => _showBb = !_showBb)),
                      _buildIndicatorChip('RSI', _showRsi, () => setState(() => _showRsi = !_showRsi)),
                      _buildIndicatorChip('MACD', _showMacd, () => setState(() => _showMacd = !_showMacd)),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),

        // 차트 본체 (캔들 + 볼륨 + 보조지표 서브패널)
        Expanded(
          child: _isLoading
              ? const Center(child: CircularProgressIndicator())
              : _candles.isEmpty
                  ? const Center(child: Text('차트 데이터가 없습니다.'))
                  : GestureDetector(
                      onScaleUpdate: (details) {
                        setState(() {
                          _candleWidth = (_candleWidth * details.scale).clamp(3.0, 30.0);
                          _scrollOffset += details.focalPointDelta.dx;
                        });
                      },
                      child: CustomPaint(
                        size: Size.infinite,
                        painter: CandlestickChartPainter(
                          candles: _candles,
                          candleWidth: _candleWidth,
                          scrollOffset: _scrollOffset,
                          showMa: _showMa,
                          maPeriods: _maPeriods,
                          showBb: _showBb,
                          showRsi: _showRsi,
                          showMacd: _showMacd,
                        ),
                      ),
                    ),
        ),
      ],
    );
  }

  Widget _buildIndicatorChip(String label, bool active, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
        margin: const EdgeInsets.only(left: 3),
        decoration: BoxDecoration(
          color: active ? AppTheme.surfaceLight : Colors.transparent,
          border: Border.all(color: active ? const Color(0xFF2962FF) : AppTheme.border),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            color: active ? Colors.white : AppTheme.textSecondary,
            fontWeight: active ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

/// 캔들 및 보조지표 렌더링 Painter
class CandlestickChartPainter extends CustomPainter {
  final List<Candle> candles;
  final double candleWidth;
  final double scrollOffset;
  final bool showMa;
  final List<int> maPeriods;
  final bool showBb;
  final bool showRsi;
  final bool showMacd;

  CandlestickChartPainter({
    required this.candles,
    required this.candleWidth,
    required this.scrollOffset,
    required this.showMa,
    required this.maPeriods,
    required this.showBb,
    required this.showRsi,
    required this.showMacd,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty) return;

    // 패널 높이 분배
    double subPanelHeight = 0.0;
    int subPanels = (showRsi ? 1 : 0) + (showMacd ? 1 : 0);
    if (subPanels > 0) {
      subPanelHeight = min(90.0, size.height * 0.22);
    }
    final volumeHeight = size.height * 0.15;
    final mainChartHeight = size.height - (subPanelHeight * subPanels) - volumeHeight;

    // 표시 가능한 캔들 수 계산
    final visibleCount = (size.width / candleWidth).ceil() + 2;
    final maxOffset = max(0.0, (candles.length * candleWidth) - size.width);
    final clampedOffset = scrollOffset.clamp(-maxOffset, 0.0);

    final endIndex = min(candles.length, ((-clampedOffset + size.width) / candleWidth).ceil());
    final startIndex = max(0, endIndex - visibleCount);

    final visibleCandles = candles.sublist(startIndex, endIndex);
    if (visibleCandles.isEmpty) return;

    // 최고가/최저가 및 거래량 계산
    double maxPrice = visibleCandles.map((c) => c.high).reduce(max);
    double minPrice = visibleCandles.map((c) => c.low).reduce(min);
    double maxVolume = visibleCandles.map((c) => c.volume).reduce(max);
    if (maxVolume == 0) maxVolume = 1.0;

    // 지표 연산
    final closes = candles.map((c) => c.close).toList();
    List<double>? ma1, ma2, ma3;
    if (showMa && maPeriods.length >= 3) {
      ma1 = IndicatorCalculator.sma(closes, maPeriods[0]);
      ma2 = IndicatorCalculator.sma(closes, maPeriods[1]);
      ma3 = IndicatorCalculator.sma(closes, maPeriods[2]);
    }
    BollingerResult? bb;
    if (showBb) {
      bb = IndicatorCalculator.bollinger(closes, period: 20, mult: 2.0);
      for (int i = startIndex; i < endIndex; i++) {
        if (!bb.upper[i].isNaN && bb.upper[i] > maxPrice) maxPrice = bb.upper[i];
        if (!bb.lower[i].isNaN && bb.lower[i] < minPrice) minPrice = bb.lower[i];
      }
    }

    final priceRange = (maxPrice - minPrice) == 0 ? 1.0 : (maxPrice - minPrice);
    final pricePadding = priceRange * 0.05;
    final adjMaxPrice = maxPrice + pricePadding;
    final adjMinPrice = minPrice - pricePadding;
    final adjRange = adjMaxPrice - adjMinPrice;

    double getY(double price) {
      return mainChartHeight - ((price - adjMinPrice) / adjRange * mainChartHeight);
    }

    // 배경 그리드 선
    final gridPaint = Paint()
      ..color = AppTheme.border.withOpacity(0.3)
      ..strokeWidth = 0.5;
    for (int i = 1; i <= 4; i++) {
      final y = (mainChartHeight / 5) * i;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    // 캔들 및 거래량 렌더링
    for (int i = 0; i < visibleCandles.length; i++) {
      final c = visibleCandles[i];
      final globalIdx = startIndex + i;
      final x = size.width - ((endIndex - globalIdx) * candleWidth);

      final isUp = c.close >= c.open;
      final color = isUp ? AppTheme.upColor : AppTheme.downColor;
      final paint = Paint()..color = color;

      // 1. 심지 (Wick)
      final highY = getY(c.high);
      final lowY = getY(c.low);
      final wickPaint = Paint()
        ..color = color
        ..strokeWidth = 1.0;
      canvas.drawLine(Offset(x + candleWidth * 0.5, highY), Offset(x + candleWidth * 0.5, lowY), wickPaint);

      // 2. 몸통 (Body)
      final openY = getY(c.open);
      final closeY = getY(c.close);
      final top = min(openY, closeY);
      final bodyHeight = max(1.0, (openY - closeY).abs());
      canvas.drawRect(
        Rect.fromLTWH(x + 1.0, top, max(1.0, candleWidth - 2.0), bodyHeight),
        paint,
      );

      // 3. 거래량 (Volume) 바
      final volHeight = (c.volume / maxVolume) * volumeHeight;
      final volTop = mainChartHeight + volumeHeight - volHeight;
      final volPaint = Paint()..color = color.withOpacity(0.4);
      canvas.drawRect(
        Rect.fromLTWH(x + 1.0, volTop, max(1.0, candleWidth - 2.0), volHeight),
        volPaint,
      );
    }

    // 볼린저 밴드 (중심선은 점선 처리)
    if (showBb && bb != null) {
      final upperPath = Path();
      final midPath = Path();
      final lowerPath = Path();
      bool started = false;

      for (int i = startIndex; i < endIndex; i++) {
        final x = size.width - ((endIndex - i) * candleWidth) + candleWidth * 0.5;
        if (!bb.upper[i].isNaN && !bb.lower[i].isNaN) {
          final uY = getY(bb.upper[i]);
          final mY = getY(bb.middle[i]);
          final lY = getY(bb.lower[i]);

          if (!started) {
            upperPath.moveTo(x, uY);
            midPath.moveTo(x, mY);
            lowerPath.moveTo(x, lY);
            started = true;
          } else {
            upperPath.lineTo(x, uY);
            midPath.lineTo(x, mY);
            lowerPath.lineTo(x, lY);
          }
        }
      }

      final bandPaint = Paint()
        ..color = AppTheme.bollinger.withOpacity(0.7)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0;
      canvas.drawPath(upperPath, bandPaint);
      canvas.drawPath(lowerPath, bandPaint);

      // 중심선 점선 (중앙 20일 SMA)
      final midPaint = Paint()
        ..color = AppTheme.bollinger.withOpacity(0.9)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0;
      canvas.drawPath(midPath, midPaint);
    }

    // 이동평균선 (MA)
    if (showMa && ma1 != null && ma2 != null && ma3 != null) {
      _drawMaLine(canvas, size, startIndex, endIndex, ma1, AppTheme.maShort, getY);
      _drawMaLine(canvas, size, startIndex, endIndex, ma2, AppTheme.maMedium, getY);
      _drawMaLine(canvas, size, startIndex, endIndex, ma3, AppTheme.maLong, getY);
    }

    // 서브패널 (RSI)
    double currentSubY = mainChartHeight + volumeHeight;
    if (showRsi) {
      _drawRsiPanel(canvas, size, currentSubY, subPanelHeight, startIndex, endIndex, closes);
      currentSubY += subPanelHeight;
    }

    // 서브패널 (MACD)
    if (showMacd) {
      _drawMacdPanel(canvas, size, currentSubY, subPanelHeight, startIndex, endIndex, closes);
    }
  }

  void _drawMaLine(
    Canvas canvas,
    Size size,
    int startIndex,
    int endIndex,
    List<double> ma,
    Color color,
    double Function(double) getY,
  ) {
    final path = Path();
    bool started = false;
    for (int i = startIndex; i < endIndex; i++) {
      if (i < ma.length && !ma[i].isNaN) {
        final x = size.width - ((endIndex - i) * candleWidth) + candleWidth * 0.5;
        final y = getY(ma[i]);
        if (!started) {
          path.moveTo(x, y);
          started = true;
        } else {
          path.lineTo(x, y);
        }
      }
    }
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    canvas.drawPath(path, paint);
  }

  void _drawRsiPanel(
    Canvas canvas,
    Size size,
    double top,
    double height,
    int startIndex,
    int endIndex,
    List<double> closes,
  ) {
    // 배경 구분선
    canvas.drawLine(Offset(0, top), Offset(size.width, top), Paint()..color = AppTheme.border);
    final rsiValues = IndicatorCalculator.rsi(closes, period: 14);

    // 30 / 70 가이드선
    final y70 = top + height * 0.3;
    final y30 = top + height * 0.7;
    final guidePaint = Paint()
      ..color = Colors.amber.withOpacity(0.3)
      ..strokeWidth = 0.5;
    canvas.drawLine(Offset(0, y70), Offset(size.width, y70), guidePaint);
    canvas.drawLine(Offset(0, y30), Offset(size.width, y30), guidePaint);

    final path = Path();
    bool started = false;
    for (int i = startIndex; i < endIndex; i++) {
      if (i < rsiValues.length && !rsiValues[i].isNaN) {
        final x = size.width - ((endIndex - i) * candleWidth) + candleWidth * 0.5;
        final y = top + (height - (rsiValues[i] / 100.0 * height));
        if (!started) {
          path.moveTo(x, y);
          started = true;
        } else {
          path.lineTo(x, y);
        }
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = Colors.purpleAccent
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );
  }

  void _drawMacdPanel(
    Canvas canvas,
    Size size,
    double top,
    double height,
    int startIndex,
    int endIndex,
    List<double> closes,
  ) {
    canvas.drawLine(Offset(0, top), Offset(size.width, top), Paint()..color = AppTheme.border);
    final macd = IndicatorCalculator.macd(closes);

    final midY = top + height * 0.5;
    canvas.drawLine(Offset(0, midY), Offset(size.width, midY), Paint()..color = AppTheme.border.withOpacity(0.4));

    // 최대 진폭 구하기
    double maxAmp = 1.0;
    for (int i = startIndex; i < endIndex; i++) {
      if (i < macd.histogram.length && !macd.histogram[i].isNaN) {
        maxAmp = max(maxAmp, macd.histogram[i].abs());
      }
    }

    // 히스토그램 바 렌더링
    for (int i = startIndex; i < endIndex; i++) {
      if (i < macd.histogram.length && !macd.histogram[i].isNaN) {
        final x = size.width - ((endIndex - i) * candleWidth);
        final val = macd.histogram[i];
        final barHeight = (val / maxAmp) * (height * 0.45);
        final isPositive = val >= 0;
        final color = isPositive ? AppTheme.upColor : AppTheme.downColor;
        canvas.drawRect(
          Rect.fromLTWH(x + 1, isPositive ? midY - barHeight : midY, candleWidth - 2, barHeight.abs()),
          Paint()..color = color.withOpacity(0.7),
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant CandlestickChartPainter oldDelegate) => true;
}
