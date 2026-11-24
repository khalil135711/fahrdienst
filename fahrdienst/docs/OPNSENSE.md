# Betrieb hinter OPNsense

Die Datenbank läuft **nicht** auf der Firewall, sondern in einem eigenen Daten-VLAN.

```
Internet → OPNsense → VLAN App:   API-Server (nur 443)
                    → VLAN Daten: PostgreSQL + Redis (kein Internet)
```

| Von | Nach | Port | Aktion |
|---|---|---|---|
| Internet | API-Server | 443 | erlauben |
| API-Server | Datenbank | 5432 | erlauben |
| API-Server | Redis | 6379 | erlauben |
| Admin (WireGuard) | Datenbank | 5432 | erlauben |
| alles andere | Datenbank | * | blockieren |

Kein Port-Forward auf 5432. Tägliche Backups auf ein externes System.

## HTTPS

Die App sendet Anmelde-Token und Passwörter. Betreiben Sie die API deshalb nur über HTTPS (Reverse Proxy mit Zertifikat, zum Beispiel Caddy oder Nginx im App-VLAN). Siehe `AUTH.md`.

## Admin-Seite nur intern erreichbar machen (empfohlen)

Kunden- und Fahrer-App brauchen aus dem Internet nur `/auth/*`, `/rides/*` und `/drivers/*`. Die Admin-Webseite (`/dashboard`) und die Admin-Funktionen (`/admin/*`) sollten Sie im Reverse Proxy nur aus dem Büro-Netz oder über WireGuard-VPN freigeben. Dann kann niemand aus dem Internet die Admin-Anmeldung angreifen.

Beispiel (Caddy, nur Büro-Netz 192.168.1.0/24 und VPN 10.10.0.0/24):

```
@intern path /dashboard* /admin*
@fremd not remote_ip 192.168.1.0/24 10.10.0.0/24
handle @intern {
    respond @fremd 403
    reverse_proxy api:8000
}
```

## Musik und Zeitungen

- `/music/*` und `/news/*` müssen für die Apps aus dem Internet erreichbar sein (wie `/auth`, `/rides`, `/drivers`). Die Verwaltung `/admin/music/*` und `/admin/news/*` fällt unter die Admin-Beschränkung oben.
- Der Reverse Proxy muss Uploads bis 35 MB erlauben (Nginx: `client_max_body_size 35m;`).
- Der API-Server braucht für die Zeitungs-Feeds ausgehend HTTPS (Port 443) ins Internet. Aus dem App-VLAN heraus erlauben Sie nur Port 443 und DNS.

## Adresssuche und Zeitungen (ausgehend)

Der API-Server muss für die Adresssuche den Nominatim-Dienst erreichen (`GEOCODER_URL`, Standard `nominatim.openstreetmap.org`, Port 443) und für die Zeitungs-Feeds HTTPS-Ziele im Internet. Erlauben Sie aus dem App-VLAN nur Port 443 und DNS. `/geo/*` und `/rides/quote` müssen für die Apps aus dem Internet erreichbar sein.

## Quittungen und Preise

`/rides/*/receipt-link` und `/rides/*/receipt.pdf` müssen für die Apps aus dem Internet erreichbar sein (der Link gilt nur 10 Minuten). Die Verwaltung der Partnerfirmen und Preise liegt unter `/admin/*` und `/dashboard` und fällt unter die Admin-Beschränkung.
