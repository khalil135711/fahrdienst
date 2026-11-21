import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import '../services/api_service.dart';
<<<<<<< HEAD
import '../services/auth_store.dart';
=======
>>>>>>> origin/main

class DriverHome extends StatefulWidget {
  const DriverHome({super.key});
  @override
  State<DriverHome> createState() => _DriverHomeState();
}

class _DriverHomeState extends State<DriverHome> {
  final _api = ApiService();
  bool _free = false;
  StreamSubscription<Position>? _sub;
<<<<<<< HEAD
  Timer? _poll;
  Map<String, dynamic>? _offer;
  Map<String, dynamic>? _active;
  String? _error;

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
          locationSettings: const LocationSettings(
              accuracy: LocationAccuracy.high, distanceFilter: 20),
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
          _active = null;
        });
      }
    } catch (e) {
      setState(() {
        _free = false;
        _error = '$e';
      });
    }
  }

  Future<void> _refresh() async {
    try {
      final s = await _api.driverState();
      if (!mounted) return;
      setState(() {
        _offer = s['offer'] as Map<String, dynamic>?;
        _active = s['active'] as Map<String, dynamic>?;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _do(Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
    await _refresh();
  }

  Future<void> _logout() async {
    if (_free && _active == null) {
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
=======

  Future<void> _toggle(bool v) async {
    setState(() => _free = v);
    await _api.setDriverStatus(v);
    if (v) {
      await Geolocator.requestPermission();
      _sub = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
            accuracy: LocationAccuracy.high, distanceFilter: 20),
      ).listen((p) => _api.sendLocation(
          p.latitude, p.longitude, p.speed * 3.6)); // m/s -> km/h
    } else {
      await _sub?.cancel();
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
>>>>>>> origin/main
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
<<<<<<< HEAD
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
          if (_free && _offer == null && _active == null)
            const Padding(
              padding: EdgeInsets.all(32),
              child: Center(child: Text('Warte auf Anfragen …')),
            ),
          if (_offer != null) _offerCard(_offer!),
          if (_active != null) _activeCard(_active!),
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
          const SizedBox(height: 12),
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
=======
      appBar: AppBar(title: const Text('Fahrer-Modus')),
      body: Center(
        child: SwitchListTile(
          title: Text(_free ? 'Ich bin FREI' : 'Ich bin OFFLINE'),
          subtitle: const Text('Anfragen in Ihrer Nähe erhalten'),
          value: _free,
          onChanged: _toggle,
        ),
>>>>>>> origin/main
      ),
    );
  }
}
