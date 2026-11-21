import 'package:flutter/material.dart';
import 'screens/customer_home.dart';
import 'screens/driver_home.dart';

void main() => runApp(const FahrdienstApp());

class FahrdienstApp extends StatelessWidget {
  const FahrdienstApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fahrdienst',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
      ),
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
    );
  }
}
