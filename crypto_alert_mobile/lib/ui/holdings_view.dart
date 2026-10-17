import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/holding.dart';
import '../services/crypto_engine.dart';
import '../utils/formatting.dart';
import 'theme.dart';

class HoldingsView extends StatelessWidget {
  const HoldingsView({super.key});

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<CryptoEngine>();

    double totalCost = 0.0;
    double totalValuation = 0.0;

    final evaluatedList = engine.holdings.map((h) {
      // 업비트 또는 바이낸스 티커에서 현재가 조회
      double currentPrice = h.avgPrice;
      final upbitTicker = engine.getTicker('upbit', h.symbol);
      final binanceTicker = engine.getTicker('binance', h.symbol);

      if (upbitTicker != null && upbitTicker.price > 0) {
        currentPrice = upbitTicker.price;
      } else if (binanceTicker != null && binanceTicker.price > 0) {
        currentPrice = binanceTicker.price;
      }

      final pv = PositionValue.calculate(h, currentPrice);
      totalCost += h.quantity * h.avgPrice;
      totalValuation += pv.valuation;

      return {'holding': h, 'pv': pv};
    }).toList();

    final totalPnl = totalValuation - totalCost;
    final totalPnlRate = totalCost > 0 ? (totalPnl / totalCost) : 0.0;

    return Scaffold(
      body: Column(
        children: [
          // 포트폴리오 요약 카드
          Container(
            margin: const EdgeInsets.all(12),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('총 평가금액', style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
                const SizedBox(height: 4),
                Text(
                  Formatting.formatPrice(totalValuation),
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Text(
                      '총 손익: ${totalPnl >= 0 ? "+" : ""}${Formatting.formatPrice(totalPnl)}',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: totalPnl >= 0 ? AppTheme.upColor : AppTheme.downColor,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      Formatting.formatChange(totalPnlRate),
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: totalPnlRate >= 0 ? AppTheme.upColor : AppTheme.downColor,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          // 보유 종목 목록
          Expanded(
            child: engine.holdings.isEmpty
                ? const Center(
                    child: Text('등록된 보유 종목이 없습니다.', style: TextStyle(color: AppTheme.textSecondary)),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    itemCount: evaluatedList.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (context, index) {
                      final item = evaluatedList[index];
                      final h = item['holding'] as Holding;
                      final pv = item['pv'] as PositionValue;

                      return Card(
                        color: AppTheme.surface,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(h.symbol, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                                    const SizedBox(height: 4),
                                    Text(
                                      '보유수량: ${h.quantity} | 평단: ${Formatting.formatPrice(h.avgPrice)}',
                                      style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                                    ),
                                    Text(
                                      '현재가: ${Formatting.formatPrice(pv.currentPrice)}',
                                      style: const TextStyle(fontSize: 12, color: AppTheme.textPrimary),
                                    ),
                                  ],
                                ),
                              ),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(
                                    Formatting.formatPrice(pv.valuation),
                                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    Formatting.formatChange(pv.pnlRate),
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                      color: pv.pnlRate >= 0 ? AppTheme.upColor : AppTheme.downColor,
                                    ),
                                  ),
                                ],
                              ),
                              IconButton(
                                icon: const Icon(Icons.close, size: 18, color: AppTheme.textSecondary),
                                onPressed: () => engine.removeHolding(index),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: const Color(0xFF2962FF),
        child: const Icon(Icons.add, color: Colors.white),
        onPressed: () => _showAddHoldingDialog(context),
      ),
    );
  }

  void _showAddHoldingDialog(BuildContext context) {
    final engine = context.read<CryptoEngine>();
    final symbolController = TextEditingController(text: 'BTC/KRW');
    final qtyController = TextEditingController();
    final priceController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Text('보유 종목 추가'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: symbolController,
                decoration: const InputDecoration(labelText: '종목 심볼 (예: BTC/KRW)', filled: true, fillColor: AppTheme.surfaceLight),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: qtyController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: '보유 수량', filled: true, fillColor: AppTheme.surfaceLight),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: priceController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: '매수 평균단가', filled: true, fillColor: AppTheme.surfaceLight),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('취소', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF2962FF)),
              onPressed: () {
                final qty = double.tryParse(qtyController.text) ?? 0.0;
                final price = double.tryParse(priceController.text) ?? 0.0;
                if (qty > 0 && price > 0) {
                  engine.addHolding(Holding(
                    symbol: symbolController.text.trim().toUpperCase(),
                    quantity: qty,
                    avgPrice: price,
                  ));
                }
                Navigator.pop(context);
              },
              child: const Text('저장'),
            ),
          ],
        );
      },
    );
  }
}
