"""Fahrdienst-API mit Anmeldung (JWT) und Rollen: customer, driver, admin.

- Kunden registrieren sich selbst (POST /auth/register).
- Fahrer legt nur der Admin an (POST /admin/drivers).
- Der erste Admin wird beim Start aus ADMIN_EMAIL / ADMIN_PASSWORD erzeugt.

Zuweisung: Anfrage -> Angebot an nächsten freien Fahrer (OFFER_SECONDS) ->
Annehmen / Ablehnen / Timeout -> nächster Fahrer -> sonst 'no_driver'."""
import math
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import psycopg
from psycopg.types.json import Jsonb
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, EmailStr, Field, model_validator

from .auth import (LOCK_MINUTES, MAX_FAILED, DUMMY_HASH, create_token,
                   hash_password, require, verify_password, current_user)
from .db import db
from . import geo, music, news, pooling, pricing, receipt

RADIUS_M = int(os.environ.get("DISPATCH_RADIUS_M", "5000"))
OFFER_SECONDS = int(os.environ.get("OFFER_SECONDS", "15"))
AVG_SPEED_KMH = 30


def _pw_bytes(p: str) -> str:
    if len(p.encode()) > 72:  # bcrypt-Grenze
        raise ValueError("Passwort ist zu lang (max. 72 Bytes)")
    return p


Password = Annotated[str, Field(min_length=8), AfterValidator(_pw_bytes)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Legt den ersten Admin an, falls es noch keinen gibt."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if email and pw:
        with db() as c:
            if not c.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone():
                if len(pw) < 8:
                    raise RuntimeError("ADMIN_PASSWORD muss mindestens 8 Zeichen haben")
                c.execute("""INSERT INTO users (name,email,password_hash,role)
                             VALUES ('Admin',%s,%s,'admin')""", (email, hash_password(pw)))
                print(f"Admin-Konto angelegt: {email}")
    yield


app = FastAPI(title="Fahrdienst API", lifespan=lifespan)
# Entwicklung: alles erlaubt. In Produktion CORS_ORIGINS auf Ihre Domain setzen!
origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins,
                   allow_methods=["*"], allow_headers=["*"])


app.include_router(music.router)
app.include_router(news.router)
app.include_router(geo.router)
app.include_router(receipt.router)


# ---------------------------------------------------------------- Modelle
class LoginBody(BaseModel):
    email: str
    password: str


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: Password


class Stop(BaseModel):
    address: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)   # Koordinaten sind Pflicht: ohne sie gibt es keinen Preis
    lng: float = Field(ge=-180, le=180)


class RideRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)  # Abfahrt = Standort des Kunden
    lng: float = Field(ge=-180, le=180)
    stops: list[Stop] = Field(min_length=1, max_length=4)
    shared: bool = False  # Kunde ist mit einer geteilten Fahrt (Mitfahrer) einverstanden: günstiger
    vehicle_type: Literal["normal", "wheelchair"] = "normal"
    payment_method: Literal["km", "taxischein"] = "km"
    voucher_no: str | None = Field(default=None, max_length=40)  # Nummer des Taxischeins
    allow_partner: bool = False  # Fahrer von Partnerfirmen sind erlaubt (Servicegebühr statt unserem Tarif)

    @model_validator(mode="after")
    def check(self):
        if self.shared and self.vehicle_type == "wheelchair":
            raise ValueError("Rollstuhlfahrten können nicht geteilt werden")
        if self.payment_method == "taxischein":
            self.voucher_no = (self.voucher_no or "").strip()
            if len(self.voucher_no) < 3:
                raise ValueError("Bitte die Nummer des Taxischeins angeben")
        else:
            self.voucher_no = None
        return self


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0, le=400)


class Rating(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


class StatusBody(BaseModel):
    status: str


class NewDriver(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: Password
    vehicle_model: str = Field(min_length=2, max_length=80)
    plate: str = Field(min_length=2, max_length=20)
    vehicle_type: Literal["normal", "wheelchair"] = "normal"
    company_id: int | None = None  # None = eigener Fahrer, sonst Fahrer dieser Partnerfirma


class CompanyBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    contact: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=200)
    fee_per_ride: float | None = Field(default=None, ge=0, le=50)  # None = Standardgebühr


class CompanyPatch(BaseModel):
    active: bool | None = None
    fee_per_ride: float | None = Field(default=None, ge=0, le=50)
    use_default_fee: bool = False


class ActiveBody(BaseModel):
    active: bool


class PasswordBody(BaseModel):
    password: Password


# ---------------------------------------------------------------- Auth
@app.post("/auth/login")
def login(b: LoginBody):
    email = b.email.strip().lower()
    generic = HTTPException(401, "E-Mail oder Passwort falsch")
    with db() as c:
        row = c.execute("""SELECT id, name, role, password_hash, active,
                                  locked_until IS NOT NULL AND locked_until > now()
                           FROM users WHERE email=%s""", (email,)).fetchone()
        if row is None:
            verify_password(b.password, DUMMY_HASH)  # gleiche Laufzeit
            raise generic
        uid, name, role, pw_hash, active, locked = row
        if locked:
            raise HTTPException(429, f"Zu viele Fehlversuche. Bitte in {LOCK_MINUTES} Minuten erneut versuchen.")
        if not verify_password(b.password, pw_hash):
            c.execute("""UPDATE users SET
                           failed_attempts = CASE WHEN failed_attempts+1 >= %s THEN 0 ELSE failed_attempts+1 END,
                           locked_until = CASE WHEN failed_attempts+1 >= %s
                                          THEN now() + (%s * interval '1 minute') ELSE locked_until END
                         WHERE id=%s""", (MAX_FAILED, MAX_FAILED, LOCK_MINUTES, uid))
            c.commit()
            raise generic
        if not active:
            raise HTTPException(403, "Konto ist gesperrt. Bitte den Administrator kontaktieren.")
        c.execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=%s", (uid,))
    return {"token": create_token(uid, role), "role": role, "name": name, "user_id": uid}


@app.post("/auth/register")
def register(b: RegisterBody):
    """Nur Kunden. Fahrer und Admins können sich nicht selbst registrieren."""
    try:
        with db() as c:
            uid = c.execute("""INSERT INTO users (name,email,password_hash,role)
                               VALUES (%s,%s,%s,'customer') RETURNING id""",
                            (b.name.strip(), b.email.lower(), hash_password(b.password))).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Diese E-Mail ist bereits registriert")
    return {"token": create_token(uid, "customer"), "role": "customer",
            "name": b.name.strip(), "user_id": uid}


@app.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


# ---------------------------------------------------------------- Hilfsfunktionen
def dispatch(c, ride_id: int):
    """Schaltet die Anfrage zum nächsten Fahrer weiter, falls nötig."""
    row = c.execute("SELECT status FROM rides WHERE id=%s", (ride_id,)).fetchone()
    if not row or row[0] != "requested":
        return
    c.execute("""UPDATE ride_offers SET status='expired'
                 WHERE ride_id=%s AND status='pending' AND expires_at < now()""", (ride_id,))
    if c.execute("SELECT 1 FROM ride_offers WHERE ride_id=%s AND status='pending'",
                 (ride_id,)).fetchone():
        return
    shared = c.execute("SELECT shared FROM rides WHERE id=%s", (ride_id,)).fetchone()[0]
    if shared:  # geteilte Fahrt: zuerst ein Fahrzeug suchen, das schon in diese Richtung fährt
        cand = pooling.best_candidate(c, ride_id, pricing.load_settings(c))
        if cand:
            c.execute("""INSERT INTO ride_offers (ride_id, driver_id, expires_at, kind, detour_km, saved_km)
                         VALUES (%s,%s, now() + (%s * interval '1 second'), 'pool', %s, %s)""",
                      (ride_id, cand["driver_id"], OFFER_SECONDS, cand["detour_km"], cand["saved_km"]))
            return
    nxt = c.execute("""
        SELECT d.user_id FROM drivers d
        JOIN users u ON u.id=d.user_id AND u.active
        JOIN vehicles v ON v.id=d.vehicle_id
        LEFT JOIN companies co ON co.id=d.company_id
        JOIN rides r ON r.id=%s
        WHERE d.status='free' AND d.location IS NOT NULL
          AND v.vehicle_type = r.vehicle_type
          AND (d.company_id IS NULL OR (r.allow_partner AND co.active))
          AND ST_DWithin(d.location, r.pickup, %s)
          AND d.user_id NOT IN (SELECT driver_id FROM ride_offers WHERE ride_id=%s)
        ORDER BY (d.company_id IS NOT NULL), ST_Distance(d.location, r.pickup) LIMIT 1""",
        (ride_id, RADIUS_M, ride_id)).fetchone()
    if nxt:
        c.execute("""INSERT INTO ride_offers (ride_id, driver_id, expires_at)
                     VALUES (%s,%s, now() + (%s * interval '1 second'))""",
                  (ride_id, nxt[0], OFFER_SECONDS))
    else:
        c.execute("UPDATE rides SET status='no_driver' WHERE id=%s", (ride_id,))


def stops_of(c, ride_id: int):
    rows = c.execute("""SELECT position, address, reached_at IS NOT NULL,
                               ST_Y(location::geometry), ST_X(location::geometry)
                        FROM ride_stops WHERE ride_id=%s ORDER BY position""",
                     (ride_id,)).fetchall()
    return [{"position": p, "address": a, "reached": r, "lat": la, "lng": ln}
            for p, a, r, la, ln in rows]


@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- Kunde
def quote_for(st: dict, r: RideRequest) -> dict:
    """Strecke und alle Preisvarianten: eigene Fahrer (einzeln/geteilt) und Partnerfirma."""
    km = pooling.chain_km((r.lat, r.lng), [(x.lat, x.lng) for x in r.stops])
    return {"distance_km": round(km, 1), "duration_min": max(1, round(km / AVG_SPEED_KMH * 60)),
            "own": pricing.own_fare(st, km, r.vehicle_type, False),
            "own_shared": None if r.vehicle_type == "wheelchair" else pricing.own_fare(st, km, r.vehicle_type, True),
            "partner": pricing.partner_fare(st, km), "discount_pct": st["pool_discount_pct"]}


@app.post("/rides/quote")
def quote(r: RideRequest, user: dict = Depends(require("customer"))):
    """Preis VOR der Fahrt. Bei eigenen Fahrern gilt unser Tarif, bei einer Partnerfirma nur die Servicegebühr."""
    with db() as c:
        st = pricing.load_settings(c)
        partners = c.execute("""SELECT EXISTS (SELECT 1 FROM drivers d
                                JOIN companies co ON co.id=d.company_id AND co.active
                                JOIN users u ON u.id=d.user_id AND u.active
                                JOIN vehicles v ON v.id=d.vehicle_id
                                WHERE v.vehicle_type=%s)""", (r.vehicle_type,)).fetchone()[0]
    return {"currency": "EUR", "partners_available": partners, **quote_for(st, r)}


@app.post("/rides")
def request_ride(r: RideRequest, user: dict = Depends(require("customer"))):
    with db() as c:
        st = pricing.load_settings(c)
        q = quote_for(st, r)
        price = (q["own_shared"] if r.shared else q["own"])["total"]
        ride_id = c.execute(
            """INSERT INTO rides (customer_id, pickup, shared, distance_km, price_solo, price,
                                  vehicle_type, payment_method, voucher_no, allow_partner, quote)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (user["id"], r.lng, r.lat, r.shared, q["distance_km"], q["own"]["total"], price,
             r.vehicle_type, r.payment_method, r.voucher_no, r.allow_partner, Jsonb(q))).fetchone()[0]
        for i, stp in enumerate(r.stops, start=1):
            c.execute(
                """INSERT INTO ride_stops (ride_id, position, address, location)
                   VALUES (%s,%s,%s, ST_SetSRID(ST_MakePoint(%s::float8,%s::float8),4326)::geography)""",
                (ride_id, i, stp.address.strip(), stp.lng, stp.lat))
        dispatch(c, ride_id)
        status = c.execute("SELECT status FROM rides WHERE id=%s", (ride_id,)).fetchone()[0]
    return {"id": ride_id, "status": status, "price": price}


@app.get("/rides/{ride_id}")
def get_ride(ride_id: int, user: dict = Depends(current_user)):
    """Status, Fahrer, ETA. Nur der Kunde der Fahrt, der zugewiesene Fahrer oder ein Admin."""
    with db() as c:
        row = c.execute("""
            SELECT r.status, r.customer_id, r.driver_id, u.name, d.rating_avg,
                   v.model || ' • ' || v.plate,
                   ST_Y(d.location::geometry), ST_X(d.location::geometry),
                   ST_Distance(d.location, r.pickup),
                   r.price, r.price_solo, r.shared, r.pooled, r.distance_km,
                   co.name, r.vehicle_type, r.payment_method, r.fare, r.quote, r.receipt_no
            FROM rides r
            LEFT JOIN companies co ON co.id = r.company_id
            LEFT JOIN drivers d ON d.user_id = r.driver_id
            LEFT JOIN users u ON u.id = r.driver_id
            LEFT JOIN vehicles v ON v.id = d.vehicle_id
            WHERE r.id=%s""", (ride_id,)).fetchone()
        (status, cust, drv, name, rating, vehicle, dlat, dlng, dist,
         price, price_solo, shared, pooled, dkm,
         company, vtype, pay, fare, quote_, receipt_no) = row if row else (None,) * 20
        if row is None or not (user["role"] == "admin" or cust == user["id"] or drv == user["id"]):
            raise HTTPException(404, "Fahrt nicht gefunden")
        if user["role"] != "driver":
            dispatch(c, ride_id)
            status = c.execute("SELECT status FROM rides WHERE id=%s", (ride_id,)).fetchone()[0]
        eta = None
        if status == "accepted" and dist is not None:
            eta = max(1, math.ceil(dist / 1000 / AVG_SPEED_KMH * 60))
        return {"id": ride_id, "status": status, "driver_name": name,
                "driver_rating": float(rating) if rating is not None else None,
                "vehicle": vehicle, "driver_lat": dlat, "driver_lng": dlng,
                "eta_minutes": eta, "stops": stops_of(c, ride_id),
                "price": None if price is None else float(price),
                "price_solo": None if price_solo is None else float(price_solo),
                "shared": shared, "pooled": pooled,
                "distance_km": None if dkm is None else float(dkm),
                "company": company, "vehicle_type": vtype, "payment_method": pay,
                "fare": fare, "quote": quote_, "receipt_available": bool(receipt_no)}


@app.post("/rides/{ride_id}/rating")
def rate(ride_id: int, r: Rating, user: dict = Depends(require("customer"))):
    try:
        with db() as c:
            row = c.execute("SELECT driver_id, status FROM rides WHERE id=%s AND customer_id=%s",
                            (ride_id, user["id"])).fetchone()
            if not row:
                raise HTTPException(404, "Fahrt nicht gefunden")
            if row[1] != "completed" or row[0] is None:
                raise HTTPException(409, "Nur beendete Fahrten können bewertet werden")
            c.execute("INSERT INTO ratings (ride_id, driver_id, stars, comment) VALUES (%s,%s,%s,%s)",
                      (ride_id, row[0], r.stars, r.comment))
            c.execute("""UPDATE drivers SET
                         rating_avg=(SELECT AVG(stars) FROM ratings WHERE driver_id=%s),
                         rating_count=(SELECT COUNT(*) FROM ratings WHERE driver_id=%s)
                         WHERE user_id=%s""", (row[0], row[0], row[0]))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Diese Fahrt wurde bereits bewertet")
    return {"ok": True}


# ---------------------------------------------------------------- Fahrer
def payment_info(method: str, voucher: str | None, fare: dict | None) -> str:
    """Hinweis für den Fahrer, wie diese Fahrt abgerechnet wird."""
    if fare and fare.get("kind") == "partner":
        return ("Fahrpreis direkt mit dem Fahrgast abrechnen (Taxameter oder Taxischein). "
                "Unsere Servicegebühr wird separat berechnet.")
    if method == "taxischein":
        return f"Taxischein Nr. {voucher}: Schein entgegennehmen, Betrag wird mit dem Kostenträger abgerechnet."
    total = (fare or {}).get("total")
    return "Abrechnung nach Kilometern" + (f": Fahrgast zahlt {total:.2f} €".replace(".", ",") if total else "")


@app.get("/drivers/me/state")
def driver_state(user: dict = Depends(require("driver"))):
    """Vom Fahrer regelmäßig abgefragt: Angebot, laufende Fahrten (bei geteilten Fahrten mehrere)
    und ein Routenvorschlag für die Reihenfolge der Halte."""
    with db() as c:
        offer = None
        o = c.execute("""
            SELECT o.ride_id, EXTRACT(EPOCH FROM (o.expires_at - now())), u.name,
                   ST_Distance(d.location, r.pickup),
                   ST_Y(r.pickup::geometry), ST_X(r.pickup::geometry),
                   o.kind, o.detour_km, r.shared, r.vehicle_type
            FROM ride_offers o
            JOIN rides r ON r.id=o.ride_id
            JOIN users u ON u.id=r.customer_id
            JOIN drivers d ON d.user_id=o.driver_id
            WHERE o.driver_id=%s AND o.status='pending' AND o.expires_at > now()
              AND r.status='requested'
            ORDER BY o.offered_at LIMIT 1""", (user["id"],)).fetchone()
        if o:
            offer = {"ride_id": o[0], "seconds_left": int(o[1]), "customer": o[2],
                     "distance_m": int(o[3] or 0), "pickup_lat": o[4], "pickup_lng": o[5],
                     "kind": o[6], "detour_km": None if o[7] is None else float(o[7]),
                     "shared": o[8], "vehicle_type": o[9], "stops": stops_of(c, o[0])}
        rows = c.execute("""SELECT r.id, r.status, u.name, ST_Y(r.pickup::geometry), ST_X(r.pickup::geometry),
                                   r.shared, r.vehicle_type, r.payment_method, r.voucher_no, r.fare
                            FROM rides r JOIN users u ON u.id=r.customer_id
                            WHERE r.driver_id=%s AND r.status IN ('accepted','in_progress')
                            ORDER BY r.id""", (user["id"],)).fetchall()
        rides = [{"ride_id": i, "status": st, "customer": n, "pickup_lat": la, "pickup_lng": ln,
                  "shared": sh, "vehicle_type": vt, "payment_method": pm, "voucher_no": vn,
                  "payment_info": payment_info(pm, vn, fare), "stops": stops_of(c, i)}
                 for i, st, n, la, ln, sh, vt, pm, vn, fare in rows]
        plan = []
        if len(rides) >= 2:  # Reihenfolge der Halte vorschlagen
            pos = c.execute("SELECT ST_Y(location::geometry), ST_X(location::geometry) FROM drivers "
                            "WHERE user_id=%s", (user["id"],)).fetchone()
            prides = pooling.load_driver_rides(c, user["id"])
            if prides and pos and pos[0] is not None:
                names = {r["ride_id"]: r["customer"] for r in rides}
                addr = {(r["ride_id"], x["position"]): x["address"] for r in rides for x in r["stops"]}
                for e in pooling.greedy_plan((pos[0], pos[1]), prides):
                    label = (f"Abholung: {names[e.ride_id]}" if e.kind == "pickup" else
                             f"Ziel {e.stop_pos} von {names[e.ride_id]}: {addr.get((e.ride_id, e.stop_pos), '')}")
                    plan.append({"ride_id": e.ride_id, "kind": e.kind, "label": label,
                                 "lat": e.point[0], "lng": e.point[1]})
        return {"offer": offer, "active": rides[0] if rides else None,
                "active_rides": rides, "route_plan": plan}


@app.post("/drivers/me/status")
def set_status(body: StatusBody, user: dict = Depends(require("driver"))):
    if body.status not in ("free", "offline"):
        raise HTTPException(400, "status muss 'free' oder 'offline' sein")
    with db() as c:
        ok = c.execute("""UPDATE drivers SET status=%s WHERE user_id=%s AND status<>'busy'
                          RETURNING 1""", (body.status, user["id"])).fetchone()
    if not ok:
        raise HTTPException(409, "Während einer laufenden Fahrt nicht möglich")
    return {"ok": True}


@app.post("/drivers/me/location")
def update_location(loc: Location, user: dict = Depends(require("driver"))):
    with db() as c:
        c.execute("""UPDATE drivers SET location=ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                     last_seen=now() WHERE user_id=%s""", (loc.lng, loc.lat, user["id"]))
        c.execute("""INSERT INTO location_log (driver_id, location, speed_kmh)
                     VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)""",
                  (user["id"], loc.lng, loc.lat, loc.speed_kmh))
    return {"ok": True}


@app.post("/rides/{ride_id}/accept")
def accept(ride_id: int, user: dict = Depends(require("driver"))):
    with db() as c:
        st = pricing.load_settings(c)
        off = c.execute("""SELECT id, kind, saved_km FROM ride_offers
                           WHERE ride_id=%s AND driver_id=%s AND status='pending' AND expires_at > now()""",
                        (ride_id, user["id"])).fetchone()
        if not off:
            raise HTTPException(409, "Angebot abgelaufen oder vergeben")
        if off[1] == "pool":  # Zusteigen: Platz und Fahrtenart nochmal prüfen
            n, solo = c.execute("""SELECT COUNT(*), COALESCE(BOOL_OR(NOT shared), false) FROM rides
                                   WHERE driver_id=%s AND status IN ('accepted','in_progress')""",
                                (user["id"],)).fetchone()
            if n >= int(st["seats"]) or solo or n == 0:
                c.execute("UPDATE ride_offers SET status='expired' WHERE id=%s", (off[0],))
                c.commit()
                raise HTTPException(409, "Das Fahrzeug ist inzwischen voll oder die Fahrt hat sich geändert")
        ride = c.execute("SELECT quote, shared FROM rides WHERE id=%s AND status='requested'", (ride_id,)).fetchone()
        if not ride or not ride[0]:
            raise HTTPException(409, "Die Fahrt ist nicht mehr offen")
        quote_, shared = ride
        drv = c.execute("""SELECT d.company_id, co.fee_per_ride FROM drivers d
                           LEFT JOIN companies co ON co.id=d.company_id WHERE d.user_id=%s""",
                        (user["id"],)).fetchone()
        company_id, company_fee = drv
        if company_id is None:  # eigener Fahrer: unser Tarif
            fare, partner_fee = (quote_["own_shared"] if shared else quote_["own"]), None
        else:  # Fahrer einer Partnerfirma: Kunde zahlt uns nur die Servicegebühr
            fare = quote_["partner"]
            partner_fee = float(company_fee) if company_fee is not None else st["partner_fee"]
        c.execute("UPDATE ride_offers SET status='accepted' WHERE id=%s", (off[0],))
        c.execute("""UPDATE rides SET status='accepted', driver_id=%s, accepted_at=now(),
                     pooled=%s, saved_km=%s, fare=%s, price=%s, company_id=%s, partner_fee=%s
                     WHERE id=%s AND status='requested'""",
                  (user["id"], off[1] == "pool", off[2], Jsonb(fare), fare["total"], company_id,
                   partner_fee, ride_id))
        c.execute("UPDATE drivers SET status='busy' WHERE user_id=%s", (user["id"],))
    return {"ok": True}


@app.post("/rides/{ride_id}/decline")
def decline(ride_id: int, user: dict = Depends(require("driver"))):
    with db() as c:
        c.execute("""UPDATE ride_offers SET status='declined'
                     WHERE ride_id=%s AND driver_id=%s AND status='pending'""",
                  (ride_id, user["id"]))
        dispatch(c, ride_id)
    return {"ok": True}


@app.post("/rides/{ride_id}/start")
def start(ride_id: int, user: dict = Depends(require("driver"))):
    """Fahrer: Kunde abgeholt, Fahrt läuft."""
    with db() as c:
        ok = c.execute("""UPDATE rides SET status='in_progress'
                          WHERE id=%s AND driver_id=%s AND status='accepted' RETURNING 1""",
                       (ride_id, user["id"])).fetchone()
    if not ok:
        raise HTTPException(409, "Fahrt kann nicht gestartet werden")
    return {"ok": True}


@app.post("/rides/{ride_id}/stops/{position}/reached")
def stop_reached(ride_id: int, position: int, user: dict = Depends(require("driver"))):
    """Fahrer: Ziel Nr. <position> erreicht. Nach dem letzten Ziel endet die Fahrt."""
    with db() as c:
        ok = c.execute("""SELECT 1 FROM rides WHERE id=%s AND driver_id=%s AND status='in_progress'""",
                       (ride_id, user["id"])).fetchone()
        if not ok:
            raise HTTPException(409, "Keine laufende Fahrt")
        c.execute("""UPDATE ride_stops SET reached_at=now()
                     WHERE ride_id=%s AND position=%s AND reached_at IS NULL""",
                  (ride_id, position))
        open_stops = c.execute(
            "SELECT COUNT(*) FROM ride_stops WHERE ride_id=%s AND reached_at IS NULL",
            (ride_id,)).fetchone()[0]
        if open_stops == 0:
            c.execute("""UPDATE rides SET status='completed', finished_at=now(),
                         receipt_no='Q-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('receipt_seq')::text, 6, '0')
                         WHERE id=%s""", (ride_id,))
            c.execute("""UPDATE drivers SET status='free' WHERE user_id=%s AND NOT EXISTS
                         (SELECT 1 FROM rides WHERE driver_id=%s AND status IN ('accepted','in_progress'))""",
                      (user["id"], user["id"]))
    return {"remaining_stops": open_stops}


# ---------------------------------------------------------------- Admin
admin = Depends(require("admin"))


@app.get("/admin/overview")
def admin_overview(_: dict = admin):
    with db() as c:
        cnt = dict(c.execute("SELECT status, COUNT(*) FROM drivers d JOIN users u ON u.id=d.user_id "
                             "WHERE u.active GROUP BY status").fetchall())
        rides_today = c.execute("SELECT COUNT(*) FROM rides WHERE requested_at >= date_trunc('day', now())"
                                ).fetchone()[0]
        completed_today = c.execute("SELECT COUNT(*) FROM rides WHERE status='completed' "
                                    "AND finished_at >= date_trunc('day', now())").fetchone()[0]
        avg = c.execute("SELECT AVG(stars) FROM ratings").fetchone()[0]
        shared_today = c.execute("SELECT COUNT(*) FROM rides WHERE shared AND "
                                 "requested_at >= date_trunc('day', now())").fetchone()[0]
        pooled_today = c.execute("SELECT COUNT(*) FROM rides WHERE pooled AND "
                                 "requested_at >= date_trunc('day', now())").fetchone()[0]
        saved_km = float(c.execute("""SELECT COALESCE(SUM(saved_km),0) FROM rides WHERE pooled AND
                                      status='completed' AND finished_at > now() - interval '30 days'"""
                                   ).fetchone()[0])
        revenue = float(c.execute("""SELECT COALESCE(SUM(price),0) FROM rides WHERE status='completed'
                                     AND finished_at >= date_trunc('day', now())""").fetchone()[0])
        cost_km = pricing.load_settings(c)["cost_per_km"]
        pf_today = float(c.execute("""SELECT COALESCE(SUM(partner_fee),0) FROM rides WHERE status='completed'
                                      AND finished_at >= date_trunc('day', now())""").fetchone()[0])
        pf_30 = float(c.execute("""SELECT COALESCE(SUM(partner_fee),0) FROM rides WHERE status='completed'
                                   AND finished_at > now() - interval '30 days'""").fetchone()[0])
        partner_rides_today = c.execute("""SELECT COUNT(*) FROM rides WHERE status='completed' AND company_id IS NOT NULL
                                           AND finished_at >= date_trunc('day', now())""").fetchone()[0]
    return {"partner_fees_today": round(pf_today, 2), "partner_fees_30d": round(pf_30, 2),
            "partner_rides_today": partner_rides_today, "shared_today": shared_today, "pooled_today": pooled_today,
            "saved_km_30d": round(saved_km, 1), "saved_cost_30d": round(saved_km * cost_km, 2),
            "revenue_today": round(revenue, 2),
            "rides_today": rides_today, "completed_today": completed_today,
            "drivers_free": cnt.get("free", 0), "drivers_busy": cnt.get("busy", 0),
            "drivers_offline": cnt.get("offline", 0),
            "avg_rating": round(float(avg), 2) if avg is not None else None}


@app.get("/admin/drivers")
def admin_drivers(days: int = 30, _: dict = admin):
    """Alle Fahrer mit Status, Position, Bewertung, Fahrten, Kilometer und Geschwindigkeit."""
    days = max(1, min(days, 365))
    with db() as c:
        rows = c.execute("""
            SELECT u.id, u.name, u.email, u.active, d.status, d.rating_avg, d.rating_count,
                   v.model, v.plate, ST_Y(d.location::geometry), ST_X(d.location::geometry),
                   d.last_seen, COALESCE(r.cnt,0), COALESCE(k.km,0), k.max_speed, k.avg_speed,
                   v.vehicle_type, d.company_id, co.name
            FROM users u
            JOIN drivers d ON d.user_id=u.id
            LEFT JOIN vehicles v ON v.id=d.vehicle_id
            LEFT JOIN companies co ON co.id=d.company_id
            LEFT JOIN (SELECT driver_id, COUNT(*) cnt FROM rides
                       WHERE status='completed' AND finished_at > now() - make_interval(days => %s)
                       GROUP BY driver_id) r ON r.driver_id=u.id
            LEFT JOIN (SELECT driver_id,
                              SUM(CASE WHEN dist < 2000 THEN dist ELSE 0 END)/1000.0 km,
                              MAX(speed_kmh) max_speed, AVG(NULLIF(speed_kmh,0)) avg_speed
                       FROM (SELECT driver_id, speed_kmh,
                                    ST_Distance(location, LAG(location) OVER
                                      (PARTITION BY driver_id ORDER BY recorded_at)) dist
                             FROM location_log
                             WHERE recorded_at > now() - make_interval(days => %s)) t
                       GROUP BY driver_id) k ON k.driver_id=u.id
            WHERE u.role='driver' ORDER BY u.name""", (days, days)).fetchall()
    f = lambda x: None if x is None else float(x)
    return [{"id": i, "name": n, "email": e, "active": a, "status": s,
             "rating_avg": f(ra), "rating_count": rc, "vehicle": vm, "plate": pl,
             "lat": la, "lng": ln, "last_seen": ls.isoformat() if ls else None,
             "rides": rides, "km": round(float(km), 1), "max_speed": f(ms),
             "avg_speed": None if avs is None else round(float(avs), 1),
             "vehicle_type": vt, "company_id": cid, "company": cname}
            for i, n, e, a, s, ra, rc, vm, pl, la, ln, ls, rides, km, ms, avs, vt, cid, cname in rows]


@app.post("/admin/drivers")
def admin_create_driver(b: NewDriver, _: dict = admin):
    try:
        with db() as c:
            if b.company_id is not None and not c.execute(
                    "SELECT 1 FROM companies WHERE id=%s AND active", (b.company_id,)).fetchone():
                raise HTTPException(404, "Firma nicht gefunden oder nicht aktiv")
            vid = c.execute("INSERT INTO vehicles (model, plate, vehicle_type) VALUES (%s,%s,%s) RETURNING id",
                            (b.vehicle_model.strip(), b.plate.strip().upper(), b.vehicle_type)).fetchone()[0]
            uid = c.execute("""INSERT INTO users (name,email,password_hash,role)
                               VALUES (%s,%s,%s,'driver') RETURNING id""",
                            (b.name.strip(), b.email.lower(), hash_password(b.password))).fetchone()[0]
            c.execute("INSERT INTO drivers (user_id, vehicle_id, company_id) VALUES (%s,%s,%s)",
                      (uid, vid, b.company_id))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "E-Mail oder Kennzeichen existiert bereits")
    return {"id": uid}


# ---------------------------------------------------------------- Admin: Partnerfirmen
@app.get("/admin/companies")
def admin_companies(_: dict = admin):
    with db() as c:
        st = pricing.load_settings(c)
        rows = c.execute("""
            SELECT co.id, co.name, co.contact, co.address, co.fee_per_ride, co.active,
                   (SELECT COUNT(*) FROM drivers d WHERE d.company_id=co.id),
                   (SELECT COUNT(*) FROM rides r WHERE r.company_id=co.id AND r.status='completed'
                      AND r.finished_at > now() - interval '30 days'),
                   (SELECT COALESCE(SUM(r.partner_fee),0) FROM rides r WHERE r.company_id=co.id
                      AND r.status='completed' AND r.finished_at > now() - interval '30 days')
            FROM companies co ORDER BY co.name""").fetchall()
    return [{"id": i, "name": n, "contact": ct, "address": ad,
             "fee_per_ride": None if fee is None else float(fee), "effective_fee": float(fee) if fee is not None else st["partner_fee"],
             "active": ac, "drivers": nd, "rides_30d": nr, "fees_30d": round(float(nf), 2)}
            for i, n, ct, ad, fee, ac, nd, nr, nf in rows]


@app.post("/admin/companies")
def admin_create_company(b: CompanyBody, _: dict = admin):
    try:
        with db() as c:
            cid = c.execute("""INSERT INTO companies (name, contact, address, fee_per_ride)
                               VALUES (%s,%s,%s,%s) RETURNING id""",
                            (b.name.strip(), b.contact.strip(), b.address.strip(), b.fee_per_ride)).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Eine Firma mit diesem Namen gibt es schon")
    return {"id": cid}


@app.patch("/admin/companies/{company_id}")
def admin_patch_company(company_id: int, b: CompanyPatch, _: dict = admin):
    """Firma ein-/ausschalten (Fahrer erhalten dann keine Anfragen mehr) oder Gebühr pro Fahrt ändern."""
    with db() as c:
        if not c.execute("SELECT 1 FROM companies WHERE id=%s", (company_id,)).fetchone():
            raise HTTPException(404, "Firma nicht gefunden")
        if b.active is not None:
            c.execute("UPDATE companies SET active=%s WHERE id=%s", (b.active, company_id))
            if not b.active:
                c.execute("""UPDATE drivers SET status='offline' WHERE company_id=%s AND status='free'""", (company_id,))
        if b.use_default_fee:
            c.execute("UPDATE companies SET fee_per_ride=NULL WHERE id=%s", (company_id,))
        elif b.fee_per_ride is not None:
            c.execute("UPDATE companies SET fee_per_ride=%s WHERE id=%s", (b.fee_per_ride, company_id))
    return {"ok": True}


@app.get("/admin/companies/{company_id}/statement")
def admin_company_statement(company_id: int, month: str, _: dict = admin):
    """Monatsabrechnung: beendete Fahrten der Firma und die Gebühr, die sie uns schuldet."""
    import re
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "Monat im Format JJJJ-MM angeben, zum Beispiel 2026-11")
    with db() as c:
        co = c.execute("SELECT name FROM companies WHERE id=%s", (company_id,)).fetchone()
        if not co:
            raise HTTPException(404, "Firma nicht gefunden")
        rows = c.execute("""SELECT r.id, r.finished_at, r.receipt_no, r.distance_km, r.partner_fee
                            FROM rides r
                            WHERE r.company_id=%s AND r.status='completed'
                              AND to_char(r.finished_at AT TIME ZONE 'Europe/Berlin', 'YYYY-MM') = %s
                            ORDER BY r.finished_at""", (company_id, month)).fetchall()
    items = [{"ride_id": i, "finished_at": f.isoformat(), "receipt_no": rn,
              "distance_km": None if km is None else float(km), "fee": float(fee or 0)}
             for i, f, rn, km, fee in rows]
    return {"company": co[0], "month": month, "rides": len(items),
            "total_fee": round(sum(x["fee"] for x in items), 2), "items": items}


@app.patch("/admin/drivers/{driver_id}")
def admin_set_active(driver_id: int, b: ActiveBody, _: dict = admin):
    """Fahrer sperren (active=false) oder wieder freigeben."""
    with db() as c:
        row = c.execute("""SELECT d.status FROM users u JOIN drivers d ON d.user_id=u.id
                           WHERE u.id=%s AND u.role='driver'""", (driver_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Fahrer nicht gefunden")
        if not b.active and row[0] == "busy":
            raise HTTPException(409, "Fahrer hat gerade eine laufende Fahrt")
        c.execute("UPDATE users SET active=%s WHERE id=%s", (b.active, driver_id))
        if not b.active:
            c.execute("UPDATE drivers SET status='offline' WHERE user_id=%s", (driver_id,))
    return {"ok": True}


@app.post("/admin/drivers/{driver_id}/password")
def admin_reset_password(driver_id: int, b: PasswordBody, _: dict = admin):
    with db() as c:
        ok = c.execute("""UPDATE users SET password_hash=%s, failed_attempts=0, locked_until=NULL
                          WHERE id=%s AND role='driver' RETURNING 1""",
                       (hash_password(b.password), driver_id)).fetchone()
    if not ok:
        raise HTTPException(404, "Fahrer nicht gefunden")
    return {"ok": True}


@app.get("/admin/rides")
def admin_rides(limit: int = 50, _: dict = admin):
    """Letzte Fahrten mit Kunde, Fahrer, Status und Zielen."""
    limit = max(1, min(limit, 200))
    with db() as c:
        rows = c.execute("""
            SELECT r.id, r.status, cu.name, du.name, r.requested_at, r.finished_at,
                   (SELECT string_agg(address, ' → ' ORDER BY position)
                      FROM ride_stops WHERE ride_id=r.id),
                   r.price, r.shared, r.pooled, r.saved_km, co.name, r.vehicle_type, r.payment_method,
                   r.receipt_no
            FROM rides r
            LEFT JOIN companies co ON co.id=r.company_id
            JOIN users cu ON cu.id=r.customer_id
            LEFT JOIN users du ON du.id=r.driver_id
            ORDER BY r.id DESC LIMIT %s""", (limit,)).fetchall()
    iso = lambda t: t.isoformat() if t else None
    f = lambda x: None if x is None else float(x)
    return [{"id": i, "status": st, "customer": cn, "driver": dn,
             "requested_at": iso(rq), "finished_at": iso(fn), "route": route,
             "price": f(pr), "shared": sh, "pooled": po, "saved_km": f(sk),
             "company": comp, "vehicle_type": vt, "payment_method": pm, "receipt_no": rno}
            for i, st, cn, dn, rq, fn, route, pr, sh, po, sk, comp, vt, pm, rno in rows]


@app.get("/admin/settings")
def admin_get_settings(_: dict = admin):
    with db() as c:
        st = pricing.load_settings(c)
    return pricing.settings_view(st)


@app.put("/admin/settings")
def admin_put_settings(body: dict[str, float | str], _: dict = admin):
    try:
        with db() as c:
            pricing.save_settings(c, body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@app.get("/admin/ratings")
def admin_ratings(limit: int = 50, _: dict = admin):
    limit = max(1, min(limit, 200))
    with db() as c:
        rows = c.execute("""
            SELECT ra.id, ra.stars, ra.comment, ra.created_at, du.name, cu.name
            FROM ratings ra
            JOIN rides r ON r.id=ra.ride_id
            JOIN users du ON du.id=ra.driver_id
            JOIN users cu ON cu.id=r.customer_id
            ORDER BY ra.id DESC LIMIT %s""", (limit,)).fetchall()
    return [{"id": i, "stars": st, "comment": cm, "created_at": ca.isoformat(),
             "driver": dn, "customer": cn} for i, st, cm, ca, dn, cn in rows]


@app.get("/admin/speeding")
def admin_speeding(limit_kmh: float = 100, hours: int = 24, _: dict = admin):
    """Gemeldete Geschwindigkeiten über dem Grenzwert (vom Handy des Fahrers, nicht straßenbezogen)."""
    limit_kmh = max(10, min(limit_kmh, 300))
    hours = max(1, min(hours, 24 * 30))
    with db() as c:
        rows = c.execute("""
            SELECT u.name, l.speed_kmh, l.recorded_at,
                   ST_Y(l.location::geometry), ST_X(l.location::geometry)
            FROM location_log l JOIN users u ON u.id=l.driver_id
            WHERE l.speed_kmh > %s AND l.recorded_at > now() - make_interval(hours => %s)
            ORDER BY l.recorded_at DESC LIMIT 200""", (limit_kmh, hours)).fetchall()
    return [{"driver": n, "speed_kmh": float(sp), "recorded_at": t.isoformat(),
             "lat": la, "lng": ln} for n, sp, t, la, ln in rows]


# ---------------------------------------------------------------- Admin-Webseite
ADMIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "admin")
DASH_HEADERS = {
    # Nur eigene Skripte; Kartenbilder von OpenStreetMap; keine Einbettung in fremde Seiten
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data: https://*.tile.openstreetmap.org; "
                                "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",
}


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(ADMIN_DIR, "index.html"), headers=DASH_HEADERS)


app.mount("/dashboard/static", StaticFiles(directory=os.path.join(ADMIN_DIR, "static")), name="dash")
