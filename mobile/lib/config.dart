/// Where the app finds Afe. Set at build time:
///   flutter run --dart-define=AFE_API_URL=https://api.dev.afe.example --dart-define=AFE_WEB_URL=https://dev.afe.example
/// The defaults reach a local API from the Android emulator (10.0.2.2 is the host machine).
class AppConfig {
  static const apiUrl = String.fromEnvironment('AFE_API_URL', defaultValue: 'http://10.0.2.2:8000');
  static const webUrl = String.fromEnvironment('AFE_WEB_URL', defaultValue: 'http://10.0.2.2:5173');
  static const version = '1.0.0';
}
