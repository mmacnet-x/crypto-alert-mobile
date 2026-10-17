import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/candle.dart';
import '../models/interval.dart';
import '../models/ticker.dart';
import 'exchange_client.dart';
import 'symbols.dart';

class OkxClient implements ExchangeClient {
  static const String _baseUrl = 'https://www.okx.com';
  static const String _wsUrl = 'wss://ws.okx.com:8443/ws/v5/public';

  @override
  String get name => 'okx';

  WebSocketChannel? _wsChannel;
  StreamController<Ticker>? _tickerController;

  static const Map<CandleInterval, String> _bars = {
    CandleInterval.m15: '15m',
    CandleInterval.h4: '4H',
    CandleInterval.d1: '1D',
    CandleInterval.w1: '1W',
    CandleInterval.mn: '1M',
  };

  @override
  Future<List<Candle>> fetchCandles(
    String symbol,
    CandleInterval interval, {
    int limit = 200,
  }) async {
    final instId = Symbols.toOkxInstId(symbol);
    final bar = _bars[interval] ?? '15m';

    final uri = Uri.parse('$_baseUrl/api/v5/market/candles').replace(queryParameters: {
      'instId': instId,
      'bar': bar,
      'limit': '100',
    });

    final response = await http.get(uri);
    if (response.statusCode != 200) {
      throw Exception('OKX 캔들 조회 실패: ${response.statusCode}');
    }

    final data = jsonDecode(response.body);
    if (data['code'] != '0') {
      throw Exception('OKX 에러: ${data['msg']}');
    }

    final List list = data['data'];
    final candles = list.map<Candle>((row) {
      return Candle(
        symbol: symbol,
        interval: interval,
        time: DateTime.fromMillisecondsSinceEpoch(int.parse(row[0] as String), isUtc: true),
        open: double.parse(row[1] as String),
        high: double.parse(row[2] as String),
        low: double.parse(row[3] as String),
        close: double.parse(row[4] as String),
        volume: double.parse(row[5] as String),
      );
    }).toList();

    // OKX는 최신순으로 반환하므로 과거순으로 정렬
    candles.sort((a, b) => a.time.compareTo(b.time));
    return candles;
  }

  @override
  Future<Map<String, Ticker>> fetchTickers(List<String> symbols) async {
    if (symbols.isEmpty) return {};
    final result = <String, Ticker>{};

    for (final sym in symbols) {
      final instId = Symbols.toOkxInstId(sym);
      final uri = Uri.parse('$_baseUrl/api/v5/market/ticker?instId=$instId');
      final response = await http.get(uri);
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['code'] == '0' && (data['data'] as List).isNotEmpty) {
          final row = data['data'][0];
          final price = double.parse(row['last'] as String);
          final open24 = double.parse(row['open24h'] as String);
          final changeRate = open24 > 0 ? (price - open24) / open24 : 0.0;
          result[sym] = Ticker(
            symbol: sym,
            price: price,
            changeRate: changeRate,
            volume: double.parse(row['vol24h'] as String),
            time: DateTime.fromMillisecondsSinceEpoch(int.parse(row['ts'] as String)),
          );
        }
      }
    }
    return result;
  }

  @override
  Stream<Ticker> subscribeTickers(List<String> symbols) {
    _tickerController?.close();
    _tickerController = StreamController<Ticker>.broadcast();

    if (symbols.isEmpty) return _tickerController!.stream;

    final args = symbols
        .map((s) => {'channel': 'tickers', 'instId': Symbols.toOkxInstId(s)})
        .toList();

    _connectWs(args);
    return _tickerController!.stream;
  }

  void _connectWs(List<Map<String, String>> args) {
    try {
      _wsChannel = WebSocketChannel.connect(Uri.parse(_wsUrl));
      final subMsg = jsonEncode({
        'op': 'subscribe',
        'args': args,
      });
      _wsChannel!.sink.add(subMsg);

      _wsChannel!.stream.listen((message) {
        try {
          final data = jsonDecode(message.toString());
          if (data['arg'] != null && data['data'] != null) {
            final row = data['data'][0];
            final sym = Symbols.fromOkxInstId(row['instId'] as String);
            final price = double.parse(row['last'] as String);
            final open24 = double.parse(row['open24h'] as String);
            final changeRate = open24 > 0 ? (price - open24) / open24 : 0.0;
            final ticker = Ticker(
              symbol: sym,
              price: price,
              changeRate: changeRate,
              volume: double.parse(row['vol24h'] as String),
              time: DateTime.fromMillisecondsSinceEpoch(int.parse(row['ts'] as String)),
            );
            _tickerController?.add(ticker);
          }
        } catch (_) {}
      }, onError: (_) {
        Future.delayed(const Duration(seconds: 3), () => _connectWs(args));
      }, onDone: () {
        Future.delayed(const Duration(seconds: 3), () => _connectWs(args));
      });
    } catch (_) {}
  }

  @override
  void disconnect() {
    _wsChannel?.sink.close();
    _tickerController?.close();
  }
}
