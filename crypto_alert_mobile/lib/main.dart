import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'services/crypto_engine.dart';
import 'services/foreground_service.dart';
import 'ui/main_screen.dart';
import 'ui/theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  ForegroundServiceHelper.init();

  final cryptoEngine = CryptoEngine();
  await cryptoEngine.initialize();

  runApp(
    ChangeNotifierProvider.value(
      value: cryptoEngine,
      child: const CryptoAlertApp(),
    ),
  );
}

class CryptoAlertApp extends StatelessWidget {
  const CryptoAlertApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'crypto-alert',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      home: const MainScreen(),
    );
  }
}
