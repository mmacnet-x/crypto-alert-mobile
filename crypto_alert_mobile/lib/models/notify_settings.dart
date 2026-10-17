/// 발송 설정 모델
class NotifySettings {
  bool popupEnabled;
  bool soundEnabled;
  bool telegramEnabled;
  String telegramBotToken;
  String telegramChatId;

  NotifySettings({
    this.popupEnabled = true,
    this.soundEnabled = true,
    this.telegramEnabled = false,
    this.telegramBotToken = '',
    this.telegramChatId = '',
  });

  bool get telegramReady =>
      telegramBotToken.trim().isNotEmpty && telegramChatId.trim().isNotEmpty;

  Map<String, dynamic> toJson() => {
    'popup_enabled': popupEnabled,
    'sound_enabled': soundEnabled,
    'telegram_enabled': telegramEnabled,
    'telegram_bot_token': telegramBotToken,
    'telegram_chat_id': telegramChatId,
  };

  factory NotifySettings.fromJson(Map<String, dynamic> json) => NotifySettings(
    popupEnabled: json['popup_enabled'] as bool? ?? true,
    soundEnabled: json['sound_enabled'] as bool? ?? true,
    telegramEnabled: json['telegram_enabled'] as bool? ?? false,
    telegramBotToken: json['telegram_bot_token'] as String? ?? '',
    telegramChatId: json['telegram_chat_id'] as String? ?? '',
  );
}
