# Anmeldung und Rollen

## Rollen

| Rolle | Wie entsteht das Konto? | Darf |
|---|---|---|
| **customer** (Kunde) | Selbstregistrierung in der App | Fahrt anfragen, eigene Fahrt ansehen, Fahrer bewerten |
| **driver** (Fahrer) | nur durch den Admin | Status frei/offline, Anfragen annehmen oder ablehnen, Fahrt durchführen |
| **admin** | wird beim ersten Start aus `ADMIN_EMAIL` und `ADMIN_PASSWORD` in `.env` angelegt | Fahrer anlegen, sperren, Passwort zurücksetzen, Übersicht und Statistik |

Die Rolle kommt immer aus der Datenbank, nicht aus dem Token. Ein Fahrer kann sich also nicht selbst zum Admin machen.

## Ablauf

1. `POST /auth/login` mit E-Mail und Passwort liefert ein Token (gültig 12 Stunden, einstellbar mit `TOKEN_HOURS`).
2. Die App sendet es bei jeder Anfrage als `Authorization: Bearer <token>`.
3. Gespeichert wird das Token mit `flutter_secure_storage` (Keychain auf iOS, Keystore auf Android).
4. Läuft das Token ab oder wird das Konto gesperrt, leitet die App automatisch zum Login.

## Schutzmaßnahmen im Backend

- Passwörter werden mit **bcrypt** gespeichert, nie im Klartext. Mindestens 8 Zeichen.
- **Fehlversuch-Sperre:** Nach 5 falschen Passwörtern ist das Konto 15 Minuten gesperrt.
- Gleiche Fehlermeldung und Antwortzeit bei falscher E-Mail oder falschem Passwort, damit niemand herausfinden kann, welche E-Mails existieren.
- **Sofortige Sperre:** Wird ein Fahrer gesperrt, sind seine Token sofort ungültig und er erhält keine Anfragen mehr.
- **Zugriffsschutz:** Kunden sehen nur ihre eigenen Fahrten, Fahrer nur ihnen zugewiesene Fahrten, der Admin alle.
- Token-Prüfung mit festem Algorithmus (HS256). Abgelaufene, manipulierte und `alg=none`-Token werden abgelehnt.
- Der Server startet nicht ohne `JWT_SECRET` (mindestens 32 Zeichen).

## Wichtig für den Betrieb

- **Nur über HTTPS betreiben.** Ohne Verschlüsselung können Token und Passwörter mitgelesen werden. TLS-Zertifikat am Reverse Proxy auf OPNsense (siehe `OPNSENSE.md`).
- `JWT_SECRET` mit `openssl rand -hex 32` erzeugen und geheim halten. Wird er geändert, müssen sich alle neu anmelden.
- `ADMIN_PASSWORD` nach dem ersten Start in der App-Verwaltung nicht mehr nötig. Entfernen Sie es danach aus `.env`.
- `CORS_ORIGINS` in Produktion auf die eigene Web-Adresse setzen, nicht `*`.
- Port 8000 nicht direkt ins Internet stellen, nur den HTTPS-Proxy.

## Noch nicht enthalten

- Passwort selbst ändern, „Passwort vergessen“ per E-Mail
- Zwei-Faktor-Anmeldung für Admins
- Token-Erneuerung (Refresh-Token); aktuell meldet sich ein Nutzer nach 12 Stunden neu an
- Protokoll der Admin-Aktionen (Audit-Log)
