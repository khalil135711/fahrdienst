import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/ride.dart';

/// Adresse des API-Servers. Beim Start setzen:
///   flutter run --dart-define=API_URL=http://192.168.1.50:8000
/// Standard: Android-Emulator -> Rechner (localhost des PCs).
const String baseUrl =
    String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

/// WebSocket-Adresse passend zur API-URL (http -> ws, https -> wss).
String get wsBaseUrl => baseUrl.replaceFirst('http', 'ws');

class ApiService {
  final String? token;
  ApiService({this.token});

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  /// [lat]/[lng] = aktueller Standort des Kunden (Abfahrt).
  /// [stops] = 1 bis 4 Ziele in Reihenfolge.
  Future<Ride> requestRide({
    required double lat,
    required double lng,
    required List<String> stops,
  }) async {
    assert(stops.isNotEmpty && stops.length <= 4);
    final r = await http.post(
      Uri.parse('$baseUrl/rides'),
      headers: _headers,
      body: jsonEncode({
        'lat': lat,
        'lng': lng,
        'stops': stops.map((a) => {'address': a}).toList(),
      }),
    );
    if (r.statusCode != 200) throw Exception('Anfrage fehlgeschlagen');
    return Ride.fromJson(jsonDecode(r.body));
  }

  Future<void> setDriverStatus(bool free) async {
    await http.post(Uri.parse('$baseUrl/drivers/me/status'),
        headers: _headers, body: jsonEncode({'status': free ? 'free' : 'offline'}));
  }

  Future<void> sendLocation(double lat, double lng, double speedKmh) async {
    await http.post(Uri.parse('$baseUrl/drivers/me/location'),
        headers: _headers,
        body: jsonEncode({'lat': lat, 'lng': lng, 'speed_kmh': speedKmh}));
  }

  Future<void> acceptRide(int id) async => http.post(
      Uri.parse('$baseUrl/rides/$id/accept'), headers: _headers);

  Future<void> rateRide(int id, int stars, String comment) async => http.post(
      Uri.parse('$baseUrl/rides/$id/rating'),
      headers: _headers,
      body: jsonEncode({'stars': stars, 'comment': comment}));
}
