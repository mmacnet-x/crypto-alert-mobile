import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/candle.dart';
import '../models/interval.dart';
import '../models/ticker.dart';
import 'exchange_client.dart';
import 'symbols.dart';

class BinanceClient implements ExchangeClient {
  static const String _baseUrl = 'https://api.binance.com';
  static const String _wsBase = 'wss://stream.binance.com:9443';

  @override
  String get name => 'binance';

  WebSocketChannel? _wsChannel;
  StreamController<Ticker>? _tickerController;

  @override
  Future<List<Candle>> fetchCandles(
    String symbol,
    CandleInterval interval, {
    int limit = 200,
  }) async {
    final bSymbol = Symbols.toBinanceSymbol(symbol);
    final uri = Uri.parse('$_baseUrl/api/v3/klines').replace(queryParameters: {
      'symbol': bSymbol,
      'interval': interval.value,
      'limit': limit.clamp(1, 1000).toString(),
    });

    final response = await http.get(uri);
    if (response.statusCode != 200) {
      throw Exception('바이낸스 캔들 조회 실패: ${response.statusCode}');
    }

    final List data = jsonDecode(response.body);
    final candles = data.map<Candle>((row) {
      return Candle(
        symbol: symbol,
        interval: interval,
        time: DateTime.fromMillisecondsSinceEpoch(row[0] as int, isUtc: true),
        open: double.parse(row[1] as String),
        high: double.parse(row[2] as String),
        low: double.parse(row[3] as String),
        close: double.parse(row[4] as String),
        volume: double.parse(row[5] as String),
      );
    }).toList();

    return candles;
  }

  @override
  Future<Map<String, Ticker>> fetchTickers(List<String> symbols) async {
    final uri = Uri.parse('$_baseUrl/api/v3/ticker/24hr');
    final response = await http.get(uri);
    if (response.statusCode != 200) {
      throw Exception('바이낸스 시세 조회 실패: ${response.statusCode}');
    }

    final List data = jsonDecode(response.body);
    final targetMap = {for (var s in symbols) Symbols.toBinanceSymbol(s): s};
    final result = <String, Ticker>{};

    for (final row in data) {
      final bSym = row['symbol'] as String;
      final standardSym = targetMap[bSym];
      if (standardSym != null) {
        final price = double.parse(row['lastPrice'] as String);
        final changePercent = double.parse(row['priceChangePercent'] as String);
        final volume = double.parse(row['volume'] as String);

        result[standardSym] = Ticker(
          symbol: standardSym,
          price: price,
          changeRate: changePercent / 100.0,
          volume: volume,
          time: DateTime.fromMillisecondsSinceEpoch(row['closeTime'] as int),
        );
      }
    }
    return result;
  }

  @override
  Stream<Ticker> subscribeTickers(List<String> symbols) {
    _tickerController?.close();
    _tickerController = StreamController<Ticker>.broadcast();

    if (symbols.isEmpty) return _tickerController!.stream;

    final streams = symbols
        .map((s) => '${Symbols.toBinanceSymbol(s).toLowerCase()}@ticker')
        .join('/');
    final url = '$_wsBase/stream?streams=$streams';

    _connectWs(url);
    return _tickerController!.stream;
  }

  void _connectWs(String url) {
    try {
      _wsChannel = WebSocketChannel.connect(Uri.parse(url));
      _wsChannel!.stream.listen((message) {
        try {
          final data = jsonDecode(message.toString());
          final payload = data['data'];
          if (payload != null && payload['e'] == '24hrTicker') {
            final standardSym = Symbols.fromBinanceSymbol(payload['s'] as String);
            final ticker = Ticker(
              symbol: standardSym,
              price: double.parse(payload['c'] as String),
              changeRate: double.parse(payload['P'] as String) / 100.0,
              volume: double.parse(payload['v'] as String),
              time: DateTime.fromMillisecondsSinceEpoch(payload['E'] as int),
            );
            _tickerController?.add(ticker);
          }
        } catch (_) {}
      }, onError: (_) {
        Future.delayed(const Duration(seconds: 3), () => _connectWs(url));
      }, onDone: () {
        Future.delayed(const Duration(seconds: 3), () => _connectWs(url));
      });
    } catch (_) {}
  }

  @override
  void disconnect() {
    _wsChannel?.sink.close();
    _tickerController?.close();
  }
}
