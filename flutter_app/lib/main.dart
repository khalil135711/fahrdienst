import 'package:flutter/material.dart';
<<<<<<< HEAD
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
=======
import 'screens/customer_home.dart';
import 'screens/driver_home.dart';

void main() => runApp(const FahrdienstApp());
>>>>>>> origin/main

class FahrdienstApp extends StatelessWidget {
  const FahrdienstApp({super.key});

  @override
  Widget build(BuildContext context) {
<<<<<<< HEAD
    final loggedIn = AuthStore.token != null && AuthStore.role != null;
    return MaterialApp(
      title: 'Fahrdienst',
      navigatorKey: navigatorKey,
=======
    return MaterialApp(
      title: 'Fahrdienst',
>>>>>>> origin/main
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
      ),
<<<<<<< HEAD
      home: loggedIn ? homeForRole(AuthStore.role!) : const LoginScreen(),
=======
      home: const RoleSelector(),
    );
  }
}

/// Einfache Rollenauswahl (später durch Login mit Rolle ersetzen).
class RoleSelector extends StatelessWidget {
  const RoleSelector({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Fahrdienst',
                style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold)),
            const SizedBox(height: 32),
            FilledButton(
              onPressed: () => Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const CustomerHome())),
              child: const Text('Ich bin Kunde'),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: () => Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const DriverHome())),
              child: const Text('Ich bin Fahrer'),
            ),
          ],
        ),
      ),
>>>>>>> origin/main
    );
  }
}
