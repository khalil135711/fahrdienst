/// Hintergrundbetrieb für Fahrer: Musik und Standortmeldung laufen weiter,
/// auch wenn die Navigations-App im Vordergrund ist.
/// Erst einschalten, nachdem Android/iOS eingerichtet sind (docs/FUNKTIONEN.md):
///   flutter run --dart-define=BACKGROUND_MODE=true
const bool backgroundMode = bool.fromEnvironment('BACKGROUND_MODE');
