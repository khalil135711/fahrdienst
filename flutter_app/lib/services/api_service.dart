import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/ride.dart';
import 'auth_store.dart';

/// Adresse des API-Servers. Beim Start setzen:
///   flutter run --dart-define=API_URL=http://192.168.1.50:8000
/// Standard: Android-Emulator -> Rechner (localhost des PCs).
const String baseUrl =
    String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

class ApiService {
  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (AuthStore.token != null) 'Authorization': 'Bearer ${AuthStore.token}',
      };

  Uri _u(String path) => Uri.parse('$baseUrl$path');

  /// Wirft bei Fehlern eine verständliche Exception.
  dynamic _check(http.Response r) {
    if (r.statusCode >= 200 && r.statusCode < 300) {
      return r.body.isEmpty ? null : jsonDecode(r.body);
    }
    // Sitzung abgelaufen oder Konto gesperrt -> zurück zum Login
    if (r.statusCode == 401 && AuthStore.token != null) {
      AuthStore.logout();
      throw Exception('Bitte erneut anmelden');
    }
    String msg = 'Fehler ${r.statusCode}';
    try {
      final d = jsonDecode(r.body);
      if (d is Map && d['detail'] is String) {
        msg = d['detail'];
      } else if (d is Map && d['detail'] is List && d['detail'].isNotEmpty) {
        msg = 'Ungültige Eingabe: ${d['detail'][0]['msg']}';
      }
    } catch (_) {}
    throw Exception(msg);
  }

  // ---------- Anmeldung ----------

  Future<void> login(String email, String password) async {
    final r = await http.post(_u('/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}));
    final d = Map<String, dynamic>.from(_check(r));
    await AuthStore.save(d['token'], d['role'], d['name']);
  }

  /// Registrierung ist nur für Kunden möglich.
  Future<void> register(String name, String email, String password) async {
    final r = await http.post(_u('/auth/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'name': name, 'email': email, 'password': password}));
    final d = Map<String, dynamic>.from(_check(r));
    await AuthStore.save(d['token'], d['role'], d['name']);
  }

  // ---------- Kunde ----------

  /// [lat]/[lng] = aktueller Standort des Kunden (Abfahrt), [stops] = 1 bis 4 Ziele.
  Future<Ride> requestRide({
    required double lat,
    required double lng,
    required List<String> stops,
  }) async {
    assert(stops.isNotEmpty && stops.length <= 4);
    final r = await http.post(_u('/rides'),
        headers: _headers,
        body: jsonEncode({
          'lat': lat,
          'lng': lng,
          'stops': stops.map((a) => {'address': a}).toList(),
        }));
    return Ride.fromJson(_check(r));
  }

  /// Status, Fahrer, ETA, Ziele. Regelmäßig abfragen (alle 2 Sek.).
  Future<Map<String, dynamic>> getRide(int id) async =>
      Map<String, dynamic>.from(_check(await http.get(_u('/rides/$id'), headers: _headers)));

  Future<void> rateRide(int id, int stars, String comment) async => _check(
      await http.post(_u('/rides/$id/rating'),
          headers: _headers,
          body: jsonEncode({'stars': stars, 'comment': comment})));

  // ---------- Fahrer ----------

  Future<void> setDriverStatus(bool free) async => _check(await http.post(
      _u('/drivers/me/status'),
      headers: _headers,
      body: jsonEncode({'status': free ? 'free' : 'offline'})));

  Future<void> sendLocation(double lat, double lng, double speedKmh) async =>
      _check(await http.post(_u('/drivers/me/location'),
          headers: _headers,
          body: jsonEncode({'lat': lat, 'lng': lng, 'speed_kmh': speedKmh})));

  /// Liefert {offer: ..., active: ...}. Regelmäßig abfragen.
  Future<Map<String, dynamic>> driverState() async => Map<String, dynamic>.from(
      _check(await http.get(_u('/drivers/me/state'), headers: _headers)));

  Future<void> acceptRide(int id) async =>
      _check(await http.post(_u('/rides/$id/accept'), headers: _headers));

  Future<void> declineRide(int id) async =>
      _check(await http.post(_u('/rides/$id/decline'), headers: _headers));

  Future<void> startRide(int id) async =>
      _check(await http.post(_u('/rides/$id/start'), headers: _headers));

  Future<void> stopReached(int id, int position) async => _check(
      await http.post(_u('/rides/$id/stops/$position/reached'), headers: _headers));

  // ---------- Admin ----------

  Future<Map<String, dynamic>> adminOverview() async => Map<String, dynamic>.from(
      _check(await http.get(_u('/admin/overview'), headers: _headers)));

  Future<List<Map<String, dynamic>>> adminDrivers() async {
    final d = _check(await http.get(_u('/admin/drivers'), headers: _headers)) as List;
    return d.map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<void> adminCreateDriver({
    required String name,
    required String email,
    required String password,
    required String vehicleModel,
    required String plate,
  }) async =>
      _check(await http.post(_u('/admin/drivers'),
          headers: _headers,
          body: jsonEncode({
            'name': name,
            'email': email,
            'password': password,
            'vehicle_model': vehicleModel,
            'plate': plate,
          })));

  Future<void> adminSetActive(int id, bool active) async => _check(
      await http.patch(_u('/admin/drivers/$id'),
          headers: _headers, body: jsonEncode({'active': active})));

  Future<void> adminResetPassword(int id, String password) async => _check(
      await http.post(_u('/admin/drivers/$id/password'),
          headers: _headers, body: jsonEncode({'password': password})));
}
