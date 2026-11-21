import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../services/api_service.dart';

/// Zeigt ETA und Live-Status der Fahrt über WebSocket.
class TrackingScreen extends StatefulWidget {
  final int rideId;
  const TrackingScreen({super.key, required this.rideId});
  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
  late final WebSocketChannel _ch;

  @override
  void initState() {
    super.initState();
    _ch = WebSocketChannel.connect(
        Uri.parse('$wsBaseUrl/ws/rides/${widget.rideId}'));
  }

  @override
  void dispose() {
    _ch.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ihre Fahrt')),
      body: StreamBuilder(
        stream: _ch.stream,
        builder: (context, snap) {
          if (!snap.hasData) {
            return const Center(child: Text('Fahrer wird gesucht …'));
          }
          final d = jsonDecode(snap.data as String);
          return Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // TODO: GoogleMap-Widget mit Marker für d['lat'], d['lng']
                Text('Fahrer kommt in ${d['eta_minutes']} Min.',
                    style: const TextStyle(
                        fontSize: 28, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text('${d['driver_name']}  ★ ${d['driver_rating']}'),
                Text('${d['vehicle']}'),
              ],
            ),
          );
        },
      ),
    );
  }
}
