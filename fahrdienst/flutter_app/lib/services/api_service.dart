import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import '../models/ride.dart';
import 'auth_store.dart';

const String _apiUrlFromEnv = String.fromEnvironment('API_URL');

/// Adresse des API-Servers. Beim Start setzen:
///   flutter run --dart-define=API_URL=http://192.168.1.50:8000
/// Ohne Angabe: Browser -> http://localhost:8000,
/// Android-Emulator -> http://10.0.2.2:8000 (so erreicht der Emulator den eigenen Rechner).
String get baseUrl {
  final url = _apiUrlFromEnv.isNotEmpty
      ? _apiUrlFromEnv
      : (kIsWeb ? 'http://localhost:8000' : 'http://10.0.2.2:8000');
  // Schrägstrich am Ende entfernen, sonst entsteht "//auth/login" und der Server meldet "Not Found"
  return url.replaceAll(RegExp(r'/+$'), '');
}

/// Betrag als Euro-Text, z. B. 12,90 €
String euro(num v) => '${v.toStringAsFixed(2).replaceAll('.', ',')} €';

/// Verständliche Fehlermeldung für die Anzeige in der App.
String errorText(Object e) {
  final s = '$e';
  if (s.contains('Failed to fetch') ||
      s.contains('SocketException') ||
      s.contains('ClientException') ||
      s.contains('Connection refused') ||
      s.contains('TimeoutException')) {
    return 'Server nicht erreichbar ($baseUrl). '
        'Läuft das Backend, und stimmt die Adresse?';
  }
  return s.replaceFirst('Exception: ', '');
}

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

  /// [lat]/[lng] = aktueller Standort des Kunden (Abfahrt).
  /// [stops] = 1 bis 4 Ziele mit Koordinaten aus der Adresssuche: {'address', 'lat', 'lng'}.
  /// [shared] = geteilte Fahrt (günstiger). [vehicleType] = 'normal' oder 'wheelchair'.
  /// [paymentMethod] = 'km' oder 'taxischein' (dann [voucherNo]).
  /// [allowPartner] = auch Fahrer von Partnerfirmen zulassen.
  Future<Ride> requestRide({
    required double lat,
    required double lng,
    required List<Map<String, dynamic>> stops,
    bool shared = false,
    String vehicleType = 'normal',
    String paymentMethod = 'km',
    String? voucherNo,
    bool allowPartner = false,
  }) async {
    assert(stops.isNotEmpty && stops.length <= 4);
    final r = await http.post(_u('/rides'),
        headers: _headers,
        body: jsonEncode({
          'lat': lat,
          'lng': lng,
          'stops': stops,
          'shared': shared,
          'vehicle_type': vehicleType,
          'payment_method': paymentMethod,
          'voucher_no': voucherNo,
          'allow_partner': allowPartner,
        }));
    return Ride.fromJson(_check(r));
  }

  /// Preis VOR der Fahrt: {distance_km, duration_min, own, own_shared, partner, partners_available, ...}
  Future<Map<String, dynamic>> quote({
    required double lat,
    required double lng,
    required List<Map<String, dynamic>> stops,
    String vehicleType = 'normal',
  }) async =>
      Map<String, dynamic>.from(_check(await http.post(_u('/rides/quote'),
          headers: _headers,
          body: jsonEncode(
              {'lat': lat, 'lng': lng, 'stops': stops, 'vehicle_type': vehicleType}))));

  /// Kurzlebiger Link zur Quittung (PDF), relativ zu [baseUrl].
  Future<String> receiptLink(int rideId) async {
    final d = Map<String, dynamic>.from(
        _check(await http.post(_u('/rides/$rideId/receipt-link'), headers: _headers)));
    return '$baseUrl${d['url']}';
  }

  /// Adresssuche: [{label, lat, lng}]
  Future<List<Map<String, dynamic>>> geoSearch(String q) async => _list(_check(
      await http.get(_u('/geo/search').replace(queryParameters: {'q': q}), headers: _headers)));

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

  // ---------- Musik (Fahrer) ----------

  Future<List<Map<String, dynamic>>> musicLibraries() async => _list(
      _check(await http.get(_u('/music/libraries'), headers: _headers)));

  /// Titel einer Bibliothek, jeder mit kurzlebigem 'stream_url' (relativ zu [baseUrl]).
  Future<List<Map<String, dynamic>>> musicTracks(int libraryId) async => _list(
      _check(await http.get(_u('/music/libraries/$libraryId/tracks'), headers: _headers)));

  // ---------- Zeitungen (Kunde, nur während der Fahrt) ----------

  Future<List<Map<String, dynamic>>> newsSources() async =>
      _list(_check(await http.get(_u('/news/sources'), headers: _headers)));

  Future<List<Map<String, dynamic>>> newsItems(int sourceId) async => _list(
      _check(await http.get(_u('/news/sources/$sourceId/items'), headers: _headers)));

  List<Map<String, dynamic>> _list(dynamic d) =>
      (d as List).map((e) => Map<String, dynamic>.from(e)).toList();
}
