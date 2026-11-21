<<<<<<< HEAD
import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

/// Fragt alle 2 Sekunden den Status der Fahrt ab (Fahrer, ETA, Ziele).
=======
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../services/api_service.dart';

/// Zeigt ETA und Live-Status der Fahrt über WebSocket.
>>>>>>> origin/main
class TrackingScreen extends StatefulWidget {
  final int rideId;
  const TrackingScreen({super.key, required this.rideId});
  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
<<<<<<< HEAD
  final _api = ApiService();
  Timer? _timer;
  Map<String, dynamic>? _ride;
  String? _error;
  bool _rated = false;
=======
  late final WebSocketChannel _ch;
>>>>>>> origin/main

  @override
  void initState() {
    super.initState();
<<<<<<< HEAD
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _refresh());
=======
    _ch = WebSocketChannel.connect(
        Uri.parse('$wsBaseUrl/ws/rides/${widget.rideId}'));
>>>>>>> origin/main
  }

  @override
  void dispose() {
<<<<<<< HEAD
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
      if (mounted) setState(() => _error = '$e');
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
          const SizedBox(height: 16),
          _stops(r),
        ];
      case 'in_progress':
        return [
          const Text('Fahrt läuft', style: big),
          const SizedBox(height: 12),
          driver,
          const SizedBox(height: 16),
          _stops(r),
        ];
      case 'completed':
        return [
          const Text('Fahrt beendet', style: big),
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
=======
    _ch.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ihre Fahrt')),
      body: StreamBuilder(
        stream: _ch.stream,
        builder: (context, snap) {
          if (!snap.hasData) {
            return const Center(child: Text('Fahrer wird gesucht …'));
          }
          final d = jsonDecode(snap.data as String);
          return Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // TODO: GoogleMap-Widget mit Marker für d['lat'], d['lng']
                Text('Fahrer kommt in ${d['eta_minutes']} Min.',
                    style: const TextStyle(
                        fontSize: 28, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text('${d['driver_name']}  ★ ${d['driver_rating']}'),
                Text('${d['vehicle']}'),
              ],
            ),
          );
        },
      ),
    );
  }
>>>>>>> origin/main
}
