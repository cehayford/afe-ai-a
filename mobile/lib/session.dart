import 'package:flutter/widgets.dart';

import 'api/client.dart';
import 'api/models.dart';
import 'api/token_store.dart';

/// Where a sign-in stands after each step.
sealed class SignInStep {}

class SignedIn extends SignInStep {}

/// Staff and listers enter the code from their authenticator app.
class NeedsMfa extends SignInStep {
  NeedsMfa(this.mfaToken);
  final String mfaToken;
}

/// First staff sign-in: add Afe to an authenticator app, then enter its code.
class NeedsMfaSetup extends SignInStep {
  NeedsMfaSetup(this.mfaToken, this.secret, this.otpauthUri);
  final String mfaToken;
  final String secret;
  final String otpauthUri;
}

/// Who is signed in, and the sign-in and sign-out steps. Screens read it through [SessionScope].
class Session extends ChangeNotifier {
  Session(this.api) {
    api.onSignedOut = () {
      me = null;
      notifyListeners();
    };
  }

  final ApiClient api;
  Me? me;
  bool starting = true;

  /// First run: false until the person has been through "Get started" (or signed in some other
  /// way). Kept on the phone, so the welcome shows once per install.
  bool onboarded = false;

  /// The role picked in "Get started" ('renter', 'landlord' or 'verifier'), until the "ready" screen
  /// after sign-up has been seen.
  String? welcomeRole;

  static const onboardedKey = 'afe_onboarded';

  Future<void> start() async {
    try {
      onboarded = await api.tokens.read(onboardedKey) == '1';
      if (await api.hasSession) {
        await reloadMe();
        onboarded = true;
      }
    } on ApiException catch (e) {
      if (e.status == 401) await api.clearSession();
    } finally {
      starting = false;
      notifyListeners();
    }
  }

  Future<void> reloadMe() async {
    me = Me((await api.get<Json>('/me')).data);
    notifyListeners();
  }

  /// Sends a sign-in code by WhatsApp (the default) or SMS. If WhatsApp can't deliver, the API
  /// sends it by SMS instead.
  Future<void> requestCode(String phone, {bool signup = false, String channel = 'whatsapp'}) =>
      api.post('/auth/code', {'phone': phone, 'purpose': signup ? 'signup' : 'login', 'channel': channel});

  Future<SignInStep> signInWithCode(String phone, String code) =>
      _finish(api.post<Json>('/auth/signin/code', {'phone': phone, 'code': code}));

  Future<SignInStep> signInWithPassword(String login, String password) =>
      _finish(api.post<Json>('/auth/signin/password', {'login': login, 'password': password}));

  Future<SignInStep> completeMfa(String mfaToken, String code) =>
      _finish(api.post<Json>('/auth/mfa', {'mfa_token': mfaToken, 'code': code}));

  Future<SignInStep> signUp({required String phone, required String code, required String name, required String role}) =>
      _finish(api.post<Json>('/auth/signup', {
        'phone': phone,
        'code': code,
        'display_name': name,
        'role': role,
        'accept_privacy': true,
      }));

  Future<SignInStep> _finish(Future<ApiResult<Json>> call) async {
    final result = (await call).data;
    switch (result['status']) {
      case 'mfa_required':
        return NeedsMfa('${result['mfa_token']}');
      case 'mfa_setup':
        return NeedsMfaSetup('${result['mfa_token']}', '${result['totp_secret']}', '${result['otpauth_uri']}');
      default:
        await api.saveSession(result);
        await reloadMe();
        // Signed in without picking a role in Get started: nothing more to show, the welcome is done.
        if (welcomeRole == null && !onboarded) await finishOnboarding();
        return SignedIn();
    }
  }

  /// "Get started" is done: the welcome won't show again on this phone.
  Future<void> finishOnboarding() async {
    onboarded = true;
    welcomeRole = null;
    await api.tokens.write(onboardedKey, '1');
    notifyListeners();
  }

  /// The role chosen in "Get started", remembered until sign-up finishes.
  void chooseWelcomeRole(String? role) {
    welcomeRole = role;
    notifyListeners();
  }

  /// Signs this account out on every phone and browser (lost phone, shared computer), this one too.
  Future<int> signOutEverywhere() async {
    final res = await api.post<Json>('/auth/signout/everywhere');
    await api.clearSession();
    me = null;
    notifyListeners();
    return (res.data['devices'] as num?)?.toInt() ?? 0;
  }

  Future<void> signOut() async {
    try {
      final refresh = await api.tokens.read(TokenStore.refresh);
      if (refresh != null) await api.post('/auth/signout', {'refresh_token': refresh});
    } on ApiException {
      // Signed out on this phone either way.
    }
    await api.clearSession();
    me = null;
    notifyListeners();
  }
}

class SessionScope extends InheritedNotifier<Session> {
  const SessionScope({super.key, required Session session, required super.child}) : super(notifier: session);

  static Session of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<SessionScope>()!.notifier!;

  /// For callbacks (button presses) that shouldn't rebuild when the session changes.
  static Session read(BuildContext context) => context.getInheritedWidgetOfExactType<SessionScope>()!.notifier!;
}

extension SessionContext on BuildContext {
  Session get session => SessionScope.read(this);
  ApiClient get api => SessionScope.read(this).api;
}
