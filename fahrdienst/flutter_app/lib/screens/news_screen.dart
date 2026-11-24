import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/api_service.dart';

/// Zeitungen für den Kunden während der Fahrt (Schlagzeilen; Artikel öffnen auf der Webseite der Zeitung).
class NewsScreen extends StatefulWidget {
  const NewsScreen({super.key});
  @override
  State<NewsScreen> createState() => _NewsScreenState();
}

class _NewsScreenState extends State<NewsScreen> {
  late final Future<List<Map<String, dynamic>>> _future = ApiService().newsSources();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Zeitungen')),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) return _Message(errorText(snap.error!));
          final list = snap.data!;
          if (list.isEmpty) return const _Message('Es sind noch keine Zeitungen eingerichtet.');
          return ListView(children: [
            for (final s in list)
              ListTile(
                leading: const Icon(Icons.newspaper),
                title: Text('${s['name']}'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.push(
                    context, MaterialPageRoute(builder: (_) => NewsItemsScreen(source: s))),
              ),
          ]);
        },
      ),
    );
  }
}

class NewsItemsScreen extends StatefulWidget {
  final Map<String, dynamic> source;
  const NewsItemsScreen({super.key, required this.source});
  @override
  State<NewsItemsScreen> createState() => _NewsItemsScreenState();
}

class _NewsItemsScreenState extends State<NewsItemsScreen> {
  late final Future<List<Map<String, dynamic>>> _future =
      ApiService().newsItems(widget.source['id'] as int);

  String _date(dynamic iso) {
    final d = DateTime.tryParse('$iso')?.toLocal();
    if (d == null) return '';
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(d.day)}.${two(d.month)}. ${two(d.hour)}:${two(d.minute)}';
  }

  Future<void> _open(String link) async {
    final uri = Uri.tryParse(link);
    if (uri == null || (uri.scheme != 'https' && uri.scheme != 'http')) return;
    var ok = false;
    try {
      ok = await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
    } catch (_) {}
    if (!ok) {
      try {
        ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
      } catch (_) {}
    }
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Der Artikel konnte nicht geöffnet werden')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.source['name']}')),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) return _Message(errorText(snap.error!));
          final items = snap.data!;
          if (items.isEmpty) return const _Message('Keine Meldungen gefunden.');
          return ListView.separated(
            itemCount: items.length + 1,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, i) {
              if (i == items.length) {
                return const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('Artikel öffnen sich auf der Webseite der Zeitung.',
                      style: TextStyle(fontSize: 12, color: Colors.grey)),
                );
              }
              final it = items[i];
              final summary = '${it['summary'] ?? ''}';
              return ListTile(
                title: Text('${it['title']}',
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text([
                  if (summary.isNotEmpty) summary,
                  if (_date(it['published']).isNotEmpty) _date(it['published']),
                ].join('\n')),
                isThreeLine: summary.isNotEmpty,
                trailing: const Icon(Icons.open_in_new, size: 18),
                onTap: () => _open('${it['link']}'),
              );
            },
          );
        },
      ),
    );
  }
}

class _Message extends StatelessWidget {
  final String text;
  const _Message(this.text);
  @override
  Widget build(BuildContext context) =>
      Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(text, textAlign: TextAlign.center)));
}
