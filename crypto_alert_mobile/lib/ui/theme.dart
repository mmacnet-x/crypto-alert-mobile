import 'package:flutter/material.dart';

class AppTheme {
  static const Color background = Color(0xFF131722);
  static const Color surface = Color(0xFF1E222D);
  static const Color surfaceLight = Color(0xFF2A2E39);
  static const Color border = Color(0xFF363A45);

  static const Color upColor = Color(0xFFC84A31); // 업비트 관행 상승 (빨강)
  static const Color downColor = Color(0xFF1261C4); // 업비트 관행 하락 (파랑)

  static const Color textPrimary = Color(0xFFD1D4DC);
  static const Color textSecondary = Color(0xFF787B86);

  static const Color maShort = Color(0xFFFF9800); // 오렌지
  static const Color maMedium = Color(0xFF2196F3); // 블루
  static const Color maLong = Color(0xFF9C27B0); // 퍼플
  static const Color bollinger = Color(0xFF00BCD4); // 시안

  static ThemeData get darkTheme {
    return ThemeData.dark().copyWith(
      scaffoldBackgroundColor: background,
      primaryColor: const Color(0xFF2962FF),
      colorScheme: const ColorScheme.dark(
        primary: Color(0xFF2962FF),
        surface: surface,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: surface,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: textPrimary,
          fontSize: 17,
          fontWeight: FontWeight.bold,
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: surface,
        selectedItemColor: Color(0xFF2962FF),
        unselectedItemColor: textSecondary,
        type: BottomNavigationBarType.fixed,
      ),
    );
  }
}
