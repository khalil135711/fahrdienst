import 'dart:async';
import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import '../services/api_service.dart';
import '../services/auth_store.dart';
import '../services/config.dart';
import '../services/navigation.dart';
import 'music_panel.dart';

class DriverHome extends StatefulWidget {
  const DriverHome({super.key});
  @override
  State<DriverHome> createState() => _DriverHomeState();
}

class _DriverHomeState extends State<DriverHome> {
  final _api = ApiService();
  bool _free = false;
  StreamSubscription<Position>? _sub;
  Timer? _poll;
  Map<String, dynamic>? _offer;
  List<Map<String, dynamic>> _activeRides = [];
  List<Map<String, dynamic>> _plan = [];
  String? _error;

  /// Mit BACKGROUND_MODE meldet das Handy den Standort auch im Hintergrund weiter
  /// (Android: Benachrichtigung „Fahrdienst“, iOS: blauer Hintergrund-Hinweis).
  LocationSettings _locationSettings() {
    const accuracy = LocationAccuracy.high;
    if (!backgroundMode || kIsWeb) {
      return const LocationSettings(accuracy: accuracy, distanceFilter: 20);
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return AndroidSettings(
          accuracy: accuracy,
          distanceFilter: 20,
          foregroundNotificationConfig: const ForegroundNotificationConfig(
            notificationTitle: 'Fahrdienst',
            notificationText: 'Ihr Standort wird für Fahrtanfragen übermittelt',
            enableWakeLock: true,
          ),
        );
      case TargetPlatform.iOS:
      case TargetPlatform.macOS:
        return AppleSettings(
          accuracy: accuracy,
          distanceFilter: 20,
          activityType: ActivityType.automotiveNavigation,
          pauseLocationUpdatesAutomatically: false,
          showBackgroundLocationIndicator: true,
          allowBackgroundLocationUpdates: true,
        );
      default:
        return const LocationSettings(accuracy: accuracy, distanceFilter: 20);
    }
  }

  Future<void> _toggle(bool v) async {
    setState(() {
      _free = v;
      _error = null;
    });
    try {
      await _api.setDriverStatus(v);
      if (v) {
        var perm = await Geolocator.checkPermission();
        if (perm == LocationPermission.denied) {
          perm = await Geolocator.requestPermission();
        }
        if (perm == LocationPermission.denied ||
            perm == LocationPermission.deniedForever) {
          throw Exception('Standortfreigabe fehlt');
        }
        // Sofort die aktuelle Position melden, sonst findet das System den Fahrer nicht
        final p = await Geolocator.getCurrentPosition();
        await _api.sendLocation(p.latitude, p.longitude, 0);
        _sub = Geolocator.getPositionStream(
          locationSettings: _locationSettings(),
        ).listen((p) => _api
            .sendLocation(p.latitude, p.longitude, p.speed * 3.6) // m/s -> km/h
            .catchError((_) {}));
        _poll = Timer.periodic(const Duration(seconds: 2), (_) => _refresh());
        _refresh();
      } else {
        await _sub?.cancel();
        _poll?.cancel();
        setState(() {
          _offer = null;
          _activeRides = [];
          _plan = [];
        });
      }
    } catch (e) {
      setState(() {
        _free = false;
        _error = errorText(e);
      });
    }
  }

  Future<void> _refresh() async {
    try {
      final s = await _api.driverState();
      if (!mounted) return;
      setState(() {
        _offer = s['offer'] as Map<String, dynamic>?;
        _activeRides = [
          for (final r in (s['active_rides'] as List? ?? [])) Map<String, dynamic>.from(r)
        ];
        _plan = [
          for (final e in (s['route_plan'] as List? ?? [])) Map<String, dynamic>.from(e)
        ];
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    }
  }

  Future<void> _do(Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    }
    await _refresh();
  }

  Future<void> _logout() async {
    if (_free && _activeRides.isEmpty) {
      try {
        await _api.setDriverStatus(false);
      } catch (_) {}
    }
    await AuthStore.logout();
  }

  @override
  void dispose() {
    _sub?.cancel();
    _poll?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Fahrer: ${AuthStore.name ?? ''}'), actions: [
        IconButton(
            tooltip: 'Abmelden',
            icon: const Icon(Icons.logout),
            onPressed: _logout),
      ]),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SwitchListTile(
            title: Text(_free ? 'Ich bin FREI' : 'Ich bin OFFLINE'),
            subtitle: const Text('Anfragen in Ihrer Nähe erhalten'),
            value: _free,
            onChanged: _toggle,
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          if (_free && _offer == null && _activeRides.isEmpty)
            const Padding(
              padding: EdgeInsets.all(32),
              child: Center(child: Text('Warte auf Anfragen …')),
            ),
          if (_offer != null) _offerCard(_offer!),
          if (_plan.isNotEmpty) _planCard(),
          for (final a in _activeRides) _activeCard(a),
          const SizedBox(height: 8),
          const MusicPanel(),
        ],
      ),
    );
  }

  Widget _stopsList(List stops) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final s in stops)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(children: [
                Icon(s['reached'] ? Icons.check_circle : Icons.circle_outlined,
                    size: 18, color: s['reached'] ? Colors.green : null),
                const SizedBox(width: 8),
                Expanded(child: Text('Ziel ${s['position']}: ${s['address']}')),
              ]),
            ),
        ],
      );

  Widget _offerCard(Map<String, dynamic> o) {
    final km = (o['distance_m'] as int) / 1000;
    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Expanded(
                child: Text('Neue Anfrage',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold))),
            Chip(label: Text('${o['seconds_left']} s')),
          ]),
          if (o['vehicle_type'] == 'wheelchair')
            const Padding(
              padding: EdgeInsets.only(bottom: 6),
              child: Text('♿ Rollstuhlfahrt',
                  style: TextStyle(color: Colors.red, fontWeight: FontWeight.bold)),
            ),
          if (o['kind'] == 'pool')
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                'Mitfahrer: steigt in Ihre laufende Fahrt zu'
                '${o['detour_km'] != null ? ' (Umweg ca. ${o['detour_km']} km)' : ''}',
                style: const TextStyle(color: Colors.green, fontWeight: FontWeight.w600),
              ),
            )
          else if (o['shared'] == true)
            const Padding(
              padding: EdgeInsets.only(bottom: 6),
              child: Text('Geteilte Fahrt: Mitfahrer können zusteigen',
                  style: TextStyle(color: Colors.green)),
            ),
          Text('Kunde: ${o['customer']}'),
          Text('Abholung in ${km.toStringAsFixed(1)} km Entfernung'),
          const SizedBox(height: 8),
          _stopsList(o['stops']),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
                child: OutlinedButton(
                    onPressed: () => _do(() => _api.declineRide(o['ride_id'])),
                    child: const Text('Ablehnen'))),
            const SizedBox(width: 12),
            Expanded(
                child: FilledButton(
                    onPressed: () => _do(() => _api.acceptRide(o['ride_id'])),
                    child: const Text('Annehmen'))),
          ]),
        ]),
      ),
    );
  }

  /// Empfohlene Reihenfolge der Halte, wenn mehrere Fahrgäste an Bord sind oder zusteigen.
  Widget _planCard() {
    final first = _plan.first;
    return Card(
      color: Theme.of(context).colorScheme.secondaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Empfohlene Reihenfolge',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          for (int i = 0; i < _plan.length; i++)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text('${i + 1}. ${_plan[i]['label']}',
                  style: TextStyle(fontWeight: i == 0 ? FontWeight.bold : FontWeight.normal)),
            ),
          const SizedBox(height: 4),
          const Text('Das ist ein Vorschlag, Sie entscheiden vor Ort.',
              style: TextStyle(fontSize: 12, color: Colors.grey)),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              icon: const Icon(Icons.navigation),
              label: const Text('Navigation zum nächsten Halt'),
              onPressed: () => openNavigation(
                  context,
                  NavTarget(
                      label: '${first['label']}',
                      lat: (first['lat'] as num).toDouble(),
                      lng: (first['lng'] as num).toDouble())),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _activeCard(Map<String, dynamic> a) {
    final stops = a['stops'] as List;
    final next = stops.cast<Map>().firstWhere((s) => !s['reached'], orElse: () => {});
    final id = a['ride_id'] as int;
    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Fahrt mit ${a['customer']}',
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          Text(a['status'] == 'accepted'
              ? 'Fahren Sie zum Kunden (Abholung)'
              : 'Fahrt läuft'),
          const SizedBox(height: 8),
          _stopsList(stops),
          if (a['vehicle_type'] == 'wheelchair')
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('♿ Rollstuhlfahrt',
                  style: TextStyle(color: Colors.red, fontWeight: FontWeight.bold)),
            ),
          if ('${a['payment_info'] ?? ''}'.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('${a['payment_info']}',
                  style: const TextStyle(fontStyle: FontStyle.italic)),
            ),
          const SizedBox(height: 12),
          if (a['status'] == 'accepted' && a['pickup_lat'] != null)
            SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                    icon: const Icon(Icons.navigation),
                    label: const Text('Navigation zum Kunden'),
                    onPressed: () => openNavigation(
                        context,
                        NavTarget(
                            label: 'Kunde ${a['customer']}',
                            lat: (a['pickup_lat'] as num).toDouble(),
                            lng: (a['pickup_lng'] as num).toDouble())))),
          if (a['status'] == 'in_progress' && next.isNotEmpty)
            SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                    icon: const Icon(Icons.navigation),
                    label: Text('Navigation zu Ziel ${next['position']}'),
                    onPressed: () => openNavigation(
                        context,
                        NavTarget(
                            label: 'Ziel ${next['position']}',
                            address: '${next['address']}')))),
          const SizedBox(height: 8),
          if (a['status'] == 'accepted')
            SizedBox(
                width: double.infinity,
                child: FilledButton(
                    onPressed: () => _do(() => _api.startRide(id)),
                    child: const Text('Kunde abgeholt'))),
          if (a['status'] == 'in_progress' && next.isNotEmpty)
            SizedBox(
                width: double.infinity,
                child: FilledButton(
                    onPressed: () =>
                        _do(() => _api.stopReached(id, next['position'])),
                    child: Text('Ziel ${next['position']} erreicht'))),
        ]),
      ),
    );
  }
}
