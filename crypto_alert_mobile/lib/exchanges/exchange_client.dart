import '../models/candle.dart';
import '../models/interval.dart';
import '../models/ticker.dart';

abstract class ExchangeClient {
  String get name;

  Future<List<Candle>> fetchCandles(
    String symbol,
    CandleInterval interval, {
    int limit = 200,
  });

  Future<Map<String, Ticker>> fetchTickers(List<String> symbols);

  Stream<Ticker> subscribeTickers(List<String> symbols);

  void disconnect();
}
