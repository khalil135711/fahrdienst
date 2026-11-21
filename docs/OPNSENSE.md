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
