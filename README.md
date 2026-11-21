# 🚕 Fahrdienst – Dispatch- und Verwaltungssystem

Ein System für den eigenen Kunden-Fahrdienst: Kunden fordern eine Fahrt an, der nächste freie Fahrer übernimmt sie, der Kunde sieht ETA und Live-Position, und die Verwaltung behält Geschwindigkeit, Kilometer und Bewertungen im Blick.

> **Status:** Prototyp / Grundgerüst (v0.1). Die Bilder unten sind **Design-Vorschauen (Mockups)** und keine echten App-Screenshots. Ersetzen Sie sie nach dem ersten Build durch echte Screenshots (siehe [Screenshots ersetzen](#screenshots-ersetzen)).

## Funktionen

- **Kunde:** Fahrt anfragen, Fahrer mit Bewertung und ETA sehen, Live-Tracking, Fahrer bewerten
- **Fahrer:** Status *frei/offline*, Anfragen in der Nähe annehmen oder ablehnen, Position und Geschwindigkeit werden übertragen
- **Admin:** Live-Karte, gefahrene Kilometer, Geschwindigkeit, Fahrtenanzahl, Bewertungen, Warnungen
- **Abfahrt und Ziele:** Die Abfahrt ist automatisch der aktuelle GPS-Standort des Kunden. Pro Fahrt sind **1 bis 4 Ziele** möglich, die der Reihe nach angefahren werden. Der Fahrer meldet jedes erreichte Ziel, nach dem letzten endet die Fahrt.
- **Zuweisung:** Anfrage geht an den nächsten freien Fahrer im Umkreis (5 km), bei Ablehnung oder Timeout an den nächsten

## Screenshots

### Kunden-App

| Fahrt anfragen (Abfahrt + 4 Ziele) | Live-Tracking mit Zielliste | Bewertung |
|:---:|:---:|:---:|
| <img src="docs/images/01_kunde_anfrage.png" width="240"> | <img src="docs/images/02_kunde_tracking.png" width="240"> | <img src="docs/images/04_kunde_bewertung.png" width="240"> |

### Fahrer-App

| Neue Anfrage |
|:---:|
| <img src="docs/images/03_fahrer_anfrage.png" width="240"> |

### Admin-Dashboard

![Admin-Dashboard](docs/images/05_admin_dashboard.png)

## Architektur

![Architektur](docs/images/06_architektur.png)

Die Datenbank läuft in einem eigenen VLAN hinter OPNsense, siehe [docs/OPNSENSE.md](docs/OPNSENSE.md).

## Projektstruktur

```
fahrdienst/
├── flutter_app/          Flutter-App (Kunde + Fahrer)
│   ├── pubspec.yaml
│   └── lib/
│       ├── main.dart
│       ├── models/ride.dart
│       ├── services/api_service.dart
│       └── screens/      customer_home, tracking_screen, driver_home
├── backend/              FastAPI + PostgreSQL/PostGIS + Redis
│   ├── app/main.py
│   ├── schema.sql
│   ├── docker-compose.yml
│   └── Dockerfile
└── docs/                 Bilder und OPNsense-Anleitung
```

## Installation

### Backend

```bash
cd backend
cp .env.example .env        # Passwort ändern!
docker compose up -d
# API: http://localhost:8000/docs
```

### Flutter-App

```bash
cd flutter_app
flutter create .            # erzeugt android/ und ios/ Ordner
flutter pub get
flutter run
```

Standortberechtigung eintragen:

- **Android:** in `android/app/src/main/AndroidManifest.xml` die Berechtigungen `ACCESS_FINE_LOCATION` und `ACCESS_COARSE_LOCATION` hinzufügen
- **iOS:** in `ios/Runner/Info.plist` den Schlüssel `NSLocationWhenInUseUsageDescription` mit einem Erklärungstext hinzufügen

Die API-Adresse wird beim Start übergeben (es gibt keine echte Domain im Code):

| Gerät | Befehl |
|---|---|
| Android-Emulator | `flutter run` (Standard: `http://10.0.2.2:8000`) |
| Echtes Handy im WLAN | `flutter run --dart-define=API_URL=http://<IP-des-PCs>:8000` |
| Flutter Web / Chrome | `flutter run -d chrome --dart-define=API_URL=http://localhost:8000` |
| Produktion | `--dart-define=API_URL=https://ihre-domain.de` |

**Fehler „failed to fetch“?** Prüfen: Läuft das Backend (`http://localhost:8000/health` im Browser)? Stimmt die IP, und erlaubt die Firewall Port 8000? Bei Klartext-HTTP auf Android 9+ in `AndroidManifest.xml` `android:usesCleartextTraffic="true"` setzen (nur zum Testen, in Produktion HTTPS verwenden).

Google-Maps-Schlüssel nach Bedarf eintragen. Das Backend legt beim ersten Start Testdaten an (`backend/seed.sql`: ein Kunde, ein freier Fahrer in Bonn).

## Screenshots ersetzen

1. App im Emulator starten (`flutter run`)
2. Screenshot erstellen, zum Beispiel mit `adb exec-out screencap -p > docs/images/01_kunde_anfrage.png`
3. Dateien in `docs/images/` mit gleichem Namen überschreiben

## Noch offen (Roadmap)

- [ ] Zielsuche mit Adressvorschlägen (Geocoding), damit `lat`/`lng` der Ziele automatisch gesetzt werden
- [ ] Route und ETA über alle Ziele hinweg berechnen
- [ ] Login und JWT-Authentifizierung mit Rollen
- [ ] Anfrage nacheinander per Push (Firebase) an Fahrer senden, 15-Sek.-Timeout
- [ ] Google-Map-Widget und Live-Marker im Tracking-Screen
- [ ] WebSocket-Endpunkt `/ws/rides/{id}` im Backend
- [ ] ETA-Berechnung (Google Directions, Mapbox oder OSRM)
- [ ] Admin-Dashboard (React) mit echten Daten
- [ ] Geschwindigkeitswarnungen und Statistik-Auswertungen
- [ ] Zahlungen

## Rechtliches (Deutschland)

- **DSGVO:** Standort- und Geschwindigkeitsüberwachung von Fahrern ist Beschäftigtendatenschutz. Rechtsgrundlage klären, gegebenenfalls Betriebsrat einbinden, Positionsdaten nach fester Frist löschen (siehe Kommentar in `schema.sql`).
- **PBefG:** Entgeltliche Personenbeförderung braucht in der Regel eine Genehmigung. Vorab mit der zuständigen Behörde oder einem Anwalt klären.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Bitte Namen in der Lizenzdatei anpassen.
