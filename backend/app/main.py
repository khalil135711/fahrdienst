<<<<<<< HEAD
"""Fahrdienst-API mit Anmeldung (JWT) und Rollen: customer, driver, admin.

- Kunden registrieren sich selbst (POST /auth/register).
- Fahrer legt nur der Admin an (POST /admin/drivers).
- Der erste Admin wird beim Start aus ADMIN_EMAIL / ADMIN_PASSWORD erzeugt.

Zuweisung: Anfrage -> Angebot an nächsten freien Fahrer (OFFER_SECONDS) ->
Annehmen / Ablehnen / Timeout -> nächster Fahrer -> sonst 'no_driver'."""
import math
import os
from contextlib import asynccontextmanager
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AfterValidator, BaseModel, EmailStr, Field

from .auth import (LOCK_MINUTES, MAX_FAILED, DUMMY_HASH, create_token,
                   hash_password, require, verify_password, current_user)
from .db import db

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
    lat: float | None = None
    lng: float | None = None


class RideRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)  # Abfahrt = Standort des Kunden
    lng: float = Field(ge=-180, le=180)
    stops: list[Stop] = Field(min_length=1, max_length=4)


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
    nxt = c.execute("""
        SELECT d.user_id FROM drivers d
        JOIN users u ON u.id=d.user_id AND u.active
        JOIN rides r ON r.id=%s
        WHERE d.status='free' AND d.location IS NOT NULL
          AND ST_DWithin(d.location, r.pickup, %s)
          AND d.user_id NOT IN (SELECT driver_id FROM ride_offers WHERE ride_id=%s)
        ORDER BY ST_Distance(d.location, r.pickup) LIMIT 1""",
        (ride_id, RADIUS_M, ride_id)).fetchone()
    if nxt:
        c.execute("""INSERT INTO ride_offers (ride_id, driver_id, expires_at)
                     VALUES (%s,%s, now() + (%s * interval '1 second'))""",
                  (ride_id, nxt[0], OFFER_SECONDS))
    else:
        c.execute("UPDATE rides SET status='no_driver' WHERE id=%s", (ride_id,))


def stops_of(c, ride_id: int):
    rows = c.execute("""SELECT position, address, reached_at IS NOT NULL
                        FROM ride_stops WHERE ride_id=%s ORDER BY position""",
                     (ride_id,)).fetchall()
    return [{"position": p, "address": a, "reached": r} for p, a, r in rows]

=======
"""Minimale FastAPI-Grundlage: Fahrer-Suche im Umkreis, Status, Position, Bewertung.
Authentifizierung (JWT) und Fehlerbehandlung müssen noch ergänzt werden."""
import os
import psycopg
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_URL = os.environ["DATABASE_URL"]
app = FastAPI(title="Fahrdienst API")
# Entwicklung: alles erlaubt. In Produktion auf Ihre Domain beschränken!
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

def db():
    return psycopg.connect(DB_URL)

class Stop(BaseModel):
    address: str
    lat: float | None = None
    lng: float | None = None

class RideRequest(BaseModel):
    # Abfahrt = aktueller Standort des Kunden (GPS)
    lat: float
    lng: float
    # 1 bis 4 Ziele, werden in dieser Reihenfolge angefahren
    stops: list[Stop] = Field(min_length=1, max_length=4)

class Location(BaseModel):
    lat: float
    lng: float
    speed_kmh: float

class Rating(BaseModel):
    stars: int
    comment: str = ""
>>>>>>> origin/main

@app.get("/health")
def health():
    return {"ok": True}

<<<<<<< HEAD

# ---------------------------------------------------------------- Kunde
@app.post("/rides")
def request_ride(r: RideRequest, user: dict = Depends(require("customer"))):
=======
@app.post("/rides")
def request_ride(r: RideRequest):
    customer_id = 1  # TODO: aus JWT
>>>>>>> origin/main
    with db() as c:
        ride_id = c.execute(
            """INSERT INTO rides (customer_id, pickup)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) RETURNING id""",
<<<<<<< HEAD
            (user["id"], r.lng, r.lat)).fetchone()[0]
        for i, st in enumerate(r.stops, start=1):
            c.execute(
                """INSERT INTO ride_stops (ride_id, position, address, location)
                   VALUES (%s,%s,%s, ST_SetSRID(ST_MakePoint(%s::float8,%s::float8),4326)::geography)""",
                (ride_id, i, st.address.strip(), st.lng, st.lat))
        dispatch(c, ride_id)
        status = c.execute("SELECT status FROM rides WHERE id=%s", (ride_id,)).fetchone()[0]
    return {"id": ride_id, "status": status}


@app.get("/rides/{ride_id}")
def get_ride(ride_id: int, user: dict = Depends(current_user)):
    """Status, Fahrer, ETA. Nur der Kunde der Fahrt, der zugewiesene Fahrer oder ein Admin."""
    with db() as c:
        row = c.execute("""
            SELECT r.status, r.customer_id, r.driver_id, u.name, d.rating_avg,
                   v.model || ' • ' || v.plate,
                   ST_Y(d.location::geometry), ST_X(d.location::geometry),
                   ST_Distance(d.location, r.pickup)
            FROM rides r
            LEFT JOIN drivers d ON d.user_id = r.driver_id
            LEFT JOIN users u ON u.id = r.driver_id
            LEFT JOIN vehicles v ON v.id = d.vehicle_id
            WHERE r.id=%s""", (ride_id,)).fetchone()
        status, cust, drv, name, rating, vehicle, dlat, dlng, dist = row if row else (None,) * 9
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
                "eta_minutes": eta, "stops": stops_of(c, ride_id)}


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
@app.get("/drivers/me/state")
def driver_state(user: dict = Depends(require("driver"))):
    """Vom Fahrer regelmäßig abgefragt: aktuelles Angebot und laufende Fahrt."""
    with db() as c:
        offer = None
        o = c.execute("""
            SELECT o.ride_id, EXTRACT(EPOCH FROM (o.expires_at - now())), u.name,
                   ST_Distance(d.location, r.pickup)
            FROM ride_offers o
            JOIN rides r ON r.id=o.ride_id
            JOIN users u ON u.id=r.customer_id
            JOIN drivers d ON d.user_id=o.driver_id
            WHERE o.driver_id=%s AND o.status='pending' AND o.expires_at > now()
              AND r.status='requested'
            ORDER BY o.offered_at LIMIT 1""", (user["id"],)).fetchone()
        if o:
            offer = {"ride_id": o[0], "seconds_left": int(o[1]), "customer": o[2],
                     "distance_m": int(o[3] or 0), "stops": stops_of(c, o[0])}
        active = None
        a = c.execute("""SELECT r.id, r.status, u.name FROM rides r JOIN users u ON u.id=r.customer_id
                         WHERE r.driver_id=%s AND r.status IN ('accepted','in_progress')
                         ORDER BY r.id DESC LIMIT 1""", (user["id"],)).fetchone()
        if a:
            active = {"ride_id": a[0], "status": a[1], "customer": a[2],
                      "stops": stops_of(c, a[0])}
        return {"offer": offer, "active": active}


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
        o = c.execute("""UPDATE ride_offers SET status='accepted'
                         WHERE ride_id=%s AND driver_id=%s AND status='pending' AND expires_at > now()
                         RETURNING id""", (ride_id, user["id"])).fetchone()
        if not o:
            raise HTTPException(409, "Angebot abgelaufen oder vergeben")
        c.execute("""UPDATE rides SET status='accepted', driver_id=%s, accepted_at=now()
                     WHERE id=%s AND status='requested'""", (user["id"], ride_id))
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
=======
            (customer_id, r.lng, r.lat)).fetchone()[0]
        for i, st in enumerate(r.stops, start=1):
            loc = None if st.lat is None else (st.lng, st.lat)
            c.execute(
                """INSERT INTO ride_stops (ride_id, position, address, location)
                   VALUES (%s,%s,%s, CASE WHEN %s::float IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography END)""",
                (ride_id, i, st.address, st.lng, st.lng, st.lat))
        drivers = c.execute(
            """SELECT user_id, ST_Distance(location, ST_MakePoint(%s,%s)::geography) AS m
               FROM drivers WHERE status='free'
               AND ST_DWithin(location, ST_MakePoint(%s,%s)::geography, 5000)
               ORDER BY m LIMIT 5""", (r.lng, r.lat, r.lng, r.lat)).fetchall()
    # TODO: Anfrage nacheinander per Push an 'drivers' senden (je 15 Sek.)
    return {"id": ride_id, "status": "requested", "candidates": len(drivers)}

@app.post("/rides/{ride_id}/stops/{position}/reached")
def stop_reached(ride_id: int, position: int):
    """Fahrer meldet: Ziel Nr. <position> erreicht. Nach dem letzten Ziel endet die Fahrt."""
    with db() as c:
        c.execute("UPDATE ride_stops SET reached_at=now() WHERE ride_id=%s AND position=%s",
>>>>>>> origin/main
                  (ride_id, position))
        open_stops = c.execute(
            "SELECT COUNT(*) FROM ride_stops WHERE ride_id=%s AND reached_at IS NULL",
            (ride_id,)).fetchone()[0]
        if open_stops == 0:
            c.execute("UPDATE rides SET status='completed', finished_at=now() WHERE id=%s", (ride_id,))
<<<<<<< HEAD
            c.execute("UPDATE drivers SET status='free' WHERE user_id=%s", (user["id"],))
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
    return {"rides_today": rides_today, "completed_today": completed_today,
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
                   d.last_seen, COALESCE(r.cnt,0), COALESCE(k.km,0), k.max_speed, k.avg_speed
            FROM users u
            JOIN drivers d ON d.user_id=u.id
            LEFT JOIN vehicles v ON v.id=d.vehicle_id
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
             "avg_speed": None if avs is None else round(float(avs), 1)}
            for i, n, e, a, s, ra, rc, vm, pl, la, ln, ls, rides, km, ms, avs in rows]


@app.post("/admin/drivers")
def admin_create_driver(b: NewDriver, _: dict = admin):
    try:
        with db() as c:
            vid = c.execute("INSERT INTO vehicles (model, plate) VALUES (%s,%s) RETURNING id",
                            (b.vehicle_model.strip(), b.plate.strip().upper())).fetchone()[0]
            uid = c.execute("""INSERT INTO users (name,email,password_hash,role)
                               VALUES (%s,%s,%s,'driver') RETURNING id""",
                            (b.name.strip(), b.email.lower(), hash_password(b.password))).fetchone()[0]
            c.execute("INSERT INTO drivers (user_id, vehicle_id) VALUES (%s,%s)", (uid, vid))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "E-Mail oder Kennzeichen existiert bereits")
    return {"id": uid}


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
=======
    return {"remaining_stops": open_stops}

@app.post("/drivers/me/status")
def set_status(body: dict):
    driver_id = 1  # TODO: aus JWT
    with db() as c:
        c.execute("UPDATE drivers SET status=%s WHERE user_id=%s",
                  (body["status"], driver_id))
    return {"ok": True}

@app.post("/drivers/me/location")
def update_location(loc: Location):
    driver_id = 1  # TODO: aus JWT
    with db() as c:
        c.execute("""UPDATE drivers SET location=ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                     last_seen=now() WHERE user_id=%s""", (loc.lng, loc.lat, driver_id))
        c.execute("""INSERT INTO location_log (driver_id, location, speed_kmh)
                     VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)""",
                  (driver_id, loc.lng, loc.lat, loc.speed_kmh))
    return {"ok": True}

@app.post("/rides/{ride_id}/rating")
def rate(ride_id: int, r: Rating):
    with db() as c:
        row = c.execute("SELECT driver_id FROM rides WHERE id=%s", (ride_id,)).fetchone()
        c.execute("INSERT INTO ratings (ride_id, driver_id, stars, comment) VALUES (%s,%s,%s,%s)",
                  (ride_id, row[0], r.stars, r.comment))
        c.execute("""UPDATE drivers SET
                     rating_avg=(SELECT AVG(stars) FROM ratings WHERE driver_id=%s),
                     rating_count=(SELECT COUNT(*) FROM ratings WHERE driver_id=%s)
                     WHERE user_id=%s""", (row[0], row[0], row[0]))
>>>>>>> origin/main
    return {"ok": True}
