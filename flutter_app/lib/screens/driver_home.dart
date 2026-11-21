import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import '../services/api_service.dart';

class DriverHome extends StatefulWidget {
  const DriverHome({super.key});
  @override
  State<DriverHome> createState() => _DriverHomeState();
}

class _DriverHomeState extends State<DriverHome> {
  final _api = ApiService();
  bool _free = false;
  StreamSubscription<Position>? _sub;

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
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fahrer-Modus')),
      body: Center(
        child: SwitchListTile(
          title: Text(_free ? 'Ich bin FREI' : 'Ich bin OFFLINE'),
          subtitle: const Text('Anfragen in Ihrer Nähe erhalten'),
          value: _free,
          onChanged: _toggle,
        ),
      ),
    );
  }
}
