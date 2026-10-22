import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/foundation.dart' show defaultTargetPlatform;
import 'package:flutter/material.dart';

/// Afe's colours, the same tokens as the website (frontend/src/app.css) and the "Afe App Screen"
/// canvas of the Claude Design project. Light first, then dark.
class AfeColors {
  static const brand = Color(0xFF0E4A3E);
  static const accent = Color(0xFF0F6B57);
  static const amber = Color(0xFFD9961A);
  static const amberSoft = Color(0xFFFBF1DC);
  static const paper = Color(0xFFF5F8F7);
  static const ink = Color(0xFF15211E);
  static const muted = Color(0xFF56665F);
  static const line = Color(0xFFD5DFDB);
  static const tint = Color(0xFFE7F0EC);
  static const ok = Color(0xFF16794C);
  static const okSoft = Color(0xFFE3F4EA);
  static const warn = Color(0xFF9A6200);
  static const crit = Color(0xFFB42318);

  static const darkPaper = Color(0xFF0D1513);
  static const darkSurface = Color(0xFF13201C);
  static const darkInk = Color(0xFFE4EDE9);
  static const darkMuted = Color(0xFF9DB0A8);
  static const darkLine = Color(0xFF26382F);
  static const darkAccent = Color(0xFF5FC7A8);
  static const darkAmber = Color(0xFFF0B84A);
}

/// The palette and platform metrics every screen reads through `context.afe`.
/// iOS gets Cupertino touches (12 px buttons, pill chips); Android gets Material 3 (pill buttons,
/// 8 px chips, 4 px fields), exactly as the canvas draws them side by side.
@immutable
class Afe extends ThemeExtension<Afe> {
  const Afe({
    required this.ios,
    required this.dark,
    required this.bg,
    required this.surface,
    required this.ink,
    required this.muted,
    required this.line,
    required this.tint,
    required this.brand,
    required this.onBrand,
    required this.accent,
    required this.amber,
    required this.amberSoft,
    required this.ok,
    required this.okSoft,
    required this.warn,
    required this.warnSoft,
    required this.crit,
    required this.critSoft,
    required this.bar,
  });

  final bool ios;
  final bool dark;
  final Color bg, surface, ink, muted, line, tint, brand, onBrand, accent, amber, amberSoft;
  final Color ok, okSoft, warn, warnSoft, crit, critSoft, bar;

  // Metrics from the canvas (--bh, --br, --cr, --in-r, --seg-r and the chip / yes-no styles).
  double get buttonHeight => ios ? 50 : 48;
  double get buttonRadius => ios ? 12 : 24;
  double get cardRadius => ios ? 14 : 12;
  double get inputRadius => ios ? 10 : 4;
  double get segmentRadius => ios ? 9 : 20;
  double get chipHeight => ios ? 36 : 32;
  double get chipRadius => ios ? 99 : 8;
  double get pickRadius => ios ? 10 : 22;
  double get drawerItemHeight => ios ? 48 : 56;
  double get drawerItemRadius => ios ? 10 : 28;

  factory Afe.of(Brightness brightness, bool ios) => brightness == Brightness.dark
      ? Afe(
          ios: ios,
          dark: true,
          bg: AfeColors.darkPaper,
          surface: AfeColors.darkSurface,
          ink: AfeColors.darkInk,
          muted: AfeColors.darkMuted,
          line: AfeColors.darkLine,
          tint: const Color(0xFF18302A),
          brand: AfeColors.darkAccent,
          onBrand: AfeColors.darkPaper,
          accent: AfeColors.darkAccent,
          amber: AfeColors.darkAmber,
          amberSoft: const Color(0xFF3A2E14),
          ok: const Color(0xFF4ADE9A),
          okSoft: const Color(0xFF133226),
          warn: const Color(0xFFF5B94A),
          warnSoft: const Color(0xFF352A12),
          crit: const Color(0xFFF97066),
          critSoft: const Color(0xFF3B1917),
          bar: ios ? const Color(0xF013201C) : AfeColors.darkSurface,
        )
      : Afe(
          ios: ios,
          dark: false,
          bg: AfeColors.paper,
          surface: Colors.white,
          ink: AfeColors.ink,
          muted: AfeColors.muted,
          line: AfeColors.line,
          tint: AfeColors.tint,
          brand: AfeColors.brand,
          onBrand: Colors.white,
          accent: AfeColors.brand,
          amber: AfeColors.amber,
          amberSoft: AfeColors.amberSoft,
          ok: AfeColors.ok,
          okSoft: AfeColors.okSoft,
          warn: AfeColors.warn,
          warnSoft: const Color(0xFFFDF3DE),
          crit: AfeColors.crit,
          critSoft: const Color(0xFFFDECEA),
          bar: ios ? const Color(0xF0F5F8F7) : const Color(0xFFEEF3F1),
        );

  @override
  Afe copyWith() => this;

  @override
  Afe lerp(ThemeExtension<Afe>? other, double t) => other is Afe && t > 0.5 ? other : this;
}

extension AfeContext on BuildContext {
  Afe get afe => Theme.of(this).extension<Afe>()!;
}

/// Type: Bricolage Grotesque for headings and figures, IBM Plex Sans for text, IBM Plex Mono for
/// references and small labels. All three are bundled (assets/fonts, OFL).
class AfeType {
  static const display = 'Bricolage Grotesque';
  static const sans = 'IBM Plex Sans';
  static const monoFamily = 'IBM Plex Mono';

  static TextStyle heading(double size, {Color? color, double height = 1.1}) =>
      TextStyle(fontFamily: display, fontSize: size, fontWeight: FontWeight.w700, height: height, color: color);

  /// Uppercase mono label, e.g. "RENT / MONTH", "BEDS".
  static TextStyle label(Color color, {double size = 10}) =>
      TextStyle(fontFamily: monoFamily, fontSize: size, letterSpacing: size * 0.08, color: color);

  static TextStyle mono(double size, {Color? color, FontWeight weight = FontWeight.w400}) =>
      TextStyle(fontFamily: monoFamily, fontSize: size, color: color, fontWeight: weight);
}

/// Motion: short, ease-out, and only where it tells the person something (press feedback,
/// content arriving). Nothing here runs longer than 300 ms.
class Motion {
  static const easeOut = Cubic(0.23, 1, 0.32, 1);
  static const snap = Cubic(0.2, 0.8, 0.2, 1);
  static const press = Duration(milliseconds: 160);
  static const appear = Duration(milliseconds: 220);

  static bool reduced(BuildContext context) => MediaQuery.maybeDisableAnimationsOf(context) ?? false;
}

ThemeData afeTheme(Brightness brightness, {TargetPlatform? platform}) {
  final target = platform ?? defaultTargetPlatform;
  final ios = target == TargetPlatform.iOS || target == TargetPlatform.macOS;
  final a = Afe.of(brightness, ios);
  final scheme = ColorScheme(
    brightness: brightness,
    primary: a.brand,
    onPrimary: a.onBrand,
    secondary: a.amber,
    onSecondary: const Color(0xFF15211E),
    error: a.crit,
    onError: Colors.white,
    surface: a.surface,
    onSurface: a.ink,
    onSurfaceVariant: a.muted,
    outline: a.line,
    outlineVariant: a.line,
    surfaceContainerLowest: a.bg,
    surfaceContainerLow: a.bg,
    surfaceContainer: a.surface,
    surfaceContainerHigh: a.surface,
    surfaceContainerHighest: a.tint,
    primaryContainer: a.tint,
    onPrimaryContainer: a.accent,
    secondaryContainer: a.tint,
    onSecondaryContainer: a.ink,
  );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: brightness, fontFamily: AfeType.sans, platform: target);
  final t = base.textTheme;
  final heading = TextStyle(fontFamily: AfeType.display, fontWeight: FontWeight.w700, color: a.ink);
  final buttonText = const TextStyle(fontFamily: AfeType.sans, fontWeight: FontWeight.w600, fontSize: 16);
  final buttonShape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.buttonRadius));
  OutlineInputBorder field(Color c, [double w = 1]) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(a.inputRadius),
    borderSide: BorderSide(color: c, width: w),
  );

  return base.copyWith(
    extensions: [a],
    scaffoldBackgroundColor: a.bg,
    canvasColor: a.bg,
    dividerColor: a.tint,
    dividerTheme: DividerThemeData(color: a.tint, thickness: 1, space: 1),
    textTheme: t.copyWith(
      displaySmall: heading.copyWith(fontSize: 34, height: 1.1),
      headlineMedium: heading.copyWith(fontSize: 28, height: 1.1),
      headlineSmall: heading.copyWith(fontSize: 26, height: 1.1),
      titleLarge: heading.copyWith(fontSize: 22, height: 1.15),
      titleMedium: heading.copyWith(fontSize: 17, height: 1.15),
      titleSmall: TextStyle(fontFamily: AfeType.sans, fontWeight: FontWeight.w600, fontSize: 15, color: a.ink),
      bodyLarge: t.bodyLarge?.copyWith(fontSize: 16, height: 1.5, color: a.ink),
      bodyMedium: t.bodyMedium?.copyWith(fontSize: 14.5, height: 1.5, color: a.ink),
      bodySmall: t.bodySmall?.copyWith(fontSize: 13, height: 1.45, color: a.muted),
      labelLarge: buttonText,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: a.bar,
      foregroundColor: a.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: ios,
      toolbarHeight: ios ? 44 : 64,
      titleTextStyle: ios
          ? TextStyle(fontFamily: 'CupertinoSystemText', fontSize: 17, fontWeight: FontWeight.w600, color: a.ink)
          : TextStyle(fontFamily: AfeType.sans, fontSize: 22, fontWeight: FontWeight.w500, color: a.ink),
      shape: ios ? Border(bottom: BorderSide(color: a.line, width: 0.5)) : null,
    ),
    cardTheme: CardThemeData(
      color: a.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(a.cardRadius),
        side: BorderSide(color: a.line),
      ),
      clipBehavior: Clip.antiAlias,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: a.brand,
        foregroundColor: a.onBrand,
        disabledBackgroundColor: a.line,
        disabledForegroundColor: a.muted,
        minimumSize: Size(0, a.buttonHeight),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        shape: buttonShape,
        textStyle: buttonText,
        elevation: 0,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: a.ink,
        minimumSize: Size(0, a.buttonHeight),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        shape: buttonShape,
        side: BorderSide(color: a.line),
        textStyle: buttonText,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: a.accent, textStyle: buttonText.copyWith(fontSize: 15)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: a.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
      labelStyle: TextStyle(color: a.muted),
      floatingLabelStyle: TextStyle(color: a.accent, fontWeight: FontWeight.w600),
      hintStyle: TextStyle(color: a.muted),
      border: field(a.line),
      enabledBorder: field(a.line),
      focusedBorder: field(a.brand, 2),
      errorBorder: field(a.crit),
      focusedErrorBorder: field(a.crit, 2),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: a.surface,
      selectedColor: a.tint,
      side: BorderSide(color: a.line),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.chipRadius)),
      labelStyle: TextStyle(fontFamily: AfeType.sans, fontWeight: FontWeight.w600, fontSize: 14, color: a.ink),
      showCheckmark: false,
    ),
    listTileTheme: ListTileThemeData(
      iconColor: a.muted,
      titleTextStyle: TextStyle(fontFamily: AfeType.sans, fontSize: 15.5, color: a.ink),
    ),
    drawerTheme: DrawerThemeData(
      backgroundColor: a.surface,
      width: 300,
      shape: ios
          ? const RoundedRectangleBorder()
          : const RoundedRectangleBorder(borderRadius: BorderRadius.horizontal(right: Radius.circular(16))),
    ),
    bottomSheetTheme: BottomSheetThemeData(backgroundColor: a.surface, surfaceTintColor: Colors.transparent),
    dialogTheme: DialogThemeData(backgroundColor: a.surface, surfaceTintColor: Colors.transparent),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: a.ink,
      contentTextStyle: TextStyle(fontFamily: AfeType.sans, color: a.bg, fontSize: 14.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.cardRadius)),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: a.brand),
    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? a.brand : Colors.transparent),
      checkColor: WidgetStatePropertyAll(a.onBrand),
      side: BorderSide(color: a.line, width: 2),
      shape: ios ? const CircleBorder() : RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
    ),
    radioTheme: RadioThemeData(fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? a.brand : a.line)),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? a.onBrand : null),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? a.brand : null),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: a.bar,
      indicatorColor: a.tint,
      labelTextStyle: WidgetStatePropertyAll(t.labelMedium?.copyWith(fontFamily: AfeType.sans)),
    ),
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {TargetPlatform.android: FadeForwardsPageTransitionsBuilder(), TargetPlatform.iOS: CupertinoPageTransitionsBuilder()},
    ),
  );
}
