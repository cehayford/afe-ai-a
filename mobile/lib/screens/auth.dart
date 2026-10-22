import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../config.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';

Future<void> openWeb(String path) => launchUrl(Uri.parse('${AppConfig.webUrl}$path'), mode: LaunchMode.externalApplication);

/// After any sign-in step: go back to the app's first screen (which now shows the signed-in
/// app), or on to the authenticator step.
Future<void> _next(BuildContext context, SignInStep step) async {
  if (!context.mounted) return;
  switch (step) {
    case SignedIn():
      Navigator.of(context).popUntil((r) => r.isFirst);
    case NeedsMfa(:final mfaToken):
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => MfaScreen(mfaToken: mfaToken)));
    case NeedsMfaSetup(:final mfaToken, :final secret, :final otpauthUri):
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => MfaScreen(mfaToken: mfaToken, setupSecret: secret, otpauthUri: otpauthUri),
        ),
      );
  }
}

/// The sign-in screens from the App Screen canvas: a big title, a muted line, then the fields.
class _Form extends StatelessWidget {
  const _Form({required this.title, required this.children, this.lede, this.bar = 'Sign in'});
  final String title;
  final String? lede;
  final String bar;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AfeAppBar(title: Text(bar), avatar: false),
    body: SafeArea(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
        children: [
          ScreenTitle(title, lede: lede, size: 28),
          const SizedBox(height: 18),
          ...children,
        ],
      ),
    ),
  );
}

const _gap = SizedBox(height: 14);

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text(text, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
  );
}

final _ghanaMobile = RegExp(r'^\+233\d{9}$');
const _badNumber = 'Enter a 9-digit Ghana number, without the leading 0.';

/// The code step shared by sign-in and sign-up: six boxes, Verify, and a resend link that waits
/// 30 seconds between codes.
class _CodeStep extends StatefulWidget {
  const _CodeStep({
    required this.phone,
    required this.channel,
    required this.code,
    required this.busy,
    required this.onVerify,
    required this.onResend,
    required this.onBack,
    this.error,
  });
  final String phone;
  final String channel;
  final TextEditingController code;
  final bool busy;
  final String? error;
  final VoidCallback onVerify;
  final Future<void> Function() onResend;
  final VoidCallback onBack;

  @override
  State<_CodeStep> createState() => _CodeStepState();
}

class _CodeStepState extends State<_CodeStep> {
  int _wait = 30;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _start();
  }

  void _start() {
    _timer?.cancel();
    setState(() => _wait = 30);
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => _wait--);
      if (_wait <= 0) t.cancel();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final digits = widget.phone.replaceFirst('+233', '');
    final shown = digits.length == 9 ? '${digits.substring(0, 2)} ${digits.substring(2, 5)} ${digits.substring(5)}' : digits;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Sent by ${widget.channel == 'sms' ? 'SMS' : 'WhatsApp'} to +233 $shown. Afe staff will never ask for it.',
          style: TextStyle(color: a.muted, fontSize: 15, height: 1.45),
        ),
        const SizedBox(height: 18),
        if (widget.error != null) ...[Note(widget.error!, kind: NoteKind.error), _gap],
        CodeBoxes(controller: widget.code, error: widget.error != null, onCompleted: widget.onVerify),
        const SizedBox(height: 18),
        PrimaryButton(label: 'Verify', busy: widget.busy, onPressed: widget.onVerify),
        const SizedBox(height: 8),
        Row(
          children: [
            Text("Didn't get it?", style: TextStyle(color: a.muted, fontSize: 14)),
            const Spacer(),
            TextButton(
              onPressed: _wait > 0
                  ? null
                  : () async {
                      await widget.onResend();
                      if (mounted) _start();
                    },
              child: Text(_wait > 0 ? 'Resend in ${_wait}s' : 'Resend code'),
            ),
          ],
        ),
        TextButton(onPressed: widget.onBack, child: const Text('Use a different number')),
        const SizedBox(height: 8),
        const Note('Afe staff will never ask you for this code.', kind: NoteKind.warn, lead: 'Keep it private.'),
      ],
    );
  }
}

/// Renters, landlords and agents sign in with a one-time code by WhatsApp or SMS.
class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key});

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  String? _sentTo;
  String _channel = 'whatsapp';
  bool _busy = false;
  String? _error;

  Future<void> _run(Future<void> Function() f) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await f();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send(String channel) => _run(() async {
    final phone = phoneE164(_phone.text);
    if (!_ghanaMobile.hasMatch(phone)) {
      setState(() => _error = _badNumber);
      return;
    }
    await context.session.requestCode(phone, channel: channel);
    _code.clear();
    setState(() {
      _sentTo = phone;
      _channel = channel;
    });
  });

  @override
  Widget build(BuildContext context) {
    final sent = _sentTo;
    if (sent != null) {
      return _Form(
        title: 'Enter your code',
        children: [
          _CodeStep(
            phone: sent,
            channel: _channel,
            code: _code,
            busy: _busy,
            error: _error,
            onVerify: () => _run(() async {
              final step = await context.session.signInWithCode(sent, _code.text);
              if (context.mounted) await _next(context, step);
            }),
            onResend: () => _send(_channel),
            onBack: () => setState(() {
              _sentTo = null;
              _error = null;
            }),
          ),
        ],
      );
    }
    return _Form(
      title: 'Sign in',
      lede: "We'll send a one-time code. No password.",
      children: [
        if (_error != null) ...[Note(_error!, kind: NoteKind.error), _gap],
        const _FieldLabel('Phone number'),
        PhoneField(controller: _phone, onSubmitted: (_) => _send('whatsapp')),
        const SizedBox(height: 18),
        PrimaryButton(label: 'Send code by WhatsApp', busy: _busy && _channel == 'whatsapp', onPressed: () => _send('whatsapp')),
        const SizedBox(height: 10),
        SecondaryButton(label: 'Send by SMS', onPressed: _busy ? null : () => _send('sms')),
        const SizedBox(height: 24),
        TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SignUpScreen())),
          child: const Text('New to Afe? Create an account'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const StaffSignInScreen())),
          child: const Text('Afe staff: sign in with a password'),
        ),
      ],
    );
  }
}

class StaffSignInScreen extends StatefulWidget {
  const StaffSignInScreen({super.key});

  @override
  State<StaffSignInScreen> createState() => _StaffSignInScreenState();
}

class _StaffSignInScreenState extends State<StaffSignInScreen> {
  final _login = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  Widget build(BuildContext context) => _Form(
    title: 'Staff sign in',
    lede: "Then you'll enter the code from your authenticator app.",
    children: [
      if (_error != null) ...[Note(_error!, kind: NoteKind.error), _gap],
      const _FieldLabel('Username or phone'),
      TextField(controller: _login, autofillHints: const [AutofillHints.username]),
      _gap,
      const _FieldLabel('Password'),
      TextField(controller: _password, obscureText: true, autofillHints: const [AutofillHints.password]),
      const SizedBox(height: 20),
      PrimaryButton(
        label: 'Continue',
        busy: _busy,
        onPressed: () async {
          setState(() {
            _busy = true;
            _error = null;
          });
          try {
            final step = await context.session.signInWithPassword(_login.text, _password.text);
            if (context.mounted) await _next(context, step);
          } on ApiException catch (e) {
            setState(() => _error = e.message);
          } finally {
            if (mounted) setState(() => _busy = false);
          }
        },
      ),
    ],
  );
}

class MfaScreen extends StatefulWidget {
  const MfaScreen({super.key, required this.mfaToken, this.setupSecret, this.otpauthUri});
  final String mfaToken;
  final String? setupSecret;
  final String? otpauthUri;

  @override
  State<MfaScreen> createState() => _MfaScreenState();
}

class _MfaScreenState extends State<MfaScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _continue() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final step = await context.session.completeMfa(widget.mfaToken, _code.text);
      if (mounted) await _next(context, step);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final setup = widget.setupSecret != null;
    return _Form(
      title: setup ? 'Protect your account' : 'Authenticator code',
      lede: setup
          ? "Landlords, agents and Afe staff also use an authenticator app, so a stolen text message can't open the account. Add Afe to Google Authenticator or Microsoft Authenticator, then enter the 6-digit code it shows."
          : 'Open your authenticator app and enter the 6-digit code for Afe.',
      children: [
        if (_error != null) ...[Note(_error!, kind: NoteKind.error), _gap],
        if (setup) ...[
          SecondaryButton(
            label: 'Add to authenticator app',
            icon: Icons.open_in_new,
            onPressed: () => launchUrl(Uri.parse(widget.otpauthUri!), mode: LaunchMode.externalApplication),
          ),
          _gap,
          Text('Or type this key into the app:', style: TextStyle(color: a.muted)),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: SelectableText(widget.setupSecret!, style: AfeType.mono(16, color: a.ink).copyWith(letterSpacing: 1.2)),
              ),
              IconButton(
                tooltip: 'Copy key',
                icon: const Icon(Icons.copy),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: widget.setupSecret!));
                  toast(context, 'Key copied');
                },
              ),
            ],
          ),
          _gap,
        ],
        CodeBoxes(controller: _code, error: _error != null, onCompleted: _continue),
        const SizedBox(height: 20),
        PrimaryButton(label: setup ? 'Finish setup' : 'Continue', busy: _busy, onPressed: _continue),
      ],
    );
  }
}

class SignUpScreen extends StatefulWidget {
  const SignUpScreen({super.key, this.initialRole = 'renter'});

  /// 'renter' or 'landlord', from "How will you use Afe?" in Get started.
  final String initialRole;

  @override
  State<SignUpScreen> createState() => _SignUpScreenState();
}

class _SignUpScreenState extends State<SignUpScreen> {
  final _phone = TextEditingController();
  final _name = TextEditingController();
  final _code = TextEditingController();
  late String _role = widget.initialRole;
  String? _sentTo;
  String _channel = 'whatsapp';
  bool _busy = false;
  String? _error;

  Future<void> _run(Future<void> Function() f) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await f();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send(String channel) => _run(() async {
    final phone = phoneE164(_phone.text);
    if (_name.text.trim().length < 2) {
      setState(() => _error = 'Enter your full name, as it appears on your Ghana Card.');
      return;
    }
    if (!_ghanaMobile.hasMatch(phone)) {
      setState(() => _error = _badNumber);
      return;
    }
    await context.session.requestCode(phone, signup: true, channel: channel);
    _code.clear();
    setState(() {
      _sentTo = phone;
      _channel = channel;
    });
  });

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final sent = _sentTo;
    if (sent != null) {
      return _Form(
        title: 'Enter your code',
        bar: 'Create account',
        children: [
          _CodeStep(
            phone: sent,
            channel: _channel,
            code: _code,
            busy: _busy,
            error: _error,
            onVerify: () => _run(() async {
              final step = await context.session.signUp(phone: sent, code: _code.text, name: _name.text.trim(), role: _role);
              if (context.mounted) await _next(context, step);
            }),
            onResend: () => _send(_channel),
            onBack: () => setState(() {
              _sentTo = null;
              _error = null;
            }),
          ),
        ],
      );
    }
    final link = TextStyle(fontSize: 13, color: a.accent, fontWeight: FontWeight.w600);
    final quiet = TextStyle(fontSize: 13, color: a.muted);
    return _Form(
      title: 'Create your account',
      bar: 'Create account',
      lede: 'It takes a minute. No password needed.',
      children: [
        if (_error != null) ...[Note(_error!, kind: NoteKind.error), _gap],
        const _FieldLabel('I am'),
        Segmented<String>(
          items: const [('renter', 'Renter'), ('landlord', 'Landlord'), ('agent', 'Agent')],
          value: _role,
          onChanged: (v) => setState(() => _role = v),
        ),
        if (_role != 'renter') ...[
          const SizedBox(height: 10),
          const Note(
            'Landlords and agents are verified: a Ghana Card check, ownership papers and one visit from an Afe verifier.',
            kind: NoteKind.warn,
          ),
        ],
        const SizedBox(height: 18),
        const _FieldLabel('Full name'),
        TextField(
          controller: _name,
          textCapitalization: TextCapitalization.words,
          autofillHints: const [AutofillHints.name],
          decoration: const InputDecoration(hintText: 'Ama Mensah', helperText: 'As it appears on your Ghana Card'),
        ),
        const SizedBox(height: 14),
        const _FieldLabel('Phone number'),
        PhoneField(controller: _phone),
        const SizedBox(height: 18),
        PrimaryButton(label: 'Send code by WhatsApp', busy: _busy && _channel == 'whatsapp', onPressed: () => _send('whatsapp')),
        const SizedBox(height: 10),
        SecondaryButton(label: 'Send by SMS', onPressed: _busy ? null : () => _send('sms')),
        const SizedBox(height: 14),
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text('By creating an account you agree to the ', style: quiet),
            GestureDetector(
              onTap: () => openWeb('/terms'),
              child: Text('Terms', style: link),
            ),
            Text(' and ', style: quiet),
            GestureDetector(
              onTap: () => openWeb('/privacy'),
              child: Text('Privacy notice', style: link),
            ),
            Text('.', style: quiet),
          ],
        ),
      ],
    );
  }
}
