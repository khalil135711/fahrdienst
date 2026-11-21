import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import '../services/api_service.dart';
import 'tracking_screen.dart';

const int maxStops = 4;

class CustomerHome extends StatefulWidget {
  const CustomerHome({super.key});
  @override
  State<CustomerHome> createState() => _CustomerHomeState();
}

class _CustomerHomeState extends State<CustomerHome> {
  final _api = ApiService();
  final List<TextEditingController> _stops = [TextEditingController()];
  Position? _pos;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _loadLocation();
  }

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
  }

  void _addStop() {
    if (_stops.length < maxStops) {
      setState(() => _stops.add(TextEditingController()));
    }
  }

  void _removeStop(int i) {
    if (_stops.length > 1) setState(() => _stops.removeAt(i).dispose());
  }

  Future<void> _request() async {
    final stops =
        _stops.map((c) => c.text.trim()).where((t) => t.isNotEmpty).toList();
    if (_pos == null || stops.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Standort fehlt oder kein Ziel eingegeben')));
      return;
    }
    setState(() => _loading = true);
    try {
      final ride = await _api.requestRide(
          lat: _pos!.latitude, lng: _pos!.longitude, stops: stops);
      if (!mounted) return;
      Navigator.push(context,
          MaterialPageRoute(builder: (_) => TrackingScreen(rideId: ride.id)));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fahrt anfragen')),
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
                controller: _stops[i],
                decoration: InputDecoration(
                  labelText: 'Ziel ${i + 1}',
                  border: const OutlineInputBorder(),
                  prefixIcon: CircleAvatar(
                      radius: 12, child: Text('${i + 1}', style: const TextStyle(fontSize: 12))),
                  suffixIcon: _stops.length > 1
                      ? IconButton(
                          icon: const Icon(Icons.close),
                          onPressed: () => _removeStop(i))
                      : null,
                ),
              ),
            ),
          if (_stops.length < maxStops)
            TextButton.icon(
              onPressed: _addStop,
              icon: const Icon(Icons.add),
              label: Text('Weiteres Ziel (${_stops.length}/$maxStops)'),
            ),
          const SizedBox(height: 24),
          SizedBox(
            height: 56,
            child: FilledButton(
              onPressed: _loading ? null : _request,
              child: _loading
                  ? const CircularProgressIndicator()
                  : const Text('Fahrt anfragen'),
            ),
          ),
        ],
      ),
    );
  }
}
