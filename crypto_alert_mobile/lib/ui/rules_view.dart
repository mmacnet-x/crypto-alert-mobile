import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../alerts/alert_conditions.dart';
import '../models/alert_rule.dart';
import '../models/interval.dart';
import '../services/crypto_engine.dart';
import '../utils/formatting.dart';
import 'theme.dart';

class RulesView extends StatefulWidget {
  const RulesView({super.key});

  @override
  State<RulesView> createState() => _RulesViewState();
}

class _RulesViewState extends State<RulesView> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<CryptoEngine>();

    return Scaffold(
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(48),
        child: Container(
          color: AppTheme.surface,
          child: TabBar(
            controller: _tabController,
            indicatorColor: const Color(0xFF2962FF),
            labelColor: Colors.white,
            unselectedLabelColor: AppTheme.textSecondary,
            tabs: [
              Tab(text: '감시 규칙 (${engine.rules.length})'),
              Tab(text: '발동 이력 (${engine.history.length})'),
            ],
          ),
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          // 1. 규칙 목록
          _buildRulesList(engine),
          // 2. 발동 이력
          _buildHistoryList(engine),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: const Color(0xFF2962FF),
        child: const Icon(Icons.add, color: Colors.white),
        onPressed: () => _showAddRuleDialog(context),
      ),
    );
  }

  Widget _buildRulesList(CryptoEngine engine) {
    if (engine.rules.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.notifications_none, size: 48, color: AppTheme.textSecondary),
            const SizedBox(height: 12),
            const Text('등록된 알림 규칙이 없습니다.', style: TextStyle(color: AppTheme.textSecondary)),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: () => _showAddRuleDialog(context),
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF2962FF)),
              child: const Text('새 규칙 추가'),
            ),
          ],
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(12),
      itemCount: engine.rules.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final rule = engine.rules[index];
        final label = AlertConditions.conditionLabels[rule.condition] ?? rule.condition;

        return Card(
          color: AppTheme.surface,
          shape: RoundedRectangleBorder(
            side: BorderSide(color: rule.enabled ? AppTheme.border : Colors.transparent),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppTheme.surfaceLight,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              rule.exchange.toUpperCase(),
                              style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            rule.symbol,
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(width: 6),
                          if (rule.interval.isNotEmpty)
                            Text(
                              '(${rule.interval})',
                              style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        label,
                        style: const TextStyle(fontSize: 13, color: Color(0xFF2962FF), fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        _describeParams(rule),
                        style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                      ),
                      if (rule.lastTriggered != null)
                        Text(
                          '최근 발동: ${rule.lastTriggered!.toLocal().toString().split(".")[0]}',
                          style: const TextStyle(fontSize: 10, color: Colors.amber),
                        ),
                    ],
                  ),
                ),
                Switch(
                  value: rule.enabled,
                  activeColor: const Color(0xFF2962FF),
                  onChanged: (_) => engine.toggleRule(rule.id),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline, size: 20, color: Colors.redAccent),
                  onPressed: () => engine.removeRule(rule.id),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _describeParams(AlertRule rule) {
    if (rule.params.containsKey('target')) {
      return '목표가: ${Formatting.formatPrice((rule.params['target'] as num).toDouble())} (재알림: ${rule.cooldownMinutes}분)';
    }
    if (rule.condition.contains('cross')) {
      return '단기 ${rule.params['fast']} / 장기 ${rule.params['slow']} (재알림: ${rule.cooldownMinutes}분)';
    }
    if (rule.condition.contains('rsi')) {
      return '주기 ${rule.params['period']} / 기준값 ${rule.params['threshold']} (재알림: ${rule.cooldownMinutes}분)';
    }
    return '재알림: ${rule.cooldownMinutes}분';
  }

  Widget _buildHistoryList(CryptoEngine engine) {
    if (engine.history.isEmpty) {
      return const Center(
        child: Text('발동된 알림 이력이 없습니다.', style: TextStyle(color: AppTheme.textSecondary)),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(12),
      itemCount: engine.history.length,
      separatorBuilder: (_, __) => const Divider(color: AppTheme.border, height: 1),
      itemBuilder: (context, index) {
        final event = engine.history[index];
        return ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const CircleAvatar(
            backgroundColor: Color(0xFF2962FF),
            radius: 16,
            child: Icon(Icons.notifications_active, size: 16, color: Colors.white),
          ),
          title: Text(
            '[${event.exchange.toUpperCase()}] ${event.symbol}',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
          ),
          subtitle: Text(event.message, style: const TextStyle(fontSize: 12, color: AppTheme.textPrimary)),
          trailing: Text(
            event.time.toLocal().toString().split(' ')[1].substring(0, 5),
            style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
          ),
        );
      },
    );
  }

  void _showAddRuleDialog(BuildContext context) {
    final engine = context.read<CryptoEngine>();
    String exchange = 'upbit';
    String symbol = 'BTC/KRW';
    String interval = '15m';
    String condition = 'price_above';
    final targetController = TextEditingController(text: '100000000');
    final cooldownController = TextEditingController(text: '30');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            final watchlist = engine.watchlist[exchange] ?? [];
            final isPriceCondition = condition == 'price_above' || condition == 'price_below';

            return Padding(
              padding: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 20,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('새 알림 규칙 등록', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 16),
                    // 거래소 선택
                    DropdownButtonFormField<String>(
                      value: exchange,
                      decoration: const InputDecoration(labelText: '거래소', filled: true, fillColor: AppTheme.surfaceLight),
                      items: const [
                        DropdownMenuItem(value: 'upbit', child: Text('업비트')),
                        DropdownMenuItem(value: 'binance', child: Text('바이낸스')),
                        DropdownMenuItem(value: 'okx', child: Text('OKX')),
                      ],
                      onChanged: (val) {
                        if (val != null) {
                          setModalState(() {
                            exchange = val;
                            final list = engine.watchlist[val] ?? [];
                            symbol = list.isNotEmpty
                                ? (val == 'upbit' ? '${list.first}/KRW' : list.first)
                                : 'BTC/KRW';
                          });
                        }
                      },
                    ),
                    const SizedBox(height: 12),
                    // 종목 선택
                    DropdownButtonFormField<String>(
                      value: watchlist.contains(symbol) || watchlist.contains(symbol.split('/')[0])
                          ? symbol
                          : (watchlist.isNotEmpty ? (exchange == 'upbit' ? '${watchlist.first}/KRW' : watchlist.first) : null),
                      decoration: const InputDecoration(labelText: '감시 종목', filled: true, fillColor: AppTheme.surfaceLight),
                      items: watchlist.map((s) {
                        final sym = exchange == 'upbit' ? (s.contains('/') ? s : '$s/KRW') : s;
                        return DropdownMenuItem(value: sym, child: Text(sym));
                      }).toList(),
                      onChanged: (val) {
                        if (val != null) setModalState(() => symbol = val);
                      },
                    ),
                    const SizedBox(height: 12),
                    // 조건 선택
                    DropdownButtonFormField<String>(
                      value: condition,
                      decoration: const InputDecoration(labelText: '알림 조건', filled: true, fillColor: AppTheme.surfaceLight),
                      items: AlertConditions.conditionLabels.entries.map((e) {
                        return DropdownMenuItem(value: e.key, child: Text(e.value, style: const TextStyle(fontSize: 13)));
                      }).toList(),
                      onChanged: (val) {
                        if (val != null) setModalState(() => condition = val);
                      },
                    ),
                    const SizedBox(height: 12),
                    // 캔들 주기 (지표 조건일 때)
                    if (!isPriceCondition) ...[
                      DropdownButtonFormField<String>(
                        value: interval,
                        decoration: const InputDecoration(labelText: '캔들 주기', filled: true, fillColor: AppTheme.surfaceLight),
                        items: CandleInterval.values.map((i) {
                          return DropdownMenuItem(value: i.value, child: Text(i.label));
                        }).toList(),
                        onChanged: (val) {
                          if (val != null) setModalState(() => interval = val);
                        },
                      ),
                      const SizedBox(height: 12),
                    ],
                    // 가격 조건 입력칸
                    if (isPriceCondition) ...[
                      TextField(
                        controller: targetController,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(
                          labelText: '목표 가격',
                          filled: true,
                          fillColor: AppTheme.surfaceLight,
                        ),
                      ),
                      const SizedBox(height: 12),
                    ],
                    // 쿨다운 입력칸
                    TextField(
                      controller: cooldownController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: '재알림 방지 쿨다운 (분)',
                        filled: true,
                        fillColor: AppTheme.surfaceLight,
                      ),
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF2962FF)),
                        onPressed: () {
                          final params = <String, dynamic>{};
                          if (isPriceCondition) {
                            params['target'] = double.tryParse(targetController.text) ?? 0.0;
                          } else if (condition.contains('cross')) {
                            params['fast'] = 5;
                            params['slow'] = 20;
                          } else if (condition.contains('rsi')) {
                            params['period'] = 14;
                            params['threshold'] = condition == 'rsi_overbought' ? 70.0 : 30.0;
                          } else if (condition.contains('macd')) {
                            params['fast'] = 12;
                            params['slow'] = 26;
                            params['signal'] = 9;
                          } else if (condition.contains('bb')) {
                            params['period'] = 20;
                            params['mult'] = 2.0;
                          }

                          final newRule = AlertRule(
                            id: DateTime.now().millisecondsSinceEpoch.toString(),
                            exchange: exchange,
                            symbol: symbol,
                            interval: interval,
                            condition: condition,
                            params: params,
                            cooldownMinutes: int.tryParse(cooldownController.text) ?? 30,
                          );

                          engine.addRule(newRule);
                          Navigator.pop(context);
                        },
                        child: const Text('규칙 저장', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}
