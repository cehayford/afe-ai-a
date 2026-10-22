import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';

/// Shared shape for the landlord forms, as the Landlord canvas's verification steps: a mono amber
/// kicker, the title and what it's for, an error line, labelled fields, and one main button
/// pinned to the bottom.
class _FormPage extends StatelessWidget {
  const _FormPage({
    required this.bar,
    required this.title,
    required this.children,
    required this.action,
    this.error,
    this.lede,
    this.kicker,
    this.footnote,
  });
  final String bar;
  final String title;
  final String? kicker;
  final String? lede;
  final String? error;
  final String? footnote;
  final List<Widget> children;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: AfeAppBar(title: Text(bar)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
        children: [
          if (kicker != null) ...[Text(kicker!.toUpperCase(), style: AfeType.label(a.warn, size: 11)), const SizedBox(height: 6)],
          Text(title, style: AfeType.heading(26, color: a.ink)),
          if (lede != null) ...[const SizedBox(height: 6), Text(lede!, style: TextStyle(color: a.muted, fontSize: 14.5, height: 1.45))],
          const SizedBox(height: 18),
          if (error != null) ...[Note(error!, kind: NoteKind.error), const SizedBox(height: 14)],
          ...children,
          if (footnote != null) ...[const SizedBox(height: 14), Text(footnote!, style: TextStyle(color: a.muted, fontSize: 13, height: 1.45))],
        ],
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: a.bar,
          border: Border(top: BorderSide(color: a.line)),
        ),
        padding: EdgeInsets.fromLTRB(16, 12, 16, 12 + MediaQuery.paddingOf(context).bottom),
        child: action,
      ),
    );
  }
}

const _gap = SizedBox(height: 16);

/// A label and its field.
Widget _field(String label, Widget field, {bool optional = false}) => Column(
  crossAxisAlignment: CrossAxisAlignment.stretch,
  children: [FieldLabel(label, optional: optional), field],
);

/// Chips for one choice among a few, wrapping onto new lines.
Widget _chips<T>(Map<T, String> items, T value, ValueChanged<T> onChanged) => Wrap(
  spacing: 8,
  runSpacing: 8,
  children: [for (final e in items.entries) AfeChip(label: e.value, selected: e.key == value, onTap: () => onChanged(e.key))],
);

mixin _Submitting<T extends StatefulWidget> on State<T> {
  bool busy = false;
  String? error;

  /// Runs [action]; the API's message shows at the top of the form if it fails.
  Future<void> submit(Future<void> Function() action) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.reasons.isEmpty ? e.message : '${e.message} ${e.reasons.join(' ')}');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }
}

// --- Ghana Card ---------------------------------------------------------------------------------

/// The landlord's or agent's Ghana Card check, with a selfie for the liveness check (canvas step 1).
class VerifyIdentityScreen extends StatefulWidget {
  const VerifyIdentityScreen({super.key});

  @override
  State<VerifyIdentityScreen> createState() => _VerifyIdentityScreenState();
}

class _VerifyIdentityScreenState extends State<VerifyIdentityScreen> with _Submitting {
  final _card = TextEditingController();
  final _name = TextEditingController();
  XFile? _selfie;

  @override
  Widget build(BuildContext context) => _FormPage(
    bar: 'Get verified',
    kicker: 'Step 1 of 4',
    title: 'Your Ghana Card',
    lede: 'We match your card with a live selfie. The selfie goes to our identity partner; Afe keeps only the result and a scrambled code of the card number, and never shows it to renters.',
    error: error,
    action: PrimaryButton(
      label: 'Check my card',
      busy: busy,
      onPressed: _selfie == null
          ? null
          : () => submit(() async {
              final res = await context.api.upload<Json>(
                '/kyc/ghana-card',
                fields: {'card_number': _card.text.trim(), 'full_name': _name.text.trim()},
                files: {'selfie': _selfie!.path},
              );
              if (!context.mounted) return;
              final status = '${res.data['status']}';
              await context.session.reloadMe();
              if (!context.mounted) return;
              toast(context, status == 'passed' ? 'Card checked. Thank you.' : 'Card check: ${res.data['failure_reason'] ?? status}');
              Navigator.pop(context);
            }),
    ),
    children: [
      _field(
        'Ghana Card number',
        TextField(
          controller: _card,
          textCapitalization: TextCapitalization.characters,
          style: AfeType.mono(16),
          decoration: const InputDecoration(hintText: 'GHA-000000000-0'),
        ),
      ),
      _gap,
      _field(
        'Full name, as on the card',
        TextField(controller: _name, textCapitalization: TextCapitalization.words),
      ),
      _gap,
      UploadTile(
        title: _selfie == null ? 'Take live selfie' : '✓ Selfie taken',
        note: _selfie == null ? 'live check, front camera' : 'tap to retake',
        done: _selfie != null,
        onTap: () async {
          final shot = await ImagePicker().pickImage(
            source: ImageSource.camera,
            preferredCameraDevice: CameraDevice.front,
            maxWidth: 1200,
            imageQuality: 85,
          );
          if (shot != null) setState(() => _selfie = shot);
        },
      ),
    ],
  );
}

// --- Add a home ------------------------------------------------------------------------------------

const propertyTypes = {
  'single_room': 'Single room',
  'chamber_and_hall': 'Chamber and hall',
  'self_contained': 'Self-contained',
  'apartment': 'Apartment',
  'house': 'House',
};

/// Register a home: its GhanaPost address and a pin placed on the map (the verifier checks in
/// within a few hundred metres of it, so it must be on the building).
class AddHomeScreen extends StatefulWidget {
  const AddHomeScreen({super.key});

  @override
  State<AddHomeScreen> createState() => _AddHomeScreenState();
}

class _AddHomeScreenState extends State<AddHomeScreen> with _Submitting {
  final _map = MapController();
  final _address = TextEditingController();
  final _label = TextEditingController();
  final _landmark = TextEditingController();
  List<Area> _areas = [];
  String _area = '';
  String _type = 'apartment';
  int _bedrooms = 2;
  int _bathrooms = 1;
  LatLng _pin = const LatLng(5.6037, -0.1870);
  bool _pinMoved = false;

  @override
  void initState() {
    super.initState();
    context.api
        .get<List>('/properties/areas')
        .then((r) {
          if (!context.mounted) return;
          setState(() {
            _areas = [for (final a in r.data) Area(a as Json)];
          });
          if (_areas.isNotEmpty) _chooseArea(_areas.first.slug);
        })
        .catchError((_) {});
  }

  Area? get _chosen => _areas.where((a) => a.slug == _area).firstOrNull;

  /// Show the chosen area on the map, outlined: the pin has to go inside it.
  void _chooseArea(String slug) {
    setState(() {
      _area = slug;
      _pinMoved = false;
    });
    final c = _chosen?.centre;
    if (c != null) {
      _pin = LatLng(c.$1, c.$2);
      try {
        _map.move(_pin, 14);
      } catch (_) {
        // The map isn't drawn yet; it starts at _pin.
      }
    }
  }

  Future<void> _here() async {
    try {
      final p = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.best));
      setState(() {
        _pin = LatLng(p.latitude, p.longitude);
        _pinMoved = true;
      });
      _map.move(_pin, 17);
    } catch (_) {
      if (mounted) toast(context, 'Couldn\'t get your location. Move the map to the home instead.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return _FormPage(
      bar: 'Add a home',
      kicker: 'New home',
      title: 'Where and what it is',
      lede: 'Its GhanaPost address, a pin on the building, and the basics. Renters see the area, never the exact spot.',
      error: error,
      action: PrimaryButton(
        label: _pinMoved ? 'Add home' : 'Place the pin on the map first',
        busy: busy,
        onPressed: !_pinMoved || _area.isEmpty
            ? null
            : () => submit(() async {
                final res = await context.api.post<Json>('/properties/units', {
                  'area_slug': _area,
                  'digital_address': _address.text.trim(),
                  'unit_label': _label.text.trim(),
                  'lat': _pin.latitude.toStringAsFixed(6),
                  'lng': _pin.longitude.toStringAsFixed(6),
                  'property_type': _type,
                  'bedrooms': _bedrooms,
                  'bathrooms': _bathrooms,
                  'landmark': _landmark.text.trim(),
                });
                if (context.mounted) Navigator.pop(context, MyUnit(res.data).unit.id);
              }),
      ),
      children: [
        _field(
          'Area',
          DropdownButtonFormField<String>(
            initialValue: _area.isEmpty ? null : _area,
            items: [for (final a in _areas) DropdownMenuItem(value: a.slug, child: Text(a.name))],
            onChanged: (v) {
              if (v != null) _chooseArea(v);
            },
          ),
        ),
        _gap,
        _field(
          'Home address or GhanaPost GPS code',
          TextField(
            controller: _address,
            textCapitalization: TextCapitalization.characters,
            style: AfeType.mono(16),
            decoration: const InputDecoration(hintText: 'GA-492-7713'),
          ),
        ),
        _gap,
        _field('Flat or room', TextField(controller: _label, decoration: const InputDecoration(hintText: 'Flat 3')), optional: true),
        _gap,
        const FieldLabel('Type of home'),
        _chips(propertyTypes, _type, (v) => setState(() => _type = v)),
        _gap,
        Panel(
          padded: true,
          children: [
            CountStepper(label: 'Bedrooms', value: _bedrooms, onChanged: (v) => setState(() => _bedrooms = v)),
            CountStepper(label: 'Bathrooms', value: _bathrooms, onChanged: (v) => setState(() => _bathrooms = v)),
          ],
        ),
        _gap,
        _field(
          'Nearby landmark',
          TextField(controller: _landmark, decoration: const InputDecoration(hintText: 'Behind the Total station')),
          optional: true,
        ),
        const SizedBox(height: 20),
        const FieldLabel('Where is it?'),
        Text(
          'Move the map until the pin is on the building, inside the outlined area.',
          style: TextStyle(color: a.muted, fontSize: 13),
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(a.cardRadius),
          child: SizedBox(
            height: 260,
            child: Stack(
              alignment: Alignment.center,
              children: [
                FlutterMap(
                  mapController: _map,
                  options: MapOptions(
                    initialCenter: _pin,
                    initialZoom: 14,
                    onPositionChanged: (camera, hasGesture) {
                      if (hasGesture) {
                        _pin = camera.center;
                        if (!_pinMoved) setState(() => _pinMoved = true);
                      }
                    },
                  ),
                  children: [
                    TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', userAgentPackageName: 'com.afe.app'),
                    if (_chosen != null && _chosen!.boundary.length > 2)
                      PolygonLayer(
                        polygons: [
                          Polygon(
                            points: [for (final p in _chosen!.boundary) LatLng(p.$1, p.$2)],
                            color: a.brand.withValues(alpha: 0.08),
                            borderColor: a.brand,
                            borderStrokeWidth: 2,
                          ),
                        ],
                      ),
                  ],
                ),
                // The pin stays in the middle; the map moves under it.
                IgnorePointer(
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 36),
                    child: Icon(Icons.location_pin, size: 44, color: a.crit),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerLeft,
          child: SmallButton(label: 'I\'m at the home: use my location', kind: SmallKind.quiet, onPressed: _here),
        ),
      ],
    );
  }
}

// --- Ownership documents ------------------------------------------------------------------------------

const relationships = {
  'owner': 'I own it',
  'authorised_agent': 'Authorised agent',
  'caretaker': 'Caretaker',
};

const documentTypes = {
  'indenture': 'Indenture',
  'land_title': 'Land title certificate',
  'lands_commission_search': 'Lands Commission search',
  'site_plan': 'Site plan',
  'owner_authorisation': 'Letter of authority',
};

/// Proof you can rent it out (canvas step 2): who you are to the home, the document type as
/// chips, and the upload tile.
class UploadDocumentScreen extends StatefulWidget {
  const UploadDocumentScreen({super.key, required this.unitId});
  final int unitId;

  @override
  State<UploadDocumentScreen> createState() => _UploadDocumentScreenState();
}

class _UploadDocumentScreenState extends State<UploadDocumentScreen> with _Submitting {
  String _relationship = 'owner';
  String _type = 'indenture';
  final _utility = TextEditingController();
  String? _path;
  String? _name;

  Future<void> _photo(ImageSource source) async {
    final shot = await ImagePicker().pickImage(source: source, maxWidth: 2400, imageQuality: 90);
    if (shot != null) {
      setState(() {
        _path = shot.path;
        _name = shot.name;
      });
    }
  }

  Future<void> _pdf() async {
    final files = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: ['pdf', 'jpg', 'jpeg', 'png']);
    final f = files.isEmpty ? null : files.single;
    if (f?.path != null) {
      setState(() {
        _path = f!.path;
        _name = f.name;
      });
    }
  }

  /// Camera, photos or a PDF, from a sheet under the tile.
  Future<void> _choose() async {
    final a = context.afe;
    final pick = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Add the document', style: AfeType.heading(20, color: a.ink)),
              const SizedBox(height: 12),
              SecondaryButton(label: 'Take a photo', icon: Icons.photo_camera_outlined, onPressed: () => Navigator.pop(context, 'camera')),
              const SizedBox(height: 8),
              SecondaryButton(label: 'Choose from photos', icon: Icons.photo_outlined, onPressed: () => Navigator.pop(context, 'photos')),
              const SizedBox(height: 8),
              SecondaryButton(label: 'Choose a PDF', icon: Icons.picture_as_pdf_outlined, onPressed: () => Navigator.pop(context, 'pdf')),
            ],
          ),
        ),
      ),
    );
    switch (pick) {
      case 'camera':
        await _photo(ImageSource.camera);
      case 'photos':
        await _photo(ImageSource.gallery);
      case 'pdf':
        await _pdf();
    }
  }

  @override
  Widget build(BuildContext context) => _FormPage(
    bar: 'Ownership document',
    kicker: 'Step 2 of 4',
    title: 'Proof you can rent it out',
    lede: 'Our verifier sees the original at the visit. A clear photo is enough for now.',
    error: error,
    footnote: 'Stored privately. Only Afe reviewers can open it, and every opening is logged.',
    action: PrimaryButton(
      label: 'Upload',
      busy: busy,
      onPressed: _path == null
          ? null
          : () => submit(() async {
              await context.api.upload(
                '/kyc/units/${widget.unitId}/authority',
                fields: {'relationship': _relationship, 'document_type': _type, 'utility_reference': _utility.text.trim()},
                files: {'document': _path!},
              );
              if (!context.mounted) return;
              toast(context, 'Uploaded. An Afe reviewer will read it.');
              Navigator.pop(context, true);
            }),
    ),
    children: [
      const FieldLabel('You are'),
      _chips(relationships, _relationship, (v) {
        setState(() {
          _relationship = v;
          if (v != 'owner') _type = 'owner_authorisation';
        });
      }),
      _gap,
      const FieldLabel('Document type'),
      _chips(documentTypes, _type, (v) => setState(() => _type = v)),
      _gap,
      UploadTile(
        title: _path == null ? 'Upload document' : '✓ Document added',
        note: _name ?? 'PDF or photo, all pages',
        done: _path != null,
        onTap: _choose,
      ),
      _gap,
      _field(
        'ECG meter or utility account number',
        TextField(controller: _utility, decoration: const InputDecoration(helperText: 'Helps the reviewer match the document to the home')),
        optional: true,
      ),
    ],
  );
}

// --- A listing -----------------------------------------------------------------------------------------

class NewListingScreen extends StatefulWidget {
  const NewListingScreen({super.key, required this.unitId});
  final int unitId;

  @override
  State<NewListingScreen> createState() => _NewListingScreenState();
}

class _NewListingScreenState extends State<NewListingScreen> with _Submitting {
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _rent = TextEditingController();
  int _advance = 6;
  int _minLease = 12;
  DateTime _from = DateTime.now().add(const Duration(days: 7));

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return _FormPage(
      bar: 'New listing',
      kicker: 'Next step',
      title: 'Create a listing',
      lede: 'Afe checks the listing before it goes live. The photos are the ones our verifier took.',
      error: error,
      action: PrimaryButton(
        label: 'Save and send for review',
        busy: busy,
        onPressed: () => submit(() async {
          final res = await context.api.post<Json>('/properties/listings', {
            'unit_id': widget.unitId,
            'title': _title.text.trim(),
            'description': _description.text.trim(),
            'rent_ghs': _rent.text.trim(),
            'advance_months': _advance,
            'min_lease_months': _minLease,
            'available_from': '${_from.year}-${_from.month.toString().padLeft(2, '0')}-${_from.day.toString().padLeft(2, '0')}',
          });
          if (!context.mounted) return;
          await context.api.post('/properties/listings/${Listing(res.data).id}/submit');
          if (!context.mounted) return;
          toast(context, 'Sent to Afe for a check. It goes live once approved.');
          Navigator.pop(context, true);
        }),
      ),
      children: [
        _field('Title', TextField(controller: _title, decoration: const InputDecoration(hintText: 'Bright 2-bedroom flat near Oxford Street'))),
        _gap,
        _field(
          'Description',
          TextField(
            controller: _description,
            minLines: 4,
            maxLines: 8,
            decoration: const InputDecoration(hintText: 'What renters should know: water, power, parking, who else lives there'),
          ),
        ),
        _gap,
        _field(
          'Monthly rent (GH₵)',
          TextField(
            controller: _rent,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
            style: AfeType.heading(18),
            decoration: const InputDecoration(hintText: '3,500', prefixText: 'GH₵ '),
          ),
        ),
        _gap,
        const FieldLabel('Months in advance'),
        ChipRow<int>(items: [for (var m = 1; m <= 6; m++) (m, '$m')], value: _advance, onChanged: (v) => setState(() => _advance = v)),
        const SizedBox(height: 6),
        Text('The law caps advance rent at 6 months (Rent Act 220).', style: TextStyle(color: a.muted, fontSize: 13)),
        _gap,
        const FieldLabel('Shortest lease'),
        Segmented<int>(
          items: const [(6, '6 months'), (12, '12 months'), (24, '24 months')],
          value: _minLease,
          onChanged: (v) => setState(() => _minLease = v),
        ),
        _gap,
        const FieldLabel('Available from'),
        Material(
          color: a.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.inputRadius), side: BorderSide(color: a.line)),
          child: InkWell(
            customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.inputRadius)),
            onTap: () async {
              final d = await showDatePicker(
                context: context,
                firstDate: DateTime.now(),
                lastDate: DateTime.now().add(const Duration(days: 365)),
                initialDate: _from,
              );
              if (d != null) setState(() => _from = d);
            },
            child: SizedBox(
              height: 52,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                child: Row(
                  children: [
                    Expanded(child: Text(day(_from), style: const TextStyle(fontSize: 16))),
                    Icon(Icons.calendar_today_outlined, size: 20, color: a.muted),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// --- Payout account ------------------------------------------------------------------------------------

const payoutChannels = {
  'momo_mtn': 'MTN Mobile Money',
  'momo_telecel': 'Telecel Cash',
  'momo_at': 'AT Money',
  'bank': 'Bank account',
};

/// Where we send your rent (canvas step 3). Changing it needs a fresh authenticator code, and the
/// new account can't receive money for 72 hours. Both protect landlords if someone else gets into
/// their account.
class ChangePayoutScreen extends StatefulWidget {
  const ChangePayoutScreen({super.key});

  @override
  State<ChangePayoutScreen> createState() => _ChangePayoutScreenState();
}

class _ChangePayoutScreenState extends State<ChangePayoutScreen> with _Submitting {
  String _channel = 'momo_mtn';
  final _number = TextEditingController();
  final _code = TextEditingController();

  @override
  Widget build(BuildContext context) => _FormPage(
    bar: 'Payout account',
    kicker: 'Step 3 of 4',
    title: 'Where we send your rent',
    lede: 'The name on this account must match your Ghana Card.',
    error: error,
    footnote: 'Your first account works straight away. If you change it later, payouts to the new account pause for 72 hours and we text you, so no one else can redirect your rent.',
    action: PrimaryButton(
      label: 'Save payout account',
      busy: busy,
      onPressed: () => submit(() async {
        final res = await context.api.post<Json>('/me/payouts', {
          'channel': _channel,
          'account_number': _number.text.replaceAll(RegExp(r'\s'), ''),
          'code': _code.text,
        });
        if (!context.mounted) return;
        final p = Payee(res.data);
        final ready = p.usableFrom == null || !p.usableFrom!.isAfter(DateTime.now());
        toast(context, ready ? 'Saved. It can receive money now.' : 'Saved. It can receive money from ${dayTime(p.usableFrom)}.');
        Navigator.pop(context, true);
      }),
    ),
    children: [
      const FieldLabel('Network'),
      _chips(payoutChannels, _channel, (v) => setState(() => _channel = v)),
      _gap,
      _field(
        _channel == 'bank' ? 'Account number' : 'Wallet number',
        TextField(
          controller: _number,
          keyboardType: TextInputType.number,
          decoration: InputDecoration(hintText: _channel == 'bank' ? '0123456789012' : '24 555 0142'),
        ),
      ),
      _gap,
      _field(
        'Code from your authenticator app',
        TextField(
          controller: _code,
          keyboardType: TextInputType.number,
          autofillHints: const [AutofillHints.oneTimeCode],
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
          style: AfeType.mono(18),
          decoration: const InputDecoration(hintText: '000000'),
        ),
      ),
    ],
  );
}
