import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import '../models/alert_event.dart';
import '../models/notify_settings.dart';

class AlertNotifier {
  static final AlertNotifier _instance = AlertNotifier._internal();
  factory AlertNotifier() => _instance;
  AlertNotifier._internal();

  final FlutterLocalNotificationsPlugin _notificationsPlugin =
      FlutterLocalNotificationsPlugin();
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) return;

    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const initSettings = InitializationSettings(android: androidSettings);

    await _notificationsPlugin.initialize(initSettings);
    _initialized = true;
  }

  Future<List<String>> dispatch(AlertEvent event, NotifySettings settings) async {
    final used = <String>[];

    if (settings.popupEnabled) {
      await _showLocalNotification(event);
      used.add('popup');
    }

    if (settings.telegramEnabled && settings.telegramReady) {
      await _sendTelegram(event, settings);
      used.add('telegram');
    }

    return used;
  }

  Future<void> _showLocalNotification(AlertEvent event) async {
    try {
      const androidDetails = AndroidNotificationDetails(
        'crypto_alert_channel',
        '코인 시세 알림',
        channelDescription: '가격 돌파 및 보조지표 신호 알림',
        importance: Importance.max,
        priority: Priority.high,
        ticker: 'crypto-alert',
        playSound: true,
        enableVibration: true,
      );
      const details = NotificationDetails(android: androidDetails);

      await _notificationsPlugin.show(
        DateTime.now().millisecondsSinceEpoch ~/ 1000,
        '[crypto-alert] ${event.symbol} 알림',
        event.message,
        details,
      );
    } catch (e) {
      debugPrint('로컬 알림 발송 실패: $e');
    }
  }

  Future<bool> _sendTelegram(AlertEvent event, NotifySettings settings) async {
    try {
      final token = settings.telegramBotToken.trim();
      final chatId = settings.telegramChatId.trim();
      final url = Uri.parse('https://api.telegram.org/bot$token/sendMessage');

      final text = '[crypto-alert] [${event.exchange.toUpperCase()}] ${event.symbol}\n'
          '${event.message}\n'
          '시각: ${event.time.toLocal().toString().split(".")[0]}';

      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'chat_id': chatId,
          'text': text,
        }),
      );

      return response.statusCode == 200;
    } catch (e) {
      debugPrint('텔레그램 발송 실패: $e');
      return false;
    }
  }

  Future<bool> testTelegram(String token, String chatId) async {
    try {
      final url = Uri.parse('https://api.telegram.org/bot$token/sendMessage');
      final text = '[crypto-alert] 테스트 발송 성공!\n현재 시각: ${DateTime.now()}';

      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'chat_id': chatId,
          'text': text,
        }),
      );

      return response.statusCode == 200;
    } catch (e) {
      debugPrint('텔레그램 테스트 실패: $e');
      return false;
    }
  }
}
