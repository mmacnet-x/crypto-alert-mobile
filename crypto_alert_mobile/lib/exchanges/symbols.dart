class Symbols {
  static const List<String> binanceQuotes = [
    'FDUSD',
    'USDT',
    'USDC',
    'BUSD',
    'TUSD',
    'BTC',
    'ETH',
    'BNB',
    'TRY',
  ];

  static String normalizeSymbol(String exchange, String raw) {
    var text = raw.trim().toUpperCase().replaceAll(' ', '');
    if (text.isEmpty) {
      throw ArgumentError('심볼이 비어 있습니다');
    }

    if (exchange == 'upbit') {
      if (text.startsWith('KRW-')) {
        text = text.substring(4);
      }
      if (text.contains('/')) {
        final parts = text.split('/');
        if (parts[1] != 'KRW') {
          throw ArgumentError('업비트는 원화마켓만 지원합니다: $raw');
        }
        return '${parts[0]}/KRW';
      }
      return '$text/KRW';
    }

    if (exchange == 'binance') {
      text = text.replaceAll('-', '/');
      if (text.contains('/')) {
        return text;
      }
      for (final quote in binanceQuotes) {
        if (text.endsWith(quote) && text.length > quote.length) {
          final base = text.substring(0, text.length - quote.length);
          return '$base/$quote';
        }
      }
      throw ArgumentError('바이낸스 심볼을 해석할 수 없습니다: $raw');
    }

    if (exchange == 'okx') {
      text = text.replaceAll('-', '/');
      if (text.contains('/')) {
        return text;
      }
      for (final quote in binanceQuotes) {
        if (text.endsWith(quote) && text.length > quote.length) {
          final base = text.substring(0, text.length - quote.length);
          return '$base/$quote';
        }
      }
      throw ArgumentError('OKX 심볼을 해석할 수 없습니다: $raw');
    }

    throw ArgumentError('알 수 없는 거래소입니다: $exchange');
  }

  static String toUpbitMarket(String symbol) {
    final parts = symbol.split('/');
    if (parts.length != 2) throw ArgumentError('업비트 심볼 형식 오류: $symbol');
    return '${parts[1]}-${parts[0]}';
  }

  static String fromUpbitMarket(String market) {
    final parts = market.split('-');
    if (parts.length != 2) throw ArgumentError('업비트 마켓 코드 오류: $market');
    return '${parts[1]}/${parts[0]}';
  }

  static String toBinanceSymbol(String symbol) {
    final parts = symbol.split('/');
    if (parts.length != 2) throw ArgumentError('바이낸스 심볼 형식 오류: $symbol');
    return '${parts[0]}${parts[1]}';
  }

  static String fromBinanceSymbol(String raw) {
    return normalizeSymbol('binance', raw);
  }

  static String toOkxInstId(String symbol) {
    final parts = symbol.split('/');
    if (parts.length != 2) throw ArgumentError('OKX 심볼 형식 오류: $symbol');
    return '${parts[0]}-${parts[1]}';
  }

  static String fromOkxInstId(String instId) {
    return normalizeSymbol('okx', instId);
  }
}
