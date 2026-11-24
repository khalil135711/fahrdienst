import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Wird für die Weiterleitung zum Login benötigt (auch aus dem ApiService heraus).
final navigatorKey = GlobalKey<NavigatorState>();

/// Speichert Token, Rolle und Name sicher auf dem Gerät.
class AuthStore {
  static const _s = FlutterSecureStorage();
  static String? token;
  static String? role; // customer | driver | admin
  static String? name;

  /// Wird bei Abmeldung oder abgelaufener Sitzung aufgerufen (setzt main.dart).
  static void Function()? onLoggedOut;

  static Future<void> load() async {
    try {
      token = await _s.read(key: 'token');
      role = await _s.read(key: 'role');
      name = await _s.read(key: 'name');
    } catch (_) {
      token = role = name = null;
    }
  }

  static Future<void> save(String t, String r, String n) async {
    token = t;
    role = r;
    name = n;
    await _s.write(key: 'token', value: t);
    await _s.write(key: 'role', value: r);
    await _s.write(key: 'name', value: n);
  }

  static Future<void> clear() async {
    token = role = name = null;
    try {
      await _s.deleteAll();
    } catch (_) {}
  }

  static Future<void> logout() async {
    await clear();
    onLoggedOut?.call();
  }
}
