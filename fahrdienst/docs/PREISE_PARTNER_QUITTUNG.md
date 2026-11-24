# Tarife, Partnerfirmen und Quittung

## Preise vor der Buchung

Der Kunde sieht den Preis **bevor** er bucht. Es gibt zwei Fälle, je nachdem, wer die Fahrt fährt:

| Fahrer | Was der Kunde uns zahlt | Wie der Fahrpreis läuft |
|---|---|---|
| **Unser eigener Fahrer** | Anfahrtskosten **4 €** (Normalfahrzeug) oder **10 €** (Rollstuhlfahrzeug) plus Kilometer | Abrechnung **nach Kilometern** oder per **Taxischein** |
| **Fahrer einer Partnerfirma** | nur eine **Servicegebühr von 3 bis 6 €** (3 € plus 0,15 € pro km, höchstens 6 €) | Der Kunde rechnet den Fahrpreis **direkt mit dem Fahrer** ab (Taxameter oder Taxischein) |

**Reihenfolge der Zuteilung:** Unsere eigenen Fahrer werden immer **zuerst** gefragt. Eine Fahrt geht nur dann an einen Partnerfahrer, wenn der Kunde bei der Buchung **„Auch Partnerfirmen zulassen“** eingeschaltet hat (Standard: aus) und kein eigener Fahrer annimmt. Die App zeigt dem Kunden beide Preise vorher.

**Fahrzeugtypen:** Normalfahrten gehen nur an Normalfahrzeuge, Rollstuhlfahrten nur an Rollstuhlfahrzeuge. Rollstuhlfahrten werden **nicht** geteilt.

**Geteilte Fahrt (nur eigene Normalfahrzeuge und erlaubte Partner):** Der Rabatt (Standard 30 %) gilt auf den Gesamtpreis inklusive Anfahrtskosten. Mehr dazu in `TEILEN.md`.

## Wichtige Annahmen, bitte bestätigen

Ihre Vorgaben ließen einige Punkte offen. Ich habe sie so umgesetzt. Alles ist unter „Preise & Teilen“ einstellbar:

1. **Kilometerpreis:** Er fehlte in Ihrer Angabe. **2,20 € pro km ist nur ein Platzhalter.** Bitte eintragen.
2. **Servicegebühr 3 bis 6 €:** Sie steigt mit der Strecke von 3 € (0,15 € pro km) bis höchstens 6 € (ab 20 km). Wollen Sie eine feste Gebühr, setzen Sie Minimum und Maximum gleich.
3. **„3 € pro Fahrt“ für Firmen:** Die Partnerfirma zahlt uns **zusätzlich** pro beendeter Fahrt 3 € (pro Firma änderbar, 0 = keine Gebühr). Der Kunde zahlt davon unabhängig die Servicegebühr. Wollten Sie nur eine der beiden Gebühren, setzen Sie die andere auf 0.
4. **Taxischein:** Die Fahrt wird mit der Scheinnummer erfasst, der Preis nach Tarif berechnet und der Betrag **mit dem Kostenträger abgerechnet**. Die App nimmt an, dass der Schein die Fahrt voll deckt. Regeln unterscheiden sich je nach Stadt und Kostenträger, bitte prüfen.
5. **Festpreis bei Buchung:** Strecke und Preis werden vor der Fahrt aus den Zielen berechnet (Luftlinie × 1,3). Es gibt kein Taxameter und keine Nachberechnung nach gefahrenen Kilometern.
6. **Kein Bezahlsystem:** Preise werden berechnet, angezeigt, gespeichert und auf der Quittung ausgewiesen, aber nicht abgebucht. Das Bezahlen (bar beim Fahrer, Rechnung, Karte) müssen Sie bisher selbst regeln.

## Einstellungen (Admin-Webseite, Reiter „Preise & Teilen“)

| Einstellung | Standard |
|---|---|
| Anfahrtskosten Normalfahrzeug / Rollstuhlfahrzeug | 4,00 € / 10,00 € |
| Preis pro Kilometer | 2,20 € (Platzhalter) |
| Rabatt für geteilte Fahrt | 30 % |
| Servicegebühr Partnerfirma: Minimum / Maximum / Aufschlag pro km | 3,00 € / 6,00 € / 0,15 € |
| Gebühr pro Fahrt, die eine Partnerfirma an uns zahlt | 3,00 € |
| Umsatzsteuer auf Fahrpreise / auf Servicegebühr | 7 % / 19 % (Platzhalter) |
| Firmenname, Anschrift, Steuernummer, Telefon (für die Quittung) | Platzhalter |
| Plätze, Umweg-Grenzen, Suchradius, eigene Kosten pro km | siehe `TEILEN.md` |

Änderungen gelten sofort für **neue** Buchungen. Bereits gebuchte Fahrten behalten den Preis vom Zeitpunkt der Buchung.

## Partnerfirmen

**Admin-Webseite, Reiter „Firmen“:**
- Firma anlegen (Name, Kontakt, Anschrift, optional eigene Gebühr pro Fahrt)
- Fahrer der Firma unter „Fahrer“ anlegen: Firma und Fahrzeugtyp (Normal oder Rollstuhl) wählen
- Gebühr pro Firma ändern oder auf Standard zurücksetzen
- Firma **ausschalten**: Ihre Fahrer gehen sofort offline und erhalten keine Anfragen mehr
- **Monatsabrechnung** pro Firma: beendete Fahrten, Kilometer, Gebühr, Gesamtsumme, als **CSV-Datei** herunterladbar (öffnet in Excel)
- Unter „Live“: Partnerfahrten und Partnergebühren heute und der letzten 30 Tage

**Beim Fahrer:** Der Fahrer einer Partnerfirma sieht „Fahrpreis direkt mit dem Fahrgast abrechnen. Unsere Servicegebühr wird separat berechnet.“ Unsere eigenen Fahrer sehen den Betrag oder die Taxischein-Nummer.

**Noch nicht enthalten:** Ein eigenes Konto oder Portal für die Firmen. Den Zugang der Fahrer legt der Admin an.

## Quittung als PDF

Nach Ende der Fahrt erscheint beim Kunden der Button **„Quittung als PDF herunterladen“**. Er öffnet das PDF im Browser, dort kann es gespeichert oder geteilt werden.

**Inhalt:** Aussteller (Firmenname, Anschrift, Steuernummer, Telefon), laufende Nummer (`Q-JJJJ-NNNNNN`), Datum und Uhrzeit (deutsche Zeit), Fahrgast, Ziele, Strecke, Fahrzeug, Fahrer (bei Partnerfirma mit Firma), Positionen mit Beträgen, Gesamtbetrag brutto, enthaltene Umsatzsteuer, Zahlungsart.

Je nach Fahrt:
- **Eigener Fahrer, Kilometer:** Anfahrtskosten, Strecke, bei geteilter Fahrt der Rabatt
- **Taxischein:** zusätzlich „Bezahlt mit Taxischein Nr. …, Betrag wird mit dem Kostenträger abgerechnet“
- **Partnerfirma:** nur die Servicegebühr, mit dem Hinweis, dass das Unternehmen für den Fahrpreis eine eigene Quittung ausstellt

**Sicherheit:** Der Download-Link gilt **10 Minuten** und öffnet nur diese eine Quittung. Nur der Kunde der Fahrt und der Admin erhalten einen Link. Die Quittungsnummer wird beim Fahrtende vergeben und ist eindeutig und aufsteigend.

### Bitte mit dem Steuerberater klären
- Die Steuersätze (7 % auf Fahrpreise, 19 % auf die Servicegebühr) sind **Platzhalter**.
- Eine **Quittung** ist ein Zahlungsbeleg. Für Firmenkunden brauchen Sie ggf. eine **Rechnung** mit weiteren Pflichtangaben.
- Das System archiviert keine PDF-Dateien. Es erzeugt sie bei jedem Abruf neu aus den gespeicherten Fahrtdaten. **Preise und Beträge bleiben dabei unverändert**, aber Firmenname, Anschrift und Steuernummer werden aus den **aktuellen** Einstellungen genommen. Für die gesetzliche Aufbewahrung sollten Sie Belege zusätzlich sichern.
- Die Abholung steht als „Standort des Fahrgasts (GPS)“ auf der Quittung, eine Abholadresse wird noch nicht ermittelt.

## Rechtliches (keine Rechtsberatung)
- Die **Vermittlung** von Fahrten an andere Unternehmen und das **Bündeln** von Fahrgästen können Genehmigungen und Pflichten nach dem Personenbeförderungsgesetz auslösen. Preise und Tarife können von der Kommune vorgegeben sein.
- Für Fahrten mit **Taxischein** gelten die Regeln des jeweiligen Kostenträgers.
- Fahrzeuge für Rollstuhlfahrer müssen die dafür geltenden Anforderungen erfüllen.

## Bestehende Datenbank aktualisieren

Entweder komplett neu (löscht alle Daten): `docker compose down -v && docker compose up -d --build`

Oder Daten behalten, nach `docker compose up -d --build`:
```bash
docker compose exec -T db psql -U fahrdienst fahrdienst < migrations/2026-11-geteilte-fahrten.sql
docker compose exec -T db psql -U fahrdienst fahrdienst < migrations/2026-12-tarife-partner-quittung.sql
```
Fahrten, die vor der Aktualisierung beendet wurden, haben keine Quittung.
