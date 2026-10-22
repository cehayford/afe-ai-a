import 'package:flutter/material.dart';

import '../theme.dart';

/// The Afe mark from the "Afe Mark" canvas, on a 100-unit grid: c = lettermark tile (the logo),
/// a = verified home, b = held safe. At 32 px and below the strokes get heavier and the "a"
/// bigger. [onDark] uses the dark-mode colours (tile #0F6B57, amber #F0B84A); by default the mark
/// follows the app's brightness.
class AfeMark extends StatelessWidget {
  const AfeMark({super.key, this.size = 32, this.variant = 'c', this.onDark});
  final double size;
  final String variant;
  final bool? onDark;

  @override
  Widget build(BuildContext context) {
    final dark = onDark ?? Theme.of(context).brightness == Brightness.dark;
    return Semantics(
      label: 'Afe',
      child: CustomPaint(size: Size.square(size), painter: _MarkPainter(variant, size, dark)),
    );
  }
}

class _MarkPainter extends CustomPainter {
  _MarkPainter(this.variant, this.size, this.dark);
  final String variant;
  final double size;
  final bool dark;

  @override
  void paint(Canvas canvas, Size s) {
    final sm = size <= 32;
    final house = dark ? const Color(0xFF0F6B57) : const Color(0xFF0E4A3E);
    final amber = dark ? const Color(0xFFF0B84A) : const Color(0xFFD9961A);
    canvas.scale(s.width / 100);
    final fill = Paint()..color = house;
    final stroke = Paint()
      ..color = amber
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    Path line(List<double> p) {
      final path = Path()..moveTo(p[0], p[1]);
      for (var i = 2; i < p.length; i += 2) {
        path.lineTo(p[i], p[i + 1]);
      }
      return path;
    }

    if (variant == 'c') {
      canvas.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(0, 0, 100, 100), const Radius.circular(24)), fill);
      stroke.strokeWidth = sm ? 10 : 7;
      canvas.drawPath(line(sm ? [24, 33, 50, 18, 76, 33] : [28, 34, 50, 22, 72, 34]), stroke);
      final tp = TextPainter(
        text: TextSpan(
          text: 'a',
          style: TextStyle(
            fontFamily: AfeType.display,
            fontWeight: FontWeight.w700,
            fontSize: sm ? 66 : 58,
            color: Colors.white,
            height: 1,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final baseline = tp.computeDistanceToActualBaseline(TextBaseline.alphabetic);
      tp.paint(canvas, Offset(50 - tp.width / 2, (sm ? 86 : 81) - baseline));
      return;
    }
    final body = line([50, 12, 88, 43, 88, 88, 12, 88, 12, 43])..close();
    canvas.drawPath(body, fill);
    canvas.drawPath(
      body,
      Paint()
        ..color = house
        ..style = PaintingStyle.stroke
        ..strokeWidth = 8
        ..strokeJoin = StrokeJoin.round,
    );
    if (variant == 'a') {
      stroke.strokeWidth = sm ? 13 : 10;
      canvas.drawPath(line(sm ? [30, 63, 45, 77, 70, 50] : [32, 64, 45, 76, 68, 52]), stroke);
    } else {
      final key = Paint()..color = amber;
      canvas.drawCircle(Offset(50, sm ? 58 : 59), sm ? 13 : 10, key);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(sm ? 43.5 : 45.5, 62, sm ? 13 : 9, sm ? 20 : 18), const Radius.circular(3)),
        key,
      );
    }
  }

  @override
  bool shouldRepaint(_MarkPainter old) => old.variant != variant || old.dark != dark || old.size != size;
}

/// Mark + lowercase "afe" wordmark, with an optional role tag in mono amber ("Landlord").
class AfeLogo extends StatelessWidget {
  const AfeLogo({super.key, this.mark = 32, this.text = 22, this.tag});
  final double mark;
  final double text;
  final String? tag;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        AfeMark(size: mark),
        const SizedBox(width: 10),
        Text(
          'afe',
          style: AfeType.heading(text, color: a.ink).copyWith(letterSpacing: -0.02 * text),
        ),
        if (tag != null) ...[const SizedBox(width: 10), Text(tag!.toUpperCase(), style: AfeType.label(a.amber, size: 11))],
      ],
    );
  }
}
