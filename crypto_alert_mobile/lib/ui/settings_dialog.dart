import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../alerts/notifier.dart';
import '../models/notify_settings.dart';
import '../services/crypto_engine.dart';
import 'theme.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key});

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late TextEditingController _tokenController;
  late TextEditingController _chatIdController;
  late bool _popupEnabled;
  late bool _soundEnabled;
  late bool _telegramEnabled;
  bool _isTesting = false;

  @override
  void initState() {
    super.initState();
    final settings = context.read<CryptoEngine>().notifySettings;
    _tokenController = TextEditingController(text: settings.telegramBotToken);
    _chatIdController = TextEditingController(text: settings.telegramChatId);
    _popupEnabled = settings.popupEnabled;
    _soundEnabled = settings.soundEnabled;
    _telegramEnabled = settings.telegramEnabled;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppTheme.surface,
      title: const Text('알림 발송 설정', style: TextStyle(fontWeight: FontWeight.bold)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('로컬 푸시 알림'),
              subtitle: const Text('스마트폰 화면 상단 알림바 팝업', style: TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
              value: _popupEnabled,
              activeColor: const Color(0xFF2962FF),
              onChanged: (val) => setState(() => _popupEnabled = val),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('알림 사운드 / 진동'),
              value: _soundEnabled,
              activeColor: const Color(0xFF2962FF),
              onChanged: (val) => setState(() => _soundEnabled = val),
            ),
            const Divider(color: AppTheme.border),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('텔레그램 알림'),
              subtitle: const Text('텔레그램 봇으로 실시간 메시지 발송', style: TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
              value: _telegramEnabled,
              activeColor: const Color(0xFF2962FF),
              onChanged: (val) => setState(() => _telegramEnabled = val),
            ),
            if (_telegramEnabled) ...[
              const SizedBox(height: 8),
              TextField(
                controller: _tokenController,
                decoration: const InputDecoration(
                  labelText: '텔레그램 봇 토큰',
                  hintText: '123456789:ABCdef...',
                  filled: true,
                  fillColor: AppTheme.surfaceLight,
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _chatIdController,
                decoration: const InputDecoration(
                  labelText: '텔레그램 Chat ID',
                  hintText: '12345678',
                  filled: true,
                  fillColor: AppTheme.surfaceLight,
                ),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  icon: _isTesting
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.send, size: 16),
                  label: const Text('텔레그램 테스트 발송'),
                  onPressed: _isTesting ? null : _testTelegram,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소', style: TextStyle(color: AppTheme.textSecondary)),
        ),
        ElevatedButton(
          style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF2962FF)),
          onPressed: _saveSettings,
          child: const Text('저장'),
        ),
      ],
    );
  }

  Future<void> _testTelegram() async {
    final token = _tokenController.text.trim();
    final chatId = _chatIdController.text.trim();

    if (token.isEmpty || chatId.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('봇 토큰과 Chat ID를 모두 입력해주세요.')),
      );
      return;
    }

    setState(() => _isTesting = true);
    final success = await AlertNotifier().testTelegram(token, chatId);
    if (mounted) {
      setState(() => _isTesting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(success ? '텔레그램 테스트 발송에 성공했습니다!' : '텔레그램 발송 실패 (토큰/Chat ID를 확인하세요)'),
          backgroundColor: success ? Colors.green : Colors.redAccent,
        ),
      );
    }
  }

  void _saveSettings() {
    final engine = context.read<CryptoEngine>();
    final newSettings = NotifySettings(
      popupEnabled: _popupEnabled,
      soundEnabled: _soundEnabled,
      telegramEnabled: _telegramEnabled,
      telegramBotToken: _tokenController.text.trim(),
      telegramChatId: _chatIdController.text.trim(),
    );
    engine.updateNotifySettings(newSettings);
    Navigator.pop(context);
  }
}
