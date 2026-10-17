import 'package:intl/intl.dart';

class Formatting {
  static final _numberFormat = NumberFormat('#,##0.00');
  static final _priceSmallFormat = NumberFormat('#,##0.0000');

  static String formatPrice(double price) {
    if (price >= 100) {
      return _numberFormat.format(price);
    }
    if (price >= 1) {
      return _priceSmallFormat.format(price);
    }
    if (price == 0) {
      return '0';
    }
    return price.toStringAsFixed(8).replaceAll(RegExp(r'0+$'), '');
  }

  static String formatChange(double rate) {
    final pct = rate * 100;
    final prefix = pct >= 0 ? '+' : '';
    return '$prefix${pct.toStringAsFixed(2)}%';
  }

  static String formatVolume(double volume) {
    return _numberFormat.format(volume);
  }

  static String formatMarketCap(double valueUsd) {
    if (valueUsd >= 1000000000000) {
      return '\$${(valueUsd / 1000000000000).toStringAsFixed(2)}T';
    }
    if (valueUsd >= 1000000000) {
      return '\$${(valueUsd / 1000000000).toStringAsFixed(2)}B';
    }
    if (valueUsd >= 1000000) {
      return '\$${(valueUsd / 1000000).toStringAsFixed(1)}M';
    }
    return '\$${NumberFormat('#,##0').format(valueUsd)}';
  }
}
