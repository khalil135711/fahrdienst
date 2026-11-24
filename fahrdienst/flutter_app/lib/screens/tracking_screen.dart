import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'package:url_launcher/url_launcher.dart';
import 'news_screen.dart';

/// Fragt alle 2 Sekunden den Status der Fahrt ab (Fahrer, ETA, Ziele).
class TrackingScreen extends StatefulWidget {
  final int rideId;
  const TrackingScreen({super.key, required this.rideId});
  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
  final _api = ApiService();
  Timer? _timer;
  Map<String, dynamic>? _ride;
  String? _error;
  bool _rated = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final r = await _api.getRide(widget.rideId);
      if (!mounted) return;
      setState(() {
        _ride = r;
        _error = null;
      });
      if (r['status'] == 'completed' || r['status'] == 'no_driver') {
        _timer?.cancel();
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _ride;
    return Scaffold(
      appBar: AppBar(title: const Text('Ihre Fahrt')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: r == null
            ? Center(child: Text(_error ?? 'Lädt …'))
            : ListView(children: [
                // TODO: GoogleMap mit Marker für r['driver_lat'], r['driver_lng']
                ..._statusWidgets(r),
                if (_error != null)
                  Text(_error!, style: const TextStyle(color: Colors.red)),
              ]),
      ),
    );
  }

  List<Widget> _statusWidgets(Map<String, dynamic> r) {
    const big = TextStyle(fontSize: 28, fontWeight: FontWeight.bold);
    final driver = Text(
        '${r['driver_name']}  ★ ${r['driver_rating']}\n${r['vehicle']}');
    switch (r['status']) {
      case 'requested':
        return [
          const Text('Fahrer wird gesucht …', style: big),
          const SizedBox(height: 16),
          const LinearProgressIndicator(),
          const SizedBox(height: 8),
          const Text('Die Anfrage geht nacheinander an Fahrer in Ihrer Nähe.'),
          _priceInfo(r),
        ];
      case 'no_driver':
        return [
          const Text('Kein Fahrer verfügbar', style: big),
          const SizedBox(height: 8),
          const Text('Im Umkreis ist gerade kein freier Fahrer. Bitte versuchen Sie es später noch einmal.'),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Zurück')),
        ];
      case 'accepted':
        return [
          Text('Fahrer kommt in ${r['eta_minutes']} Min.', style: big),
          const SizedBox(height: 12),
          driver,
          _priceInfo(r),
          const SizedBox(height: 16),
          _stops(r),
          const SizedBox(height: 12),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.newspaper),
            label: const Text('Zeitungen lesen'),
            onPressed: () => Navigator.push(
                context, MaterialPageRoute(builder: (_) => const NewsScreen())),
          ),
        ];
      case 'in_progress':
        return [
          const Text('Fahrt läuft', style: big),
          const SizedBox(height: 12),
          driver,
          _priceInfo(r),
          const SizedBox(height: 16),
          _stops(r),
          const SizedBox(height: 12),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.newspaper),
            label: const Text('Zeitungen lesen'),
            onPressed: () => Navigator.push(
                context, MaterialPageRoute(builder: (_) => const NewsScreen())),
          ),
        ];
      case 'completed':
        return [
          const Text('Fahrt beendet', style: big),
          _priceInfo(r),
          _receiptButton(r),
          const SizedBox(height: 16),
          _stops(r),
          const SizedBox(height: 24),
          Text(_rated ? 'Danke für Ihre Bewertung!' : 'Wie war Ihre Fahrt?',
              style: const TextStyle(fontSize: 20)),
          if (!_rated)
            Row(children: [
              for (int i = 1; i <= 5; i++)
                IconButton(
                    iconSize: 40,
                    color: Colors.amber,
                    icon: const Icon(Icons.star),
                    onPressed: () async {
                      await _api.rateRide(widget.rideId, i, '');
                      if (mounted) setState(() => _rated = true);
                    }),
            ]),
        ];
      default:
        return [Text('Status: ${r['status']}')];
    }
  }

  Widget _priceInfo(Map<String, dynamic> r) {
    final p = r['price'];
    if (p == null) return const SizedBox.shrink();
    final fare = r['fare'] as Map?;
    final lines = <String>[];
    if (fare != null && fare['kind'] == 'partner') {
      lines.add('Servicegebühr: ${euro(p as num)}');
      lines.add('Fahrer von ${r['company']}. Den Fahrpreis rechnen Sie direkt mit dem Fahrer ab.');
    } else {
      final shared = r['shared'] == true;
      lines.add('${shared ? 'Geteilte Fahrt (Mitfahrer möglich)' : 'Einzelfahrt'}: ${euro(p as num)}');
      if (r['vehicle_type'] == 'wheelchair') lines.add('Rollstuhlfahrzeug');
      if (r['payment_method'] == 'taxischein') {
        lines.add('Abrechnung mit Taxischein');
      }
    }
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final l in lines) Text(l, style: const TextStyle(fontSize: 16)),
      ]),
    );
  }

  /// Quittung als PDF: kurzlebiger Link, öffnet sich im Browser (dort speichern oder teilen).
  Widget _receiptButton(Map<String, dynamic> r) {
    if (r['receipt_available'] != true) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: FilledButton.icon(
        icon: const Icon(Icons.receipt_long),
        label: const Text('Quittung als PDF herunterladen'),
        onPressed: () async {
          try {
            final url = await _api.receiptLink(widget.rideId);
            final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
            if (!ok && mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Die Quittung konnte nicht geöffnet werden')));
            }
          } catch (e) {
            if (mounted) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(SnackBar(content: Text(errorText(e))));
            }
          }
        },
      ),
    );
  }

  Widget _stops(Map<String, dynamic> r) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final s in (r['stops'] as List))
            Row(children: [
              Icon(s['reached'] ? Icons.check_circle : Icons.circle_outlined,
                  size: 18, color: s['reached'] ? Colors.green : null),
              const SizedBox(width: 8),
              Expanded(child: Text('Ziel ${s['position']}: ${s['address']}')),
            ]),
        ],
      );
}
