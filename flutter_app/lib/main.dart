import 'package:flutter/material.dart';
import 'screens/login_screen.dart';
import 'screens/role_home.dart';
import 'services/auth_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AuthStore.load();
  // Bei Abmeldung oder abgelaufener Sitzung zurück zum Login
  AuthStore.onLoggedOut = () {
    navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  };
  runApp(const FahrdienstApp());
}

class FahrdienstApp extends StatelessWidget {
  const FahrdienstApp({super.key});

  @override
  Widget build(BuildContext context) {
    final loggedIn = AuthStore.token != null && AuthStore.role != null;
    return MaterialApp(
      title: 'Fahrdienst',
      navigatorKey: navigatorKey,
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
      ),
      home: loggedIn ? homeForRole(AuthStore.role!) : const LoginScreen(),
    );
  }
}
