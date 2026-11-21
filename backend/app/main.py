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

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/rides")
def request_ride(r: RideRequest):
    customer_id = 1  # TODO: aus JWT
    with db() as c:
        ride_id = c.execute(
            """INSERT INTO rides (customer_id, pickup)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) RETURNING id""",
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
                  (ride_id, position))
        open_stops = c.execute(
            "SELECT COUNT(*) FROM ride_stops WHERE ride_id=%s AND reached_at IS NULL",
            (ride_id,)).fetchone()[0]
        if open_stops == 0:
            c.execute("UPDATE rides SET status='completed', finished_at=now() WHERE id=%s", (ride_id,))
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
    return {"ok": True}
