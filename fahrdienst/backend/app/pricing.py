"""Preise und Einstellungen. Alle Werte sind im Admin-Bereich änderbar (Tabelle settings).

Tarif (eigene Fahrer): Anfahrtskosten (Normalfahrzeug / Rollstuhlfahrzeug) + Kilometer, oder Taxischein.
Partnerfirma: Der Kunde zahlt uns nur eine Servicegebühr (3 bis 6 €, steigt mit der Strecke);
den Fahrpreis rechnet er direkt mit dem Fahrer der Firma ab. Die Firma zahlt uns pro Fahrt 3 €.

WICHTIG: Der Kilometerpreis und die Steuersätze sind Platzhalter. Bitte mit Ihren Tarifen und Ihrem
Steuerberater abstimmen."""
SETTINGS_META = [
    {"key": "approach_normal", "label": "Anfahrtskosten Normalfahrzeug", "unit": "€", "min": 0, "max": 100, "default": 4.0},
    {"key": "approach_wheelchair", "label": "Anfahrtskosten Rollstuhlfahrzeug", "unit": "€", "min": 0, "max": 100, "default": 10.0},
    {"key": "per_km", "label": "Preis pro Kilometer (Platzhalter, bitte anpassen)", "unit": "€/km", "min": 0, "max": 50, "default": 2.2},
    {"key": "pool_discount_pct", "label": "Rabatt für geteilte Fahrt", "unit": "%", "min": 0, "max": 70, "default": 30},
    {"key": "booking_fee_min", "label": "Servicegebühr bei Partnerfirma: Minimum", "unit": "€", "min": 0, "max": 50, "default": 3.0},
    {"key": "booking_fee_max", "label": "Servicegebühr bei Partnerfirma: Maximum", "unit": "€", "min": 0, "max": 50, "default": 6.0},
    {"key": "booking_fee_per_km", "label": "Servicegebühr: Aufschlag pro Kilometer", "unit": "€/km", "min": 0, "max": 5, "default": 0.15},
    {"key": "partner_fee", "label": "Gebühr pro Fahrt, die eine Partnerfirma an uns zahlt (Standard)", "unit": "€", "min": 0, "max": 50, "default": 3.0},
    {"key": "vat_rate_pct", "label": "Umsatzsteuer auf Fahrpreise (mit Steuerberater klären)", "unit": "%", "min": 0, "max": 30, "default": 7},
    {"key": "vat_service_pct", "label": "Umsatzsteuer auf Servicegebühr (mit Steuerberater klären)", "unit": "%", "min": 0, "max": 30, "default": 19},
    {"key": "cost_per_km", "label": "Eigene Kosten pro gefahrenem km (für die Ersparnis-Rechnung)", "unit": "€/km", "min": 0, "max": 10, "default": 0.35},
    {"key": "seats", "label": "Plätze pro Fahrzeug (Fahrgäste gleichzeitig)", "unit": "", "min": 2, "max": 8, "default": 3},
    {"key": "pool_max_ratio", "label": "Max. Verlängerung der Fahrstrecke je Fahrgast (Faktor)", "unit": "×", "min": 1.1, "max": 3, "default": 1.5},
    {"key": "pool_max_extra_km", "label": "Max. Umweg je Fahrgast", "unit": "km", "min": 0, "max": 50, "default": 8},
    {"key": "pool_radius_m", "label": "Suchradius für Fahrzeuge zum Zusteigen", "unit": "m", "min": 500, "max": 30000, "default": 5000},
]
# Angaben des Ausstellers für die Quittung (Text)
TEXT_META = [
    {"key": "company_name", "label": "Firmenname (Quittung)", "default": "Ihre Firma"},
    {"key": "company_address", "label": "Anschrift (Quittung)", "default": "Straße Nr., PLZ Ort"},
    {"key": "company_tax_id", "label": "Steuernummer oder USt-IdNr. (Quittung)", "default": ""},
    {"key": "company_phone", "label": "Telefon (Quittung)", "default": ""},
]
DEFAULTS = {m["key"]: m["default"] for m in SETTINGS_META + TEXT_META}
_NUM = {m["key"]: m for m in SETTINGS_META}
_TEXT = {m["key"]: m for m in TEXT_META}


def load_settings(c) -> dict:
    s = dict(DEFAULTS)
    for k, v in c.execute("SELECT key, value FROM settings").fetchall():
        if k in _NUM:
            try:
                s[k] = float(v)
            except ValueError:
                pass
        elif k in _TEXT:
            s[k] = v
    return s


def settings_view(s: dict) -> list:
    return ([{**m, "type": "number", "value": s[m["key"]]} for m in SETTINGS_META] +
            [{**m, "type": "text", "value": s[m["key"]]} for m in TEXT_META])


def save_settings(c, values: dict) -> None:
    """Prüft Namen und Wertebereiche und speichert. Wirft ValueError bei ungültigen Werten."""
    for k, v in values.items():
        if k in _NUM:
            m = _NUM[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{m['label']}: Bitte eine Zahl angeben")
            if not (m["min"] <= v <= m["max"]):
                raise ValueError(f"{m['label']}: erlaubt sind {m['min']} bis {m['max']}")
        elif k in _TEXT:
            if not isinstance(v, str) or len(v) > 200:
                raise ValueError(f"{_TEXT[k]['label']}: Text bis 200 Zeichen")
        else:
            raise ValueError(f"Unbekannte Einstellung: {k}")
    if (values.get("booking_fee_min", 0) > values.get("booking_fee_max", 1e9)):
        raise ValueError("Servicegebühr: Das Minimum darf nicht über dem Maximum liegen")
    for k, v in values.items():
        c.execute("""INSERT INTO settings (key, value) VALUES (%s,%s)
                     ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""",
                  (k, v.strip() if isinstance(v, str) else str(float(v))))


def _vat_inclusive(total: float, pct: float) -> float:
    return round(total * pct / (100 + pct), 2)


def own_fare(s: dict, km: float, vehicle_type: str, shared: bool) -> dict:
    """Preis bei unseren eigenen Fahrern: Anfahrtskosten + Strecke, bei geteilter Fahrt mit Rabatt."""
    approach = s["approach_wheelchair"] if vehicle_type == "wheelchair" else s["approach_normal"]
    km_price = round(s["per_km"] * km, 2)
    subtotal = round(approach + km_price, 2)
    discount = round(subtotal * s["pool_discount_pct"] / 100, 2) if shared else 0.0
    total = round(subtotal - discount, 2)
    return {"kind": "own", "vehicle_type": vehicle_type, "approach_fee": approach,
            "distance_km": round(km, 1), "per_km": s["per_km"], "km_price": km_price,
            "subtotal": subtotal, "shared": shared,
            "discount_pct": s["pool_discount_pct"] if shared else 0, "discount": discount,
            "total": total, "vat_pct": s["vat_rate_pct"],
            "vat_amount": _vat_inclusive(total, s["vat_rate_pct"])}


def booking_fee(s: dict, km: float) -> float:
    """Servicegebühr bei Partnerfirma: ab Minimum, steigt mit der Strecke, höchstens Maximum."""
    return round(min(s["booking_fee_max"], max(s["booking_fee_min"], s["booking_fee_min"] + s["booking_fee_per_km"] * km)), 2)


def partner_fare(s: dict, km: float) -> dict:
    fee = booking_fee(s, km)
    return {"kind": "partner", "booking_fee": fee, "total": fee, "distance_km": round(km, 1),
            "vat_pct": s["vat_service_pct"], "vat_amount": _vat_inclusive(fee, s["vat_service_pct"]),
            "fare_settled_directly": True}
