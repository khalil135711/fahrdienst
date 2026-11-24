import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/auth_store.dart';

/// Admin: Übersicht, Fahrerliste mit Status, Bewertung, Fahrten, Kilometer,
/// Geschwindigkeit; Fahrer anlegen, sperren, Passwort zurücksetzen.
class AdminHome extends StatefulWidget {
  const AdminHome({super.key});
  @override
  State<AdminHome> createState() => _AdminHomeState();
}

class _AdminHomeState extends State<AdminHome> {
  final _api = ApiService();
  Timer? _timer;
  Map<String, dynamic>? _overview;
  List<Map<String, dynamic>> _drivers = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final o = await _api.adminOverview();
      final d = await _api.adminDrivers();
      if (!mounted) return;
      setState(() {
        _overview = o;
        _drivers = d;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    }
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Color _statusColor(Map<String, dynamic> d) {
    if (d['active'] != true) return Colors.red;
    switch (d['status']) {
      case 'free':
        return Colors.green;
      case 'busy':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  String _statusText(Map<String, dynamic> d) {
    if (d['active'] != true) return 'gesperrt';
    switch (d['status']) {
      case 'free':
        return 'frei';
      case 'busy':
        return 'unterwegs';
      default:
        return 'offline';
    }
  }

  Future<void> _createDriver() async {
    final name = TextEditingController();
    final email = TextEditingController();
    final pass = TextEditingController();
    final model = TextEditingController();
    final plate = TextEditingController();
    String? error;
    bool busy = false;
    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: const Text('Fahrer anlegen'),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
              TextField(
                  controller: email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'E-Mail')),
              TextField(
                  controller: pass,
                  decoration: const InputDecoration(
                      labelText: 'Start-Passwort (mind. 8 Zeichen)')),
              TextField(
                  controller: model,
                  decoration: const InputDecoration(labelText: 'Fahrzeug (z. B. Mercedes E-Klasse)')),
              TextField(
                  controller: plate,
                  decoration: const InputDecoration(labelText: 'Kennzeichen')),
              if (error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(error!, style: const TextStyle(color: Colors.red)),
                ),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Abbrechen')),
            FilledButton(
              onPressed: busy
                  ? null
                  : () async {
                      setD(() {
                        busy = true;
                        error = null;
                      });
                      try {
                        await _api.adminCreateDriver(
                            name: name.text.trim(),
                            email: email.text.trim(),
                            password: pass.text,
                            vehicleModel: model.text.trim(),
                            plate: plate.text.trim());
                        if (ctx.mounted) Navigator.pop(ctx);
                        _snack('Fahrer angelegt. Geben Sie ihm E-Mail und Passwort.');
                        _load();
                      } catch (e) {
                        setD(() {
                          busy = false;
                          error = errorText(e);
                        });
                      }
                    },
              child: const Text('Anlegen'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _resetPassword(Map<String, dynamic> d) async {
    final pass = TextEditingController();
    String? error;
    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: Text('Neues Passwort für ${d['name']}'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
                controller: pass,
                decoration: const InputDecoration(labelText: 'Neues Passwort (mind. 8 Zeichen)')),
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(error!, style: const TextStyle(color: Colors.red)),
              ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Abbrechen')),
            FilledButton(
              onPressed: () async {
                try {
                  await _api.adminResetPassword(d['id'], pass.text);
                  if (ctx.mounted) Navigator.pop(ctx);
                  _snack('Passwort geändert');
                } catch (e) {
                  setD(() => error = errorText(e));
                }
              },
              child: const Text('Speichern'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _toggleActive(Map<String, dynamic> d) async {
    try {
      await _api.adminSetActive(d['id'], d['active'] != true);
      _snack(d['active'] == true ? 'Fahrer gesperrt' : 'Fahrer freigegeben');
      _load();
    } catch (e) {
      _snack(errorText(e));
    }
  }

  Widget _card(String label, String value, Color c) => SizedBox(
        width: 150,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(value, style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: c)),
              Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
            ]),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final o = _overview;
    return Scaffold(
      appBar: AppBar(title: Text('Admin: ${AuthStore.name ?? ''}'), actions: [
        IconButton(tooltip: 'Aktualisieren', icon: const Icon(Icons.refresh), onPressed: _load),
        IconButton(tooltip: 'Abmelden', icon: const Icon(Icons.logout), onPressed: AuthStore.logout),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _createDriver,
        icon: const Icon(Icons.person_add),
        label: const Text('Fahrer anlegen'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 16, 16, 96), children: [
          if (_error != null)
            Text(_error!, style: const TextStyle(color: Colors.red)),
          if (o != null)
            Wrap(spacing: 8, runSpacing: 8, children: [
              _card('Fahrten heute', '${o['rides_today']}', Colors.blue),
              _card('Beendet heute', '${o['completed_today']}', Colors.blue),
              _card('Fahrer frei', '${o['drivers_free']}', Colors.green),
              _card('Fahrer unterwegs', '${o['drivers_busy']}', Colors.orange),
              _card('Fahrer offline', '${o['drivers_offline']}', Colors.grey),
              _card('Ø Bewertung', o['avg_rating'] == null ? '–' : '${o['avg_rating']} ★', Colors.amber),
              _card('Geteilt heute', '${o['pooled_today']} / ${o['shared_today']}', Colors.blue),
              _card('Gespart (30 T.)', '${o['saved_km_30d']} km', Colors.green),
              _card('Umsatz heute', euro(o['revenue_today'] as num), Colors.blue),
            ]),
          const SizedBox(height: 16),
          const Text('Fahrer (letzte 30 Tage)',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          if (_drivers.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text('Noch keine Fahrer. Legen Sie den ersten mit „Fahrer anlegen“ an.'),
            ),
          for (final d in _drivers)
            Card(
              child: ListTile(
                leading: Tooltip(
                  message: _statusText(d),
                  child: CircleAvatar(radius: 8, backgroundColor: _statusColor(d)),
                ),
                title: Text('${d['name']}  •  ${_statusText(d)}'),
                subtitle: Text(
                  '${d['vehicle']} • ${d['plate']}\n'
                  '${d['rating_avg'] == null ? 'keine Bewertung' : '★ ${d['rating_avg']} (${d['rating_count']})'}'
                  ' • ${d['rides']} Fahrten • ${d['km']} km\n'
                  'Geschwindigkeit: Ø ${d['avg_speed'] ?? '–'} km/h, max. ${d['max_speed'] ?? '–'} km/h',
                ),
                isThreeLine: true,
                trailing: PopupMenuButton<String>(
                  onSelected: (v) => v == 'toggle' ? _toggleActive(d) : _resetPassword(d),
                  itemBuilder: (_) => [
                    PopupMenuItem(
                        value: 'toggle',
                        child: Text(d['active'] == true ? 'Sperren' : 'Freigeben')),
                    const PopupMenuItem(value: 'pw', child: Text('Passwort zurücksetzen')),
                  ],
                ),
              ),
            ),
        ]),
      ),
    );
  }
}
