# Geteilte Fahrten und Kosten sparen

## Worum geht es?

Kunden mit ähnlicher Strecke können sich ein Fahrzeug teilen. Der Kunde zahlt dafür weniger, und Ihre Firma fährt für mehrere Fahrgäste zusammen weniger Kilometer.

## So läuft es für den Kunden

1. Der Kunde gibt seine Ziele (bis zu 4) ein und tippt bei jedem auf die **Lupe**. Er wählt die Adresse aus der Liste. Erst dann kennt das System die genaue Lage.
2. Die App zeigt Strecke, Fahrzeit und die Preisaufstellung mit Anfahrtskosten. Mit dem Schalter sieht der Kunde den geteilten Preis (zum Beispiel „32,37 € statt 46,24 €, −30 %“).
3. Mit dem Schalter **„Fahrt teilen und sparen“** erklärt sich der Kunde mit Mitfahrern einverstanden. Der Preis steht bei der Anfrage fest.

Ohne Lupe (nur Text) ist keine Buchung möglich, weil das System Strecke und Preis braucht.

## So entscheidet das System

Fragt ein Kunde eine **geteilte** Fahrt an, sucht das System **zuerst** ein Fahrzeug, das schon fährt, und erst danach einen freien Fahrer. Ein Fahrzeug kommt infrage, wenn

- es in der Nähe ist (Standard 5 km) und **nur geteilte** Fahrten fährt (ein Kunde mit Einzelfahrt bekommt nie Mitfahrer),
- noch ein Platz frei ist (Standard 3 Fahrgäste),
- **kein Fahrgast zu viel Umweg** hat: höchstens das 1,5-Fache seiner Strecke und höchstens 8 km mehr,
- es ein **Normalfahrzeug** ist (Rollstuhlfahrten werden nie geteilt) und, falls es einer Partnerfirma gehört, der Kunde Partnerfahrer erlaubt hat,
- das Zusammenlegen **mindestens 20 %** der Einzelstrecke des neuen Fahrgasts spart.

Unter mehreren passenden Fahrzeugen gewinnt das mit dem kleinsten Umweg. Der Fahrer bekommt das Angebot wie jede andere Anfrage (Annehmen oder Ablehnen, Standard 15 Sekunden). Lehnt er ab oder passt kein Fahrzeug, geht die Anfrage an den nächsten freien Fahrer.

**Beispiel (aus den Tests):** Fahrgast A fährt zum Flughafen Köln/Bonn. Fahrgast B steigt unterwegs in der Nähe zu und will bis zum Gewerbegebiet Nord, das auf der Strecke liegt. Umweg für das Fahrzeug: etwa 0,1 km. B spart 12,8 km Einzelstrecke.

## Beim Fahrer

- Bei geteilten Fahrten sieht der Fahrer **mehrere Fahrten** gleichzeitig, jede mit eigenen Buttons („Kunde abgeholt“, „Ziel erreicht“).
- Eine Karte **„Empfohlene Reihenfolge“** schlägt vor, in welcher Reihenfolge er abholt und absetzt, mit Button **„Navigation zum nächsten Halt“**.
- Angebote zum Zusteigen sind markiert: „Mitfahrer steigt zu (Umweg ca. X km)“.
- Der Fahrer wird erst wieder **frei**, wenn der letzte Fahrgast ausgestiegen ist.

## Wie Ihre Firma spart (Admin-Seite)

Unter **Live** sehen Sie:

- zusammengelegt / geteilt angefragt (heute)
- gesparte Strecke und gesparte Kosten (30 Tage). Gesparte Strecke = Einzelstrecke des Mitfahrers minus Umweg. Gesparte Kosten = gesparte Strecke × Ihre Kosten pro km.
- Umsatz heute

Unter **Fahrten** steht pro Fahrt der Preis und „zusammengelegt (−X km)“.

### Einstellungen (Reiter „Preise & Teilen“)

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Anfahrtskosten, Preis pro km | 4,00 € (Rollstuhl 10,00 €), 2,20 €/km | Preis bei eigenen Fahrern, siehe `PREISE_PARTNER_QUITTUNG.md`. **Kilometerpreis ist ein Platzhalter.** |
| Rabatt für geteilte Fahrt | 30 % | Wie viel der Kunde spart |
| Eigene Kosten pro km | 0,35 €/km | Nur für die Ersparnis-Rechnung |
| Plätze pro Fahrzeug | 3 | Fahrgäste gleichzeitig |
| Max. Verlängerung / Umweg | 1,5× / 8 km | Schutz vor zu großen Umwegen |
| Suchradius | 5000 m | Wie weit ein Fahrzeug entfernt sein darf |

Änderungen gelten sofort für neue Anfragen.

**Wirtschaftlich wichtig:** Der Rabatt gilt, sobald der Kunde „teilen“ wählt, **auch wenn sich kein Mitfahrer findet**. Beobachten Sie „zusammengelegt / geteilt angefragt“: Findet nur ein kleiner Teil einen Mitfahrer, ist ein hoher Rabatt ein Verlustgeschäft. Starten Sie lieber mit 10 bis 20 % und erhöhen Sie, wenn die Quote steigt.

## Grenzen (bitte ehrlich einplanen)

- **Entfernungen sind Schätzungen:** Luftlinie × 1,3. Das ist keine echte Routenberechnung, Staus und Einbahnstraßen kennt das System nicht. Der Preis steht deshalb bei der Anfrage fest und wird nicht nach gefahrenen Kilometern abgerechnet.
- **Die Reihenfolge ist eine Faustregel**, kein mathematisch bester Weg. Der Fahrer entscheidet vor Ort.
- **Mitfahrer können nur zusteigen, solange die Fahrt läuft.** Es gibt keine Planung im Voraus und keine Sammelfahrten ab festen Zeiten.
- **Es gibt kein Bezahlsystem:** Preise werden berechnet, angezeigt und gespeichert, aber nicht abgebucht.
- Die Fahrgäste sehen einander nicht und erhalten keine Mitteilung über Mitfahrer.

## Rechtliches (keine Rechtsberatung)

In Deutschland kann das **Bündeln von Fahrgästen (Pooling)** genehmigungspflichtig sein (Personenbeförderungsgesetz, „gebündelter Bedarfsverkehr“). Auch Preise können von der Kommune vorgegeben oder genehmigungspflichtig sein. Klären Sie das vor dem Einsatz mit Ihrer Genehmigungsbehörde oder einem Anwalt. Eine Fahrt mit mehreren Fahrgästen hat außerdem Folgen für Haftung und Versicherung.

## Adresssuche

Die Suche nutzt OpenStreetMap/Nominatim über Ihren Server (Kunden sehen keine fremden Server). Der öffentliche Server `nominatim.openstreetmap.org` ist nur zum Testen gedacht: höchstens 1 Anfrage pro Sekunde, Kontakt im `GEOCODER_USER_AGENT` Pflicht, kein Dauerbetrieb für eine Firma. **Für den Echtbetrieb** brauchen Sie einen eigenen Nominatim-Server oder einen kommerziellen Anbieter mit Nominatim-kompatibler Schnittstelle (`GEOCODER_URL` in `.env`). Der Server begrenzt zusätzlich auf 20 Suchen pro Minute und Nutzer und speichert Ergebnisse einen Tag.

## Bestehende Datenbank aktualisieren

Entweder neu anfangen (löscht alle Daten):
```bash
docker compose down -v && docker compose up -d --build
```
oder die Datenbank behalten:
```bash
docker compose up -d --build
docker compose exec -T db psql -U fahrdienst fahrdienst < migrations/2026-11-geteilte-fahrten.sql
docker compose exec -T db psql -U fahrdienst fahrdienst < migrations/2026-12-tarife-partner-quittung.sql
```
