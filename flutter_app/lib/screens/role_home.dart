import 'package:flutter/material.dart';
import 'admin_home.dart';
import 'customer_home.dart';
import 'driver_home.dart';

/// Leitet nach Rolle (kommt vom Server) auf den passenden Bildschirm.
Widget homeForRole(String role) {
  switch (role) {
    case 'admin':
      return const AdminHome();
    case 'driver':
      return const DriverHome();
    default:
      return const CustomerHome();
  }
}
