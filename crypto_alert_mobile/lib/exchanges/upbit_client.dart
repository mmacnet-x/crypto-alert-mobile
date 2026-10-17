import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/candle.dart';
import '../models/interval.dart';
import '../models/ticker.dart';
import 'exchange_client.dart';
import 'symbols.dart';

class UpbitClient implements ExchangeClient {
  static const String _baseUrl = 'https://api.upbit.com';
  static const String _wsUrl = 'wss://api.upbit.com/websocket/v1';

  @override
  String get name => 'upbit';

  WebSocketChannel? _wsChannel;
  StreamController<Ticker>? _tickerController;

  @override
  Future<List<Candle>> fetchCandles(
    String symbol,
    CandleInterval interval, {
    int limit = 200,
  }) async {
    final market = Symbols.toUpbitMarket(symbol);
    String path;
    final queryParams = <String, String>{
      'market': market,
      'count': limit.clamp(1, 200).toString(),
    };

    switch (interval) {
      case CandleInterval.m15:
        path = '/v1/candles/minutes/15';
        break;
      case CandleInterval.h4:
        path = '/v1/candles/minutes/240';
        break;
      case CandleInterval.d1:
        path = '/v1/candles/days';
        queryParams['unit'] = '1';
        break;
      case CandleInterval.w1:
        path = '/v1/candles/days';
        queryParams['unit'] = '7';
        break;
      case CandleInterval.mn:
        path = '/v1/candles/days';
        queryParams['unit'] = '30';
        break;
    }

    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: queryParams);
    final response = await http.get(uri);

    if (response.statusCode != 200) {
      throw Exception('업비트 캔들 조회 실패: ${response.statusCode} ${response.body}');
    }

    final List data = jsonDecode(response.body);
    final candles = data.map<Candle>((row) {
      return Candle(
        symbol: symbol,
        interval: interval,
        time: DateTime.parse(row['candle_date_time_utc'] as String),
        open: (row['opening_price'] as num).toDouble(),
        high: (row['high_price'] as num).toDouble(),
        low: (row['low_price'] as num).toDouble(),
        close: (row['trade_price'] as num).toDouble(),
        volume: (row['candle_acc_trade_volume'] as num).toDouble(),
      );
    }).toList();

    // 과거 -> 최신 순 정렬
    candles.sort((a, b) => a.time.compareTo(b.time));
    return candles;
  }

  @override
  Future<Map<String, Ticker>> fetchTickers(List<String> symbols) async {
    if (symbols.isEmpty) return {};
    final markets = symbols.map(Symbols.toUpbitMarket).join(',');
    final uri = Uri.parse('$_baseUrl/v1/ticker?markets=$markets');
    final response = await http.get(uri);

    if (response.statusCode != 200) {
      throw Exception('업비트 시세 조회 실패: ${response.statusCode}');
    }

    final List data = jsonDecode(response.body);
    final result = <String, Ticker>{};

    for (final row in data) {
      final sym = Symbols.fromUpbitMarket(row['market'] as String);
      result[sym] = Ticker(
        symbol: sym,
        price: (row['trade_price'] as num).toDouble(),
        changeRate: (row['change_rate'] as num).toDouble(),
        volume: (row['acc_trade_volume'] as num).toDouble(),
        time: DateTime.fromMillisecondsSinceEpoch(row['timestamp'] as int),
      );
    }
    return result;
  }

  @override
  Stream<Ticker> subscribeTickers(List<String> symbols) {
    _tickerController?.close();
    _tickerController = StreamController<Ticker>.broadcast();

    if (symbols.isEmpty) return _tickerController!.stream;

    final markets = symbols.map(Symbols.toUpbitMarket).toList();
    _connectWs(markets);
    return _tickerController!.stream;
  }

  void _connectWs(List<String> markets) {
    try {
      _wsChannel = WebSocketChannel.connect(Uri.parse(_wsUrl));
      final subMsg = jsonEncode([
        {'ticket': 'crypto-alert-mobile'},
        {'type': 'ticker', 'codes': markets},
        {'format': 'DEFAULT'}
      ]);
      _wsChannel!.sink.add(subMsg);

      _wsChannel!.stream.listen((message) {
        try {
          final String text = message is List<int> ? utf8.decode(message) : message.toString();
          final data = jsonDecode(text);
          if (data['type'] == 'ticker') {
            final sym = Symbols.fromUpbitMarket(data['code'] as String);
            final ticker = Ticker(
              symbol: sym,
              price: (data['trade_price'] as num).toDouble(),
              changeRate: (data['change_rate'] as num).toDouble(),
              volume: (data['acc_trade_volume_24h'] as num?)?.toDouble() ??
                  (data['acc_trade_volume'] as num).toDouble(),
              time: DateTime.fromMillisecondsSinceEpoch(data['timestamp'] as int),
            );
            _tickerController?.add(ticker);
          }
        } catch (_) {}
      }, onError: (e) {
        Future.delayed(const Duration(seconds: 3), () => _connectWs(markets));
      }, onDone: () {
        Future.delayed(const Duration(seconds: 3), () => _connectWs(markets));
      });
    } catch (_) {}
  }

  @override
  void disconnect() {
    _wsChannel?.sink.close();
    _tickerController?.close();
  }
}
