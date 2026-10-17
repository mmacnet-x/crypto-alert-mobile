import 'dart:async';
import 'package:flutter/foundation.dart';
import '../alerts/alert_conditions.dart';
import '../alerts/notifier.dart';
import '../exchanges/binance_client.dart';
import '../exchanges/exchange_client.dart';
import '../exchanges/okx_client.dart';
import '../exchanges/upbit_client.dart';
import '../models/alert_event.dart';
import '../models/alert_rule.dart';
import '../models/candle.dart';
import '../models/holding.dart';
import '../models/interval.dart';
import '../models/market_rank.dart';
import '../models/notify_settings.dart';
import '../models/ticker.dart';
import 'storage_service.dart';

class CryptoEngine extends ChangeNotifier {
  final Map<String, ExchangeClient> _clients = {
    'upbit': UpbitClient(),
    'binance': BinanceClient(),
    'okx': OkxClient(),
  };

  Map<String, List<String>> _watchlist = {};
  final Map<String, Ticker> _tickers = {}; // "exchange:symbol" -> Ticker
  List<AlertRule> _rules = [];
  List<AlertEvent> _history = [];
  List<Holding> _holdings = [];
  NotifySettings _notifySettings = NotifySettings();
  Map<String, double> _supplies = {};
  List<MarketRank> _marketRanks = [];

  final AlertNotifier _notifier = AlertNotifier();
  Timer? _candlePollTimer;
  bool _isRunning = false;

  Map<String, List<String>> get watchlist => _watchlist;
  Map<String, Ticker> get tickers => _tickers;
  List<AlertRule> get rules => _rules;
  List<AlertEvent> get history => _history;
  List<Holding> get holdings => _holdings;
  NotifySettings get notifySettings => _notifySettings;
  List<MarketRank> get marketRanks => _marketRanks;

  Ticker? getTicker(String exchange, String symbol) => _tickers['$exchange:$symbol'];

  Future<void> initialize() async {
    await _notifier.initialize();
    _watchlist = await StorageService.loadWatchlist();
    _rules = await StorageService.loadRules();
    _history = await StorageService.loadHistory();
    _holdings = await StorageService.loadHoldings();
    _notifySettings = await StorageService.loadNotifySettings();
    _supplies = await StorageService.loadSupplies();

    await start();
  }

  Future<void> start() async {
    if (_isRunning) return;
    _isRunning = true;

    // 1. 초기 REST 시세 스냅샷 조회
    for (final entry in _watchlist.entries) {
      final exchange = entry.key;
      final symbols = entry.value;
      final client = _clients[exchange];
      if (client != null && symbols.isNotEmpty) {
        try {
          final initialTickers = await client.fetchTickers(symbols);
          for (final t in initialTickers.entries) {
            _tickers['$exchange:${t.key}'] = t.value;
          }
        } catch (_) {}
      }
    }
    _recalculateMarketCap();
    notifyListeners();

    // 2. 실시간 WebSocket 구독
    for (final entry in _watchlist.entries) {
      final exchange = entry.key;
      final symbols = entry.value;
      final client = _clients[exchange];
      if (client != null && symbols.isNotEmpty) {
        client.subscribeTickers(symbols).listen((ticker) {
          _onTickerReceived(exchange, ticker);
        });
      }
    }

    // 3. 지표 알림 조건 평가를 위한 60초 주기 타이머
    _candlePollTimer = Timer.periodic(const Duration(seconds: 60), (_) {
      _evaluateCandleRules();
    });
  }

  void _onTickerReceived(String exchange, Ticker ticker) {
    _tickers['$exchange:${ticker.symbol}'] = ticker;
    _evaluatePriceRules(exchange, ticker);
    _recalculateMarketCap();
    notifyListeners();
  }

  void _evaluatePriceRules(String exchange, Ticker ticker) {
    final now = DateTime.now();
    for (final rule in _rules) {
      if (!rule.enabled) continue;
      if (rule.exchange != exchange || rule.symbol != ticker.symbol) continue;
      if (rule.condition != 'price_above' && rule.condition != 'price_below') continue;

      final eval = AlertConditions.evaluatePrice(rule.condition, ticker.price, rule.params);
      _checkAndDispatch(rule, eval, ticker.price, now);
    }
  }

  Future<void> _evaluateCandleRules() async {
    final now = DateTime.now();
    final candleRules = _rules.where((r) =>
        r.enabled && r.condition != 'price_above' && r.condition != 'price_below');

    for (final rule in candleRules) {
      final client = _clients[rule.exchange];
      if (client == null) continue;

      try {
        final interval = CandleInterval.fromString(rule.interval);
        final candles = await client.fetchCandles(rule.symbol, interval, limit: 100);
        final eval = AlertConditions.evaluateCandles(rule.condition, candles, rule.params);
        final price = candles.isNotEmpty ? candles.last.close : null;
        _checkAndDispatch(rule, eval, price, now);
      } catch (_) {}
    }
  }

  void _checkAndDispatch(AlertRule rule, ConditionEvaluation eval, double? price, DateTime now) {
    // 엣지 감지: false -> true 전환 시점에만 발동
    final isEdge = eval.triggered && !rule.lastState;
    rule.lastState = eval.triggered;

    if (isEdge) {
      final cooldownPassed = rule.lastTriggered == null ||
          now.difference(rule.lastTriggered!).inMinutes >= rule.cooldownMinutes;

      if (cooldownPassed) {
        rule.lastTriggered = now;
        final event = AlertEvent(
          ruleId: rule.id,
          exchange: rule.exchange,
          symbol: rule.symbol,
          interval: rule.interval,
          condition: rule.condition,
          message: eval.message,
          price: price,
          time: now,
        );

        _history.insert(0, event);
        if (_history.length > 100) _history.removeLast();

        _notifier.dispatch(event, _notifySettings);
        StorageService.saveRules(_rules);
        StorageService.saveHistory(_history);
        notifyListeners();
      }
    }
  }

  void _recalculateMarketCap() {
    if (_supplies.isEmpty) return;
    final List<MarketRank> ranks = [];

    // 환율 추정 (업비트 KRW-USDT 또는 기본 1350)
    double usdKrw = 1350.0;
    final usdtUpbit = _tickers['upbit:USDT/KRW'];
    if (usdtUpbit != null && usdtUpbit.price > 0) {
      usdKrw = usdtUpbit.price;
    }

    _supplies.forEach((base, supply) {
      // 1. 바이낸스 USDT 기준가 우선
      double? priceUsd;
      String? sourceExchange;
      String? sourceSymbol;
      double changeRate = 0.0;

      final binanceTicker = _tickers['binance:$base/USDT'];
      if (binanceTicker != null && binanceTicker.price > 0) {
        priceUsd = binanceTicker.price;
        sourceExchange = 'binance';
        sourceSymbol = '$base/USDT';
        changeRate = binanceTicker.changeRate;
      } else {
        // 2. 업비트 KRW 기준가 환산
        final upbitTicker = _tickers['upbit:$base/KRW'];
        if (upbitTicker != null && upbitTicker.price > 0) {
          priceUsd = upbitTicker.price / usdKrw;
          sourceExchange = 'upbit';
          sourceSymbol = '$base/KRW';
          changeRate = upbitTicker.changeRate;
        } else {
          // 3. OKX
          final okxTicker = _tickers['okx:$base/USDT'];
          if (okxTicker != null && okxTicker.price > 0) {
            priceUsd = okxTicker.price;
            sourceExchange = 'okx';
            sourceSymbol = '$base/USDT';
            changeRate = okxTicker.changeRate;
          }
        }
      }

      if (priceUsd != null && sourceExchange != null && sourceSymbol != null) {
        final cap = supply * priceUsd;
        ranks.add(MarketRank(
          base: base,
          symbol: sourceSymbol,
          exchange: sourceExchange,
          priceUsd: priceUsd,
          marketCapUsd: cap,
          changeRate: changeRate,
          supply: supply,
        ));
      }
    });

    ranks.sort((a, b) => b.marketCapUsd.compareTo(a.marketCapUsd));
    _marketRanks = ranks;
  }

  Future<void> addRule(AlertRule rule) async {
    _rules.add(rule);
    await StorageService.saveRules(_rules);
    notifyListeners();
  }

  Future<void> removeRule(String ruleId) async {
    _rules.removeWhere((r) => r.id == ruleId);
    await StorageService.saveRules(_rules);
    notifyListeners();
  }

  Future<void> toggleRule(String ruleId) async {
    final idx = _rules.indexWhere((r) => r.id == ruleId);
    if (idx != -1) {
      _rules[idx].enabled = !_rules[idx].enabled;
      await StorageService.saveRules(_rules);
      notifyListeners();
    }
  }

  Future<void> addHolding(Holding holding) async {
    _holdings.add(holding);
    await StorageService.saveHoldings(_holdings);
    notifyListeners();
  }

  Future<void> removeHolding(int index) async {
    if (index >= 0 && index < _holdings.length) {
      _holdings.removeAt(index);
      await StorageService.saveHoldings(_holdings);
      notifyListeners();
    }
  }

  Future<void> updateNotifySettings(NotifySettings settings) async {
    _notifySettings = settings;
    await StorageService.saveNotifySettings(settings);
    notifyListeners();
  }

  Future<List<Candle>> fetchCandles(String exchange, String symbol, CandleInterval interval) async {
    final client = _clients[exchange];
    if (client == null) throw Exception('거래소 없음: $exchange');
    return client.fetchCandles(symbol, interval, limit: 200);
  }

  @override
  void dispose() {
    _candlePollTimer?.cancel();
    for (final c in _clients.values) {
      c.disconnect();
    }
    super.dispose();
  }
}
