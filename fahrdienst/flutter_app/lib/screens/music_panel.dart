import 'dart:async';
import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'package:just_audio_background/just_audio_background.dart';
import '../services/api_service.dart';

/// Musik-Player für den Fahrer: Playlist (Bibliothek) wählen, starten, pausieren, überspringen.
/// Die Musik kommt vom Server und läuft über das Handy (Bluetooth/AUX mit dem Fahrzeug verbunden).
class MusicPanel extends StatefulWidget {
  const MusicPanel({super.key});
  @override
  State<MusicPanel> createState() => _MusicPanelState();
}

class _MusicPanelState extends State<MusicPanel> {
  final _api = ApiService();
  final _player = AudioPlayer();
  final List<StreamSubscription> _subs = [];
  List<Map<String, dynamic>> _libs = [];
  List<Map<String, dynamic>> _tracks = [];
  int? _libId;
  int? _index;
  bool _loading = false;
  bool _shuffle = false;
  bool _started = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _subs.add(_player.currentIndexStream.listen((i) {
      if (mounted) setState(() => _index = i);
    }));
    _subs.add(_player.playbackEventStream.listen((_) {}, onError: (Object e, StackTrace st) {
      if (mounted) {
        setState(() => _error =
            'Wiedergabe fehlgeschlagen. Bitte Titel überspringen oder die Playlist neu starten.');
      }
    }));
    _loadLibraries();
  }

  @override
  void dispose() {
    for (final s in _subs) {
      s.cancel();
    }
    _player.dispose();
    super.dispose();
  }

  Future<void> _loadLibraries() async {
    try {
      final libs = await _api.musicLibraries();
      if (!mounted) return;
      setState(() {
        _libs = libs;
        _libId ??= libs.isNotEmpty ? libs.first['id'] as int : null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    }
  }

  Future<void> _start() async {
    final id = _libId;
    if (id == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final tracks = await _api.musicTracks(id);
      if (tracks.isEmpty) throw Exception('Diese Bibliothek ist leer');
      final sources = [
        for (final t in tracks)
          AudioSource.uri(
            Uri.parse('$baseUrl${t['stream_url']}'),
            tag: MediaItem(
              id: '${t['id']}',
              title: '${t['title']}',
              artist: '${t['artist']}'.isEmpty ? null : '${t['artist']}',
            ),
          ),
      ];
      await _player.setLoopMode(LoopMode.all);
      await _player.setShuffleModeEnabled(_shuffle);
      await _player.setAudioSource(ConcatenatingAudioSource(children: sources),
          initialIndex: 0);
      if (_shuffle) await _player.shuffle();
      unawaited(_player.play());
      if (mounted) {
        setState(() {
          _tracks = tracks;
          _started = true;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggleShuffle() async {
    setState(() => _shuffle = !_shuffle);
    await _player.setShuffleModeEnabled(_shuffle);
    if (_shuffle) await _player.shuffle();
  }

  @override
  Widget build(BuildContext context) {
    final current =
        (_index != null && _index! < _tracks.length) ? _tracks[_index!] : null;
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Row(children: [
            Icon(Icons.music_note),
            SizedBox(width: 8),
            Text('Musik im Fahrzeug',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          ]),
          const SizedBox(height: 8),
          if (_libs.isEmpty)
            const Text('Noch keine Musik vorhanden. Der Administrator legt Bibliotheken an.')
          else ...[
            DropdownButton<int>(
              isExpanded: true,
              value: _libId,
              items: [
                for (final l in _libs)
                  DropdownMenuItem(
                      value: l['id'] as int,
                      child: Text('${l['name']} (${l['tracks']} Titel)')),
              ],
              onChanged: (v) => setState(() => _libId = v),
            ),
            const SizedBox(height: 4),
            FilledButton.icon(
              onPressed: _loading ? null : _start,
              icon: _loading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.play_arrow),
              label: Text(_started ? 'Diese Playlist starten' : 'Playlist starten'),
            ),
            if (_started) ...[
              const SizedBox(height: 12),
              Text(current == null ? '–' : '${current['title']}',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
              if (current != null && '${current['artist']}'.isNotEmpty)
                Text('${current['artist']}'),
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                IconButton(
                    iconSize: 44,
                    tooltip: 'Zurück',
                    icon: const Icon(Icons.skip_previous),
                    onPressed: _player.seekToPrevious),
                StreamBuilder<PlayerState>(
                  stream: _player.playerStateStream,
                  builder: (context, snap) {
                    final playing = snap.data?.playing ?? false;
                    return IconButton(
                      iconSize: 60,
                      tooltip: playing ? 'Pause' : 'Abspielen',
                      icon: Icon(playing ? Icons.pause_circle : Icons.play_circle),
                      onPressed: playing ? _player.pause : _player.play,
                    );
                  },
                ),
                IconButton(
                    iconSize: 44,
                    tooltip: 'Überspringen',
                    icon: const Icon(Icons.skip_next),
                    onPressed: _player.seekToNext),
                IconButton(
                    iconSize: 32,
                    tooltip: 'Zufällige Reihenfolge',
                    color: _shuffle ? Theme.of(context).colorScheme.primary : Colors.grey,
                    icon: const Icon(Icons.shuffle),
                    onPressed: _toggleShuffle),
              ]),
            ],
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 4),
          const Text('Bitte nur bedienen, wenn das Fahrzeug steht.',
              style: TextStyle(fontSize: 12, color: Colors.grey)),
        ]),
      ),
    );
  }
}
