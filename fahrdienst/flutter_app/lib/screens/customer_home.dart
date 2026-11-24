import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import '../services/api_service.dart';
import '../services/auth_store.dart';
import 'tracking_screen.dart';

const int maxStops = 4;

/// Ein Ziel: Text und (nach der Adresssuche) Koordinaten.
class _StopInput {
  final TextEditingController text = TextEditingController();
  double? lat;
  double? lng;
  bool get resolved => lat != null && lng != null;
}

class CustomerHome extends StatefulWidget {
  const CustomerHome({super.key});
  @override
  State<CustomerHome> createState() => _CustomerHomeState();
}

class _CustomerHomeState extends State<CustomerHome> {
  final _api = ApiService();
  final List<_StopInput> _stops = [_StopInput()];
  Position? _pos;
  bool _loading = false;
  bool _shared = false;
  String _vehicle = 'normal'; // normal | wheelchair
  String _payment = 'km'; // km | taxischein
  bool _allowPartner = false;
  final _voucher = TextEditingController();
  Map<String, dynamic>? _quote;

  @override
  void initState() {
    super.initState();
    _loadLocation();
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  /// Abfahrt = aktueller Standort des Kunden.
  Future<void> _loadLocation() async {
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.denied ||
        perm == LocationPermission.deniedForever) {
      return;
    }
    final p = await Geolocator.getCurrentPosition();
    if (mounted) setState(() => _pos = p);
    _updateQuote();
  }

  void _addStop() {
    if (_stops.length < maxStops) {
      setState(() => _stops.add(_StopInput()));
      _updateQuote();
    }
  }

  void _removeStop(int i) {
    if (_stops.length > 1) {
      setState(() => _stops.removeAt(i).text.dispose());
      _updateQuote();
    }
  }

  /// Nur ausgefüllte Ziele; mit Koordinaten, wenn über die Suche gewählt.
  List<Map<String, dynamic>> _payloadStops() => [
        for (final s in _stops)
          if (s.text.text.trim().isNotEmpty)
            {
              'address': s.text.text.trim(),
              if (s.resolved) 'lat': s.lat,
              if (s.resolved) 'lng': s.lng,
            }
      ];

  bool get _allResolved {
    final filled = _stops.where((s) => s.text.text.trim().isNotEmpty).toList();
    return filled.isNotEmpty && filled.every((s) => s.resolved);
  }

  Future<void> _search(int i) async {
    final q = _stops[i].text.text.trim();
    if (q.length < 3) {
      _snack('Bitte mindestens 3 Zeichen eingeben');
      return;
    }
    try {
      final results = await _api.geoSearch(q);
      if (!mounted) return;
      if (results.isEmpty) {
        _snack('Nichts gefunden. Bitte genauer eingeben (Straße, Hausnummer, Ort).');
        return;
      }
      final pick = await showModalBottomSheet<Map<String, dynamic>>(
        context: context,
        builder: (ctx) => SafeArea(
          child: ListView(shrinkWrap: true, children: [
            const ListTile(
                title: Text('Bitte Ziel auswählen',
                    style: TextStyle(fontWeight: FontWeight.bold))),
            for (final r in results)
              ListTile(
                leading: const Icon(Icons.place),
                title: Text('${r['label']}', maxLines: 2, overflow: TextOverflow.ellipsis),
                onTap: () => Navigator.pop(ctx, r),
              ),
          ]),
        ),
      );
      if (pick == null) return;
      setState(() {
        _stops[i].text.text = '${pick['label']}'.split(',').take(3).join(',').trim();
        _stops[i].lat = (pick['lat'] as num).toDouble();
        _stops[i].lng = (pick['lng'] as num).toDouble();
      });
      _updateQuote();
    } catch (e) {
      _snack(errorText(e));
    }
  }

  /// Preis berechnen, sobald Standort und alle Ziele mit Koordinaten bekannt sind.
  Future<void> _updateQuote() async {
    if (_pos == null || !_allResolved) {
      if (mounted) {
        setState(() {
          _quote = null;
          _shared = false;
        });
      }
      return;
    }
    try {
      final q = await _api.quote(
          lat: _pos!.latitude,
          lng: _pos!.longitude,
          stops: _payloadStops(),
          vehicleType: _vehicle);
      if (!mounted) return;
      setState(() {
        _quote = q;
        if (q['own_shared'] == null) _shared = false; // Rollstuhlfahrten kann man nicht teilen
        if (q['partners_available'] != true) _allowPartner = false;
      });
    } catch (e) {
      if (mounted) setState(() => _quote = null);
    }
  }

  Future<void> _request() async {
    final stops = _payloadStops();
    if (_pos == null || stops.isEmpty) {
      _snack('Standort fehlt oder kein Ziel eingegeben');
      return;
    }
    if (!_allResolved) {
      _snack('Bitte jedes Ziel über die Lupe auswählen, sonst gibt es keinen Preis');
      return;
    }
    if (_payment == 'taxischein' && _voucher.text.trim().length < 3) {
      _snack('Bitte die Nummer des Taxischeins eingeben');
      return;
    }
    setState(() => _loading = true);
    try {
      final ride = await _api.requestRide(
          lat: _pos!.latitude,
          lng: _pos!.longitude,
          stops: stops,
          shared: _shared,
          vehicleType: _vehicle,
          paymentMethod: _payment,
          voucherNo: _payment == 'taxischein' ? _voucher.text.trim() : null,
          allowPartner: _allowPartner);
      if (!mounted) return;
      Navigator.push(context,
          MaterialPageRoute(builder: (_) => TrackingScreen(rideId: ride.id)));
    } catch (e) {
      if (mounted) _snack(errorText(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _line(String label, num value, {bool bold = false, Color? color}) {
    final style = TextStyle(fontWeight: bold ? FontWeight.bold : FontWeight.normal, color: color);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 1),
      child: Row(children: [
        Expanded(child: Text(label, style: style)),
        Text(euro(value), style: style),
      ]),
    );
  }

  Widget _quoteCard() {
    final q = _quote;
    if (q == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text(
          'Tippen Sie bei jedem Ziel auf die Lupe und wählen Sie die Adresse aus. '
          'Dann sehen Sie den Preis, bevor Sie buchen.',
          style: TextStyle(color: Colors.grey),
        ),
      );
    }
    final canShare = q['own_shared'] != null;
    final fare = Map<String, dynamic>.from(_shared && canShare ? q['own_shared'] : q['own']);
    final partner = Map<String, dynamic>.from(q['partner']);
    final solo = (q['own']['total'] as num);
    final pct = (q['discount_pct'] as num).round();
    final vehicleName = _vehicle == 'wheelchair' ? 'Rollstuhlfahrzeug' : 'Normalfahrzeug';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${q['distance_km']} km · ca. ${q['duration_min']} Min.',
              style: const TextStyle(color: Colors.grey)),
          const SizedBox(height: 6),
          const Text('Preis bei unseren Fahrern',
              style: TextStyle(fontWeight: FontWeight.bold)),
          _line('Anfahrtskosten ($vehicleName)', fare['approach_fee'] as num),
          _line('Strecke ${q['distance_km']} km × ${euro(fare['per_km'] as num)}/km',
              fare['km_price'] as num),
          if ((fare['discount'] as num) > 0)
            _line('Rabatt geteilte Fahrt (−$pct %)', -(fare['discount'] as num),
                color: Colors.green),
          const Divider(height: 12),
          _line('Voraussichtlicher Preis', fare['total'] as num, bold: true),
          if (_payment == 'taxischein')
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text(
                  'Mit Taxischein: Sie geben den Schein beim Fahrer ab, der Betrag wird mit dem Kostenträger abgerechnet.',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
            ),
          if (canShare)
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Fahrt teilen und sparen'),
              subtitle: Text(
                'Es können Mitfahrer zusteigen, die in Ihre Richtung fahren. '
                'Sie zahlen ${euro(q['own_shared']['total'] as num)} statt ${euro(solo)} (−$pct %).',
              ),
              value: _shared,
              onChanged: (v) => setState(() => _shared = v),
            )
          else
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('Rollstuhlfahrten werden nicht geteilt.',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
            ),
          if (q['partners_available'] == true)
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Auch Partnerfirmen zulassen'),
              subtitle: Text(
                'Unsere eigenen Fahrer werden immer zuerst gefragt. Übernimmt ein Fahrer einer '
                'Partnerfirma, zahlen Sie uns nur die Servicegebühr von ${euro(partner['booking_fee'] as num)}. '
                'Den Fahrpreis rechnen Sie dann direkt mit dem Fahrer ab (Taxameter oder Taxischein).',
              ),
              value: _allowPartner,
              onChanged: (v) => setState(() => _allowPartner = v),
            ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Hallo ${AuthStore.name ?? ''}'), actions: [
        IconButton(
            tooltip: 'Abmelden',
            icon: const Icon(Icons.logout),
            onPressed: AuthStore.logout),
      ]),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Text('Wohin möchten Sie?',
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
          const SizedBox(height: 20),
          // Abfahrt: automatisch, nicht editierbar
          ListTile(
            tileColor: Colors.blue.withOpacity(0.08),
            leading: const Icon(Icons.my_location, color: Colors.blue),
            title: const Text('Abfahrt: Ihr aktueller Standort'),
            subtitle: Text(_pos == null
                ? 'Standort wird ermittelt …'
                : '${_pos!.latitude.toStringAsFixed(4)}, ${_pos!.longitude.toStringAsFixed(4)}'),
          ),
          const SizedBox(height: 12),
          for (int i = 0; i < _stops.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: TextField(
                controller: _stops[i].text,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _search(i),
                onChanged: (_) {
                  // Text geändert: die gewählte Adresse gilt nicht mehr
                  if (_stops[i].resolved) {
                    setState(() {
                      _stops[i].lat = null;
                      _stops[i].lng = null;
                    });
                    _updateQuote();
                  }
                },
                decoration: InputDecoration(
                  labelText: 'Ziel ${i + 1}',
                  helperText: _stops[i].resolved ? 'Adresse ausgewählt ✓' : null,
                  border: const OutlineInputBorder(),
                  prefixIcon: Icon(
                      _stops[i].resolved ? Icons.check_circle : Icons.place_outlined,
                      color: _stops[i].resolved ? Colors.green : null),
                  suffixIcon: Row(mainAxisSize: MainAxisSize.min, children: [
                    IconButton(
                        tooltip: 'Adresse suchen',
                        icon: const Icon(Icons.search),
                        onPressed: () => _search(i)),
                    if (_stops.length > 1)
                      IconButton(
                          tooltip: 'Ziel entfernen',
                          icon: const Icon(Icons.close),
                          onPressed: () => _removeStop(i)),
                  ]),
                ),
              ),
            ),
          if (_stops.length < maxStops)
            TextButton.icon(
              onPressed: _addStop,
              icon: const Icon(Icons.add),
              label: Text('Weiteres Ziel (${_stops.length}/$maxStops)'),
            ),
          const Text('Fahrzeug', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'normal', icon: Icon(Icons.directions_car), label: Text('Normal')),
              ButtonSegment(value: 'wheelchair', icon: Icon(Icons.accessible), label: Text('Rollstuhl')),
            ],
            selected: {_vehicle},
            onSelectionChanged: (v) {
              setState(() {
                _vehicle = v.first;
                if (_vehicle == 'wheelchair') _shared = false;
              });
              _updateQuote();
            },
          ),
          const SizedBox(height: 16),
          const Text('Zahlung', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'km', icon: Icon(Icons.speed), label: Text('Nach Kilometern')),
              ButtonSegment(value: 'taxischein', icon: Icon(Icons.confirmation_number), label: Text('Taxischein')),
            ],
            selected: {_payment},
            onSelectionChanged: (v) => setState(() => _payment = v.first),
          ),
          if (_payment == 'taxischein')
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: TextField(
                controller: _voucher,
                decoration: const InputDecoration(
                    labelText: 'Nummer des Taxischeins', border: OutlineInputBorder()),
              ),
            ),
          const SizedBox(height: 12),
          _quoteCard(),
          const SizedBox(height: 16),
          SizedBox(
            height: 56,
            child: FilledButton(
              onPressed: (_loading || !_allResolved || _pos == null) ? null : _request,
              child: _loading
                  ? const CircularProgressIndicator()
                  : Text(_shared ? 'Geteilte Fahrt anfragen' : 'Fahrt anfragen'),
            ),
          ),
        ],
      ),
    );
  }
}
