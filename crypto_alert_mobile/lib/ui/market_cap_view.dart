import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/crypto_engine.dart';
import '../utils/formatting.dart';
import 'theme.dart';

class MarketCapView extends StatelessWidget {
  const MarketCapView({super.key});

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<CryptoEngine>();
    final ranks = engine.marketRanks;

    if (ranks.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text('시가총액 순위 계산 중...', style: TextStyle(color: AppTheme.textSecondary)),
          ],
        ),
      );
    }

    return Scaffold(
      body: ListView.separated(
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: ranks.length,
        separatorBuilder: (_, __) => const Divider(color: AppTheme.border, height: 1),
        itemBuilder: (context, index) {
          final rank = ranks[index];

          return ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            leading: SizedBox(
              width: 32,
              child: Center(
                child: Text(
                  '${index + 1}',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: index < 3 ? Colors.amber : AppTheme.textSecondary,
                  ),
                ),
              ),
            ),
            title: Row(
              children: [
                Text(
                  rank.base,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                  decoration: BoxDecoration(
                    color: AppTheme.surfaceLight,
                    borderRadius: BorderRadius.circular(3),
                  ),
                  child: Text(
                    rank.exchange.toUpperCase(),
                    style: const TextStyle(fontSize: 9, color: AppTheme.textSecondary),
                  ),
                ),
              ],
            ),
            subtitle: Text(
              '시총: ${Formatting.formatMarketCap(rank.marketCapUsd)}',
              style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
            ),
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '\$${Formatting.formatPrice(rank.priceUsd)}',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
                const SizedBox(height: 2),
                Text(
                  Formatting.formatChange(rank.changeRate),
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: rank.changeRate >= 0 ? AppTheme.upColor : AppTheme.downColor,
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
