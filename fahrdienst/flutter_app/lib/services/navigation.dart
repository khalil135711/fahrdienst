import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// Ziel für die Navigation: entweder Koordinaten (Abholung) oder eine Adresse (Ziele).
class NavTarget {
  final String label;
  final double? lat;
  final double? lng;
  final String? address;
  const NavTarget({required this.label, this.lat, this.lng, this.address});

  bool get hasCoords => lat != null && lng != null;
  String get query => hasCoords ? '$lat,$lng' : (address ?? '');
}

Uri googleMapsUri(NavTarget t) => Uri.https('www.google.com', '/maps/dir/', {
      'api': '1',
      'destination': t.query,
      'travelmode': 'driving',
      'dir_action': 'navigate',
    });

Uri appleMapsUri(NavTarget t) =>
    Uri.https('maps.apple.com', '/', {'daddr': t.query, 'dirflg': 'd'});

Uri wazeUri(NavTarget t) => t.hasCoords
    ? Uri.https('waze.com', '/ul', {'ll': '${t.lat},${t.lng}', 'navigate': 'yes'})
    : Uri.https('waze.com', '/ul', {'q': t.query, 'navigate': 'yes'});

/// Fragt, mit welcher Navi-App geöffnet werden soll, und startet sie.
Future<void> openNavigation(BuildContext context, NavTarget t) async {
  final apple = defaultTargetPlatform == TargetPlatform.iOS ||
      defaultTargetPlatform == TargetPlatform.macOS;
  final choice = await showModalBottomSheet<Uri>(
    context: context,
    builder: (ctx) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        ListTile(
          title: Text('Navigation zu: ${t.label}',
              style: const TextStyle(fontWeight: FontWeight.bold)),
          subtitle: t.hasCoords ? null : Text(t.query),
        ),
        ListTile(
          leading: const Icon(Icons.map),
          title: const Text('Google Maps'),
          onTap: () => Navigator.pop(ctx, googleMapsUri(t)),
        ),
        if (apple)
          ListTile(
            leading: const Icon(Icons.map_outlined),
            title: const Text('Apple Karten'),
            onTap: () => Navigator.pop(ctx, appleMapsUri(t)),
          ),
        ListTile(
          leading: const Icon(Icons.alt_route),
          title: const Text('Waze'),
          onTap: () => Navigator.pop(ctx, wazeUri(t)),
        ),
      ]),
    ),
  );
  if (choice == null) return;
  var ok = false;
  try {
    ok = await launchUrl(choice, mode: LaunchMode.externalApplication);
  } catch (_) {}
  if (!ok && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Die Navigation konnte nicht geöffnet werden')));
  }
}
