import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/alert_event.dart';
import '../models/alert_rule.dart';
import '../models/holding.dart';
import '../models/notify_settings.dart';

class StorageService {
  static const String _keyRules = 'crypto_alert_rules';
  static const String _keyHoldings = 'crypto_alert_holdings';
  static const String _keyNotify = 'crypto_alert_notify_settings';
  static const String _keyHistory = 'crypto_alert_history';
  static const String _keyWatchlist = 'crypto_alert_watchlist';

  static Future<Map<String, List<String>>> loadWatchlist() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_keyWatchlist);
    if (jsonStr != null) {
      final map = jsonDecode(jsonStr) as Map<String, dynamic>;
      return map.map((k, v) => MapEntry(k, List<String>.from(v as List)));
    }

    try {
      final assetStr = await rootBundle.loadString('assets/watchlist.json');
      final map = jsonDecode(assetStr) as Map<String, dynamic>;
      return map.map((k, v) => MapEntry(k, List<String>.from(v as List)));
    } catch (_) {
      return {
        'upbit': ['BTC', 'ETH', 'XRP', 'SOL', 'DOGE'],
        'binance': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
        'okx': ['PI/USDT'],
      };
    }
  }

  static Future<void> saveWatchlist(Map<String, List<String>> watchlist) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyWatchlist, jsonEncode(watchlist));
  }

  static Future<Map<String, double>> loadSupplies() async {
    try {
      final assetStr = await rootBundle.loadString('assets/supplies.json');
      final map = jsonDecode(assetStr) as Map<String, dynamic>;
      final result = <String, double>{};
      map.forEach((k, v) {
        if (!k.startsWith('_') && v is num && v > 0) {
          result[k.toUpperCase()] = v.toDouble();
        }
      });
      return result;
    } catch (_) {
      return {};
    }
  }

  static Future<List<AlertRule>> loadRules() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_keyRules);
    if (jsonStr == null) return [];
    try {
      final list = jsonDecode(jsonStr) as List;
      return list.map((item) => AlertRule.fromJson(item as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> saveRules(List<AlertRule> rules) async {
    final prefs = await SharedPreferences.getInstance();
    final list = rules.map((r) => r.toJson()).toList();
    await prefs.setString(_keyRules, jsonEncode(list));
  }

  static Future<List<Holding>> loadHoldings() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_keyHoldings);
    if (jsonStr == null) return [];
    try {
      final list = jsonDecode(jsonStr) as List;
      return list.map((item) => Holding.fromJson(item as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> saveHoldings(List<Holding> holdings) async {
    final prefs = await SharedPreferences.getInstance();
    final list = holdings.map((h) => h.toJson()).toList();
    await prefs.setString(_keyHoldings, jsonEncode(list));
  }

  static Future<NotifySettings> loadNotifySettings() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_keyNotify);
    if (jsonStr == null) return NotifySettings();
    try {
      return NotifySettings.fromJson(jsonDecode(jsonStr) as Map<String, dynamic>);
    } catch (_) {
      return NotifySettings();
    }
  }

  static Future<void> saveNotifySettings(NotifySettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyNotify, jsonEncode(settings.toJson()));
  }

  static Future<List<AlertEvent>> loadHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_keyHistory);
    if (jsonStr == null) return [];
    try {
      final list = jsonDecode(jsonStr) as List;
      return list.map((item) => AlertEvent.fromJson(item as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> saveHistory(List<AlertEvent> history) async {
    final prefs = await SharedPreferences.getInstance();
    final list = history.take(100).map((e) => e.toJson()).toList();
    await prefs.setString(_keyHistory, jsonEncode(list));
  }
}
