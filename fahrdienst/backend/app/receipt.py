"""Quittung als PDF. Der Kunde bekommt einen kurzlebigen Download-Link (10 Minuten), der nur diese Quittung öffnet."""
import datetime as dt
import hashlib
import io
import os
from zoneinfo import ZoneInfo

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from . import pricing
from .auth import ALGO, JWT_SECRET, current_user
from .db import db

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
pdfmetrics.registerFont(TTFont("DV", os.path.join(FONTS, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DV-B", os.path.join(FONTS, "DejaVuSans-Bold.ttf")))
TZ = ZoneInfo("Europe/Berlin")
# Eigener Schlüssel: Ein Quittungs-Link ist nie als Anmelde-Token verwendbar
RECEIPT_SECRET = hashlib.sha256((JWT_SECRET + "|receipt").encode()).hexdigest()
LINK_MINUTES = 10

router = APIRouter()


def eur(v: float) -> str:
    """12345.6 -> '12.345,60 €'"""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def num(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def km_txt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",") + " km"


def build_pdf(d: dict, st: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Quittung {d['receipt_no']}")
    c.setAuthor(st["company_name"])
    W, H = A4
    L, R = 20 * mm, W - 20 * mm
    y = H - 22 * mm

    def text(x, yy, s, size=10, bold=False, right=False):
        c.setFont("DV-B" if bold else "DV", size)
        (c.drawRightString if right else c.drawString)(x, yy, s)

    def wrapped(x, yy, s, width, size=10, bold=False, lead=13):
        for line in simpleSplit(s, "DV-B" if bold else "DV", size, width):
            text(x, yy, line, size, bold)
            yy -= lead
        return yy

    # Aussteller
    text(L, y, st["company_name"], 15, True); y -= 16
    y = wrapped(L, y, st["company_address"], 90 * mm)
    if st["company_phone"]:
        text(L, y, "Tel. " + st["company_phone"]); y -= 13
    if st["company_tax_id"]:
        text(L, y, "Steuer-Nr./USt-IdNr.: " + st["company_tax_id"]); y -= 13

    # Titel
    y -= 18
    text(L, y, "Quittung", 22, True)
    text(R, y + 10, "Nr. " + d["receipt_no"], 11, True, right=True)
    done = d["finished_at"].astimezone(TZ)
    text(R, y - 4, "Datum: " + done.strftime("%d.%m.%Y, %H:%M") + " Uhr", 10, right=True)
    y -= 12
    c.setLineWidth(0.8); c.line(L, y, R, y); y -= 20

    # Fahrt
    text(L, y, "Fahrgast", 9, True); text(L + 38 * mm, y, d["customer"]); y -= 15
    text(L, y, "Fahrt", 9, True)
    y = wrapped(L + 38 * mm, y, "Abholung: Standort des Fahrgasts (GPS)", R - L - 38 * mm)
    for i, a in enumerate(d["stops"], 1):
        y = wrapped(L + 38 * mm, y, f"Ziel {i}: {a}", R - L - 38 * mm)
    fare = d["fare"]
    text(L + 38 * mm, y, "Strecke: " + km_txt(fare["distance_km"])); y -= 15
    veh = "Rollstuhlfahrzeug" if d["vehicle_type"] == "wheelchair" else "Normalfahrzeug"
    text(L, y, "Fahrzeug", 9, True); text(L + 38 * mm, y, veh); y -= 15
    text(L, y, "Fahrer", 9, True)
    drv = d["driver"] + (f" ({d['company']})" if d["company"] else "")
    y = wrapped(L + 38 * mm, y, drv, R - L - 38 * mm)
    if d["shared"]:
        text(L, y, "Art", 9, True); text(L + 38 * mm, y, "Geteilte Fahrt (Mitfahrer möglich)"); y -= 15

    # Positionen
    y -= 10
    c.setFillGray(0.93); c.rect(L, y - 4, R - L, 18, fill=1, stroke=0); c.setFillGray(0)
    text(L + 3 * mm, y + 1, "Leistung", 9, True); text(R - 3 * mm, y + 1, "Betrag", 9, True, right=True)
    y -= 20
    rows = []
    if fare["kind"] == "own":
        rows.append((f"Anfahrtskosten ({veh})", fare["approach_fee"]))
        rows.append((f"Fahrstrecke {km_txt(fare['distance_km'])} × {num(fare['per_km'])} €/km", fare["km_price"]))
        if fare["discount"]:
            rows.append((f"Rabatt geteilte Fahrt (−{fare['discount_pct']:.0f} %)", -fare["discount"]))
    else:
        rows.append((f"Servicegebühr für die Vermittlung (Fahrt durchgeführt von: {d['company']})", fare["booking_fee"]))
    for label, amount in rows:
        y0 = y
        y = wrapped(L + 3 * mm, y, label, R - L - 40 * mm)
        text(R - 3 * mm, y0, eur(amount), 10, False, True)
    y -= 4; c.line(L, y + 8, R, y + 8); y -= 6
    text(L + 3 * mm, y, "Gesamtbetrag (brutto)", 11, True); text(R - 3 * mm, y, eur(fare["total"]), 11, True, True); y -= 15
    text(L + 3 * mm, y, f"darin enthaltene Umsatzsteuer {fare['vat_pct']:.0f} %", 9)
    text(R - 3 * mm, y, eur(fare["vat_amount"]), 9, False, True); y -= 26

    # Zahlung
    text(L, y, "Zahlung", 9, True)
    if fare["kind"] == "partner":
        msg = (f"Der Fahrpreis wird direkt zwischen Fahrgast und {d['company']} abgerechnet; das Unternehmen "
               "stellt dafür einen eigenen Beleg aus. Diese Quittung betrifft nur unsere Servicegebühr.")
    elif d["payment_method"] == "taxischein":
        msg = f"Bezahlt mit Taxischein Nr. {d['voucher_no']}. Der Betrag wird mit dem Kostenträger abgerechnet."
    else:
        msg = "Abrechnung nach Kilometern."
    y = wrapped(L + 38 * mm, y, msg, R - L - 38 * mm)
    y -= 30
    text(L, 18 * mm, "Preis und Strecke wurden bei der Buchung anhand der berechneten Strecke festgelegt. Maschinell erstellt.", 8)
    c.showPage(); c.save()
    return buf.getvalue()


def make_token(ride_id: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(ride_id), "typ": "receipt", "exp": now + dt.timedelta(minutes=LINK_MINUTES)},
                      RECEIPT_SECRET, algorithm=ALGO)


@router.post("/rides/{ride_id}/receipt-link")
def receipt_link(ride_id: int, user: dict = Depends(current_user)):
    """Gibt einen kurzlebigen Link zur Quittung (PDF) zurück. Nur der Kunde der Fahrt oder ein Admin."""
    with db() as c:
        row = c.execute("SELECT customer_id, status, receipt_no FROM rides WHERE id=%s", (ride_id,)).fetchone()
    if not row or not (user["role"] == "admin" or row[0] == user["id"]):
        raise HTTPException(404, "Fahrt nicht gefunden")
    if row[1] != "completed" or not row[2]:
        raise HTTPException(409, "Die Quittung gibt es erst nach Ende der Fahrt")
    return {"url": f"/rides/{ride_id}/receipt.pdf?t={make_token(ride_id)}", "receipt_no": row[2]}


@router.get("/rides/{ride_id}/receipt.pdf")
def receipt_pdf(ride_id: int, t: str = ""):
    try:
        data = jwt.decode(t, RECEIPT_SECRET, algorithms=[ALGO], options={"require": ["exp", "sub"]})
        if data.get("typ") != "receipt" or int(data["sub"]) != ride_id:
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Link abgelaufen oder ungültig")
    with db() as c:
        row = c.execute("""
            SELECT r.receipt_no, r.finished_at, cu.name, du.name, co.name, r.vehicle_type,
                   r.payment_method, r.voucher_no, r.fare, r.shared
            FROM rides r
            JOIN users cu ON cu.id=r.customer_id
            LEFT JOIN users du ON du.id=r.driver_id
            LEFT JOIN companies co ON co.id=r.company_id
            WHERE r.id=%s AND r.status='completed' AND r.receipt_no IS NOT NULL AND r.fare IS NOT NULL""",
                        (ride_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Für diese Fahrt gibt es keine Quittung")
        stops = [a for (a,) in c.execute("SELECT address FROM ride_stops WHERE ride_id=%s ORDER BY position",
                                         (ride_id,)).fetchall()]
        st = pricing.load_settings(c)
    no, fin, cust, drv, comp, veh, pay, voucher, fare, shared = row
    pdf = build_pdf({"receipt_no": no, "finished_at": fin, "customer": cust, "driver": drv or "–",
                     "company": comp, "vehicle_type": veh, "payment_method": pay, "voucher_no": voucher,
                     "fare": fare, "shared": shared, "stops": stops}, st)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Quittung-{no}.pdf"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
