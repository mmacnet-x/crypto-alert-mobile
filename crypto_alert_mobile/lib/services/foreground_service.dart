import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

@pragma('vm:entry-point')
void startCallback() {
  FlutterForegroundTask.setTaskHandler(CryptoAlertTaskHandler());
}

class CryptoAlertTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    debugPrint('Foreground Service 시작됨: $timestamp');
  }

  @override
  void onRepeatEvent(DateTime timestamp) {
    // 24시간 백그라운드 유지 및 주기적 체크
    FlutterForegroundTask.updateService(
      notificationTitle: 'crypto-alert 감시 중',
      notificationText: '업비트·바이낸스·OKX 실시간 시세 수신 중 (${timestamp.hour}:${timestamp.minute.toString().padLeft(2, '0')})',
    );
  }

  @override
  Future<void> onDestroy(DateTime timestamp) async {
    debugPrint('Foreground Service 종료됨');
  }

  @override
  void onReceiveData(Object data) {}

  @override
  void onNotificationButtonPressed(String id) {}

  @override
  void onNotificationPressed() {
    FlutterForegroundTask.launchApp('/');
  }

  @override
  void onNotificationDismissed() {}
}

class ForegroundServiceHelper {
  static void init() {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'crypto_alert_foreground',
        channelName: 'crypto-alert 24시간 상시 감시',
        channelDescription: '백그라운드에서 실시간 시세 및 알림 조건을 지속 감시합니다.',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
        iconData: const NotificationIconData(
          resType: ResourceType.mipmap,
          resPrefix: ResourcePrefix.ic,
          name: 'launcher',
        ),
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: true,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(60000), // 1분 주기 갱신
        autoRunOnBoot: true,
        autoRunOnMyPackageReplaced: true,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  static Future<bool> startService() async {
    if (await FlutterForegroundTask.isRunningService) {
      return true;
    }
    return FlutterForegroundTask.startService(
      serviceId: 256,
      notificationTitle: 'crypto-alert 감시 시작',
      notificationText: '실시간 시세 스트림 연결 중...',
      callback: startCallback,
    );
  }

  static Future<bool> stopService() async {
    return FlutterForegroundTask.stopService();
  }
}
