# Navigation, Musik und Zeitungen

## 1. Navigation für den Fahrer

Sobald der Fahrer eine Fahrt angenommen hat, erscheint auf seinem Bildschirm:

- **„Navigation zum Kunden“** (Abholung): öffnet die Route zum Standort des Kunden anhand der Koordinaten
- **„Navigation zu Ziel N“** (nach „Kunde abgeholt“): öffnet die Route zum nächsten der bis zu 4 Ziele

Der Fahrer wählt **Google Maps, Apple Karten (nur iPhone) oder Waze**. Die App startet die gewählte Navigations-App, die Navigation selbst übernimmt diese.

Hinweis: Die Ziele sind bisher Adresstexte. Google Maps und Waze suchen sie selbst. Für exakte Treffer ist später eine Adresssuche (Geocoding) beim Kunden sinnvoll (siehe Roadmap).

## 2. Musik im Fahrzeug

**Idee:** Der Admin pflegt Bibliotheken (jede ist eine Playlist). Der Fahrer wählt eine, startet sie und kann pausieren, überspringen, zurückgehen und die Reihenfolge mischen. Die Musik läuft über das Handy des Fahrers (Bluetooth oder Aux mit dem Fahrzeug verbunden).

### Admin (Webseite `/dashboard`, Reiter „Musik“)
1. Bibliothek anlegen (zum Beispiel „Entspannt“, „Morgens“).
2. Titel hochladen: MP3, M4A, OGG oder WAV bis 30 MB (`MAX_UPLOAD_MB`). MP3 ist am verträglichsten.
3. **Lizenznachweis eintragen (Pflicht)** und bestätigen, dass die Rechte vorliegen.
4. Titel anhören, löschen, Bibliothek mit allen Titeln löschen.

Das System prüft, dass es wirklich eine lesbare Audiodatei ist (eine umbenannte Textdatei wird abgelehnt). Dateien liegen mit Zufallsnamen im Docker-Volume `musicdata`. **Dieses Volume gehört in Ihre Datensicherung.**

### Fahrer-App
Der Player steht unten im Fahrer-Bildschirm. Er funktioniert auch im Wartezustand, ohne Fahrt.

### Musik über Bluetooth im Fahrzeug
Die App spielt die Musik über das **Handy des Fahrers** ab. So hört man sie im Fahrzeug:
1. Handy mit der Fahrzeug-Freisprecheinrichtung oder einem Bluetooth-Lautsprecher **koppeln** (Einstellungen des Handys, Bluetooth).
2. Playlist in der Fahrer-App starten. Das Handy leitet den Ton automatisch an das gekoppelte Gerät.
3. Lautstärke am Handy und am Fahrzeug einstellen.
Die App hat keine eigene Bluetooth-Funktion, sie nutzt die des Handys. Bei einem Anruf pausiert Android oder iOS die Wiedergabe in der Regel selbst. Damit die Musik weiterläuft, wenn die Navigation im Vordergrund ist, schalten Sie den Hintergrundbetrieb ein (Abschnitt 4).

### Rechtliches (keine Rechtsberatung)
- In Fahrzeugen mit Fahrgästen ist das Abspielen von Musik in Deutschland in der Regel **lizenzpflichtig** (zum Beispiel GEMA). Klären Sie das mit der GEMA oder Ihrem Anwalt, oder nutzen Sie ausschließlich Musik, für die Sie eine gewerbliche Lizenz haben (rechtefreie Musik, Anbieter mit Business-Lizenz).
- Private Abos von Streaming-Diensten dürfen meist nicht gewerblich genutzt werden.
- Das System speichert pro Titel Ihren Lizenznachweis, kontrolliert aber nicht, ob er stimmt.

### Technik
- Der Fahrer erhält pro Titel einen Stream-Link, der 12 Stunden gilt und nur für diesen Titel funktioniert. Er lässt sich nicht als Anmelde-Token verwenden.
- Der Server unterstützt Vor- und Zurückspulen (Range-Anfragen).
- Die Musik wird jedes Mal gestreamt und nicht auf dem Handy zwischengespeichert. Das verbraucht Datenvolumen (ca. 1 MB pro Minute bei MP3 mit 128 kbit/s).
- Im Reverse Proxy muss die Upload-Größe mindestens 35 MB erlauben (Nginx: `client_max_body_size 35m;`).

## 3. Zeitungen für Kunden

- Der Admin trägt im Reiter „Zeitungen“ RSS- oder Atom-Feeds ein (nur `https://`) und kann sie jederzeit aus- und einschalten oder per „Vorschau“ testen.
- Der Kunde sieht in seiner Fahrt den Button **„Zeitungen lesen“**, **nur wenn der Fahrer unterwegs zu ihm ist oder die Fahrt läuft**. Ohne Fahrt antwortet der Server mit „nur während einer Fahrt verfügbar“.
- Der Server liefert nur Titel, Kurztext und Link. Der Artikel öffnet sich in der Webseite der Zeitung, Bezahlschranken gelten weiterhin.
- **Rechte:** Viele Verlage erlauben ihre Feeds nur für private Nutzung. Prüfen Sie die Nutzungsbedingungen jeder Zeitung für den gewerblichen Einsatz, oder fragen Sie den Verlag.

### Schutz im Server
Feed-Adressen mit `http://`, internen Adressen (`localhost`, `192.168.x.x`, `10.x.x.x`, Cloud-Metadaten `169.254.x.x`), Zugangsdaten in der Adresse oder anderen Protokollen werden abgelehnt. Das gilt auch für Weiterleitungen. XML mit externen Entitäten wird verworfen, Feeds sind auf 2 MB und 8 Sekunden begrenzt, Links mit `javascript:` werden entfernt. Die Umgebungsvariable `NEWS_ALLOW_PRIVATE=1` ist nur für lokale Tests gedacht und darf in Produktion **nicht** gesetzt sein.

## 4. Hintergrundbetrieb einschalten (empfohlen für Fahrer)

Öffnet der Fahrer Google Maps, läuft die Fahrdienst-App im Hintergrund. Ohne Einrichtung stoppen dann **Musik und Standortmeldung**, und der Fahrer erhält keine Anfragen mehr. Deshalb gibt es den Schalter `BACKGROUND_MODE`:

```bash
flutter run --dart-define=BACKGROUND_MODE=true
```

Schalten Sie ihn erst ein, nachdem Sie die Plattformen eingerichtet haben, sonst kann die App beim Start abstürzen.

### Android (`android/app/src/main/AndroidManifest.xml`)
Vor `<application>`:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
<uses-permission android:name="android.permission.WAKE_LOCK"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK"/>
```
Innerhalb von `<application>` (und `xmlns:tools="http://schemas.android.com/tools"` im `<manifest>`-Tag):
```xml
<service android:name="com.ryanheise.audioservice.AudioService"
    android:foregroundServiceType="mediaPlayback"
    android:exported="true" tools:ignore="Instantiatable">
  <intent-filter><action android:name="android.media.browse.MediaBrowserService"/></intent-filter>
</service>
<receiver android:name="com.ryanheise.audioservice.MediaButtonReceiver"
    android:exported="true" tools:ignore="Instantiatable">
  <intent-filter><action android:name="android.intent.action.MEDIA_BUTTON"/></intent-filter>
</receiver>
```
`MainActivity` (Kotlin) muss von `AudioServiceActivity` erben:
```kotlin
import com.ryanheise.audioservice.AudioServiceActivity
class MainActivity : AudioServiceActivity()
```

### iOS (`ios/Runner/Info.plist`)
```xml
<key>UIBackgroundModes</key>
<array><string>audio</string><string>location</string></array>
<key>NSLocationWhenInUseUsageDescription</key>
<string>Ihr Standort wird für Fahrtanfragen in Ihrer Nähe benötigt.</string>
<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
<string>Ihr Standort wird auch bei geöffneter Navigation für Fahrtanfragen benötigt.</string>
```
Der Fahrer muss die Standortfreigabe auf „Immer“ stellen.

### Datenschutz
Mit Hintergrundbetrieb wird der Standort der Fahrer auch außerhalb der App-Ansicht übertragen, solange sie auf FREI oder unterwegs stehen. Das ist Beschäftigtendatenschutz: Rechtsgrundlage klären, Fahrer informieren, Löschfristen festlegen.

## 5. Verkehrssicherheit

Die Bedienung am Handy während der Fahrt ist riskant und teilweise verboten. Die App weist darauf hin, die Tasten sind groß, aber Sie sollten Fahrer anweisen, das Handy in eine Halterung zu legen und nur bei Stillstand zu bedienen.

## 6. Noch nicht enthalten

- Spracherkennung oder Lenkradtasten für die Musik
- Zwischenspeichern der Musik auf dem Handy (Offline-Betrieb)
- Adresssuche mit Koordinaten für die Ziele
- Musik- und Zeitungsverwaltung in der Flutter-Admin-Ansicht (nur auf der Webseite)
