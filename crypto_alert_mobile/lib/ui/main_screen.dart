import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import '../services/foreground_service.dart';
import 'chart_view.dart';
import 'holdings_view.dart';
import 'market_cap_view.dart';
import 'rules_view.dart';
import 'settings_dialog.dart';
import 'theme.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;
  bool _isServiceRunning = false;

  final List<Widget> _screens = const [
    ChartView(),
    RulesView(),
    HoldingsView(),
    MarketCapView(),
  ];

  @override
  void initState() {
    super.initState();
    _checkServiceStatus();
  }

  Future<void> _checkServiceStatus() async {
    final running = await FlutterForegroundTask.isRunningService;
    if (mounted) {
      setState(() => _isServiceRunning = running);
    }
  }

  Future<void> _toggleForegroundService() async {
    if (_isServiceRunning) {
      await ForegroundServiceHelper.stopService();
      setState(() => _isServiceRunning = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('24시간 백그라운드 감시가 중지되었습니다.')),
        );
      }
    } else {
      await ForegroundServiceHelper.startService();
      setState(() => _isServiceRunning = true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('24시간 백그라운드 감시가 시작되었습니다. (상단바 알림 등록)'),
            backgroundColor: Color(0xFF2962FF),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.candlestick_chart, color: Color(0xFF2962FF), size: 22),
            const SizedBox(width: 8),
            const Text('crypto-alert'),
            const SizedBox(width: 8),
            // 백그라운드 서비스 활성 뱃지
            GestureDetector(
              onTap: _toggleForegroundService,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: _isServiceRunning ? Colors.green.withOpacity(0.2) : Colors.grey.withOpacity(0.2),
                  border: Border.all(color: _isServiceRunning ? Colors.green : Colors.grey),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircleAvatar(
                      radius: 3,
                      backgroundColor: _isServiceRunning ? Colors.green : Colors.grey,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _isServiceRunning ? '24h 감시중' : '백그라운드 OFF',
                      style: TextStyle(
                        fontSize: 10,
                        color: _isServiceRunning ? Colors.green : Colors.grey,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: '알림 설정',
            onPressed: () {
              showDialog(
                context: context,
                builder: (_) => const SettingsDialog(),
              );
            },
          ),
        ],
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) => setState(() => _currentIndex = index),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.show_chart),
            label: '차트·시세',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.notifications_active_outlined),
            label: '알림 규칙',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.account_balance_wallet_outlined),
            label: '보유종목',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.leaderboard_outlined),
            label: '시총 순위',
          ),
        ],
      ),
    );
  }
}
