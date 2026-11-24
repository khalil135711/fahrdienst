"""Geteilte Fahrten (Pooling): Prüft, ob ein neuer Fahrgast zu einer laufenden Fahrt zusteigen kann.

Vorgehen:
  1. Fahrzeuge in der Nähe, die nur geteilte Fahrten fahren und noch Platz haben.
  2. Für jedes: Wie sieht die Route ohne und mit dem neuen Fahrgast aus? (günstigstes Einfügen)
  3. Zulässig nur, wenn kein Fahrgast zu viel Umweg hat und das Zusammenlegen mindestens 20 %
     der Einzelstrecke des neuen Fahrgasts spart.

Entfernungen sind Luftlinie x Straßenfaktor (Schätzung). Die Reihenfolge ist eine Heuristik,
keine mathematisch beste Tour. Der Fahrer entscheidet vor Ort."""
import math
import os
from dataclasses import dataclass

ROAD_FACTOR = float(os.environ.get("ROAD_FACTOR", "1.3"))
MIN_SAVED_SHARE = 0.2  # Zusammenlegen muss mind. 20 % der Einzelstrecke sparen

Point = tuple  # (lat, lng)


def haversine_km(a: Point, b: Point) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def dist(a: Point, b: Point) -> float:
    return haversine_km(a, b) * ROAD_FACTOR


@dataclass
class PRide:
    id: int
    pickup: Point
    pickup_done: bool
    stops: list  # [(position, Point)], noch nicht erreichte Ziele in Reihenfolge


@dataclass
class Event:
    ride_id: int
    kind: str  # 'pickup' | 'drop'
    point: Point
    stop_pos: int = 0


def chain_km(pickup: Point, stops: list) -> float:
    """Strecke Abholung -> Ziel 1 -> ... -> Ziel n (stops = Liste von Punkten)."""
    total, cur = 0.0, pickup
    for p in stops:
        total += dist(cur, p)
        cur = p
    return total


def greedy_plan(pos: Point, rides: list) -> list:
    """Reihenfolge nach 'nächster Halt zuerst', Abholung immer vor den Zielen des Fahrgasts."""
    seqs = {}
    for r in rides:
        seq = [] if r.pickup_done else [Event(r.id, "pickup", r.pickup)]
        seq += [Event(r.id, "drop", pt, sp) for sp, pt in r.stops]
        seqs[r.id] = seq
    ptr = {i: 0 for i in seqs}
    events, cur = [], pos
    while any(ptr[i] < len(seqs[i]) for i in seqs):
        best = None
        for rid, seq in seqs.items():
            if ptr[rid] < len(seq):
                ev = seq[ptr[rid]]
                dd = dist(cur, ev.point)
                if best is None or dd < best[0]:
                    best = (dd, rid, ev)
        _, rid, ev = best
        events.append(ev)
        ptr[rid] += 1
        cur = ev.point
    return events


def path_len(pos: Point, events: list) -> float:
    total, cur = 0.0, pos
    for e in events:
        total += dist(cur, e.point)
        cur = e.point
    return total


def ride_span(pos: Point, events: list, ride: PRide) -> float:
    """Strecke, die der Fahrgast im Fahrzeug verbringt (ab Abholung bis zum letzten Ziel)."""
    cum, cur, acc = [], pos, 0.0
    for e in events:
        acc += dist(cur, e.point)
        cum.append(acc)
        cur = e.point
    start = 0.0
    if not ride.pickup_done:
        idx = next((i for i, e in enumerate(events) if e.ride_id == ride.id and e.kind == "pickup"), None)
        if idx is None:
            return 0.0
        start = cum[idx]
    last = max((i for i, e in enumerate(events) if e.ride_id == ride.id), default=None)
    return 0.0 if last is None else cum[last] - start


def best_insertion(pos: Point, events: list, new: PRide) -> tuple:
    """Fügt Abholung und Zielfolge des neuen Fahrgasts an der günstigsten Stelle ein."""
    pick = Event(new.id, "pickup", new.pickup)
    drops = [Event(new.id, "drop", pt, sp) for sp, pt in new.stops]
    best = None
    n = len(events)
    for i in range(n + 1):
        for j in range(i, n + 1):
            cand = events[:i] + [pick] + events[i:j] + drops + events[j:]
            length = path_len(pos, cand)
            if best is None or length < best[0]:
                best = (length, cand)
    return best


def evaluate(pos: Point, existing: list, new: PRide, s: dict):
    """Gibt {'detour_km','saved_km','solo_km','plan'} zurück, oder None wenn das Zusteigen nicht passt."""
    old_plan = greedy_plan(pos, existing)
    old_len = path_len(pos, old_plan)
    new_len, new_plan = best_insertion(pos, old_plan, new)
    detour = new_len - old_len
    solo = chain_km(new.pickup, [pt for _, pt in new.stops])
    if solo <= 0:
        return None
    for r in existing:
        before, after = ride_span(pos, old_plan, r), ride_span(pos, new_plan, r)
        if after > before * s["pool_max_ratio"] or after - before > s["pool_max_extra_km"]:
            return None
    own = ride_span(pos, new_plan, new)
    if own > solo * s["pool_max_ratio"] or own - solo > s["pool_max_extra_km"]:
        return None
    saved = solo - detour
    if saved < MIN_SAVED_SHARE * solo:
        return None
    return {"detour_km": round(detour, 2), "saved_km": round(saved, 2),
            "solo_km": round(solo, 2), "plan": new_plan}


# ---------------------------------------------------------------- Datenbank
def load_driver_rides(c, driver_id: int):
    """Laufende Fahrten eines Fahrers. None, wenn Koordinaten fehlen (dann nicht planbar)."""
    rows = c.execute("""SELECT id, status, ST_Y(pickup::geometry), ST_X(pickup::geometry)
                        FROM rides WHERE driver_id=%s AND status IN ('accepted','in_progress')
                        ORDER BY id""", (driver_id,)).fetchall()
    rides = []
    for rid, status, la, lo in rows:
        stops = c.execute("""SELECT position, ST_Y(location::geometry), ST_X(location::geometry)
                             FROM ride_stops WHERE ride_id=%s AND reached_at IS NULL
                             ORDER BY position""", (rid,)).fetchall()
        if any(sla is None for _, sla, _ in stops):
            return None
        rides.append(PRide(rid, (la, lo), status == "in_progress", [(p, (a, b)) for p, a, b in stops]))
    return rides


def best_candidate(c, ride_id: int, s: dict):
    """Bestes Fahrzeug zum Zusteigen für diese (geteilte) Fahrt, oder None."""
    row = c.execute("SELECT ST_Y(pickup::geometry), ST_X(pickup::geometry), shared FROM rides WHERE id=%s",
                    (ride_id,)).fetchone()
    if not row or not row[2]:
        return None
    stops = c.execute("""SELECT position, ST_Y(location::geometry), ST_X(location::geometry)
                         FROM ride_stops WHERE ride_id=%s ORDER BY position""", (ride_id,)).fetchall()
    if not stops or any(la is None for _, la, _ in stops):
        return None
    new = PRide(ride_id, (row[0], row[1]), False, [(p, (a, b)) for p, a, b in stops])
    cands = c.execute("""
        SELECT d.user_id, ST_Y(d.location::geometry), ST_X(d.location::geometry)
        FROM drivers d
        JOIN users u ON u.id=d.user_id AND u.active
        JOIN vehicles v ON v.id=d.vehicle_id
        LEFT JOIN companies co ON co.id=d.company_id
        JOIN rides r ON r.id=%s
        WHERE d.status='busy' AND d.location IS NOT NULL
          AND r.vehicle_type='normal' AND v.vehicle_type='normal'
          AND (d.company_id IS NULL OR (r.allow_partner AND co.active))
          AND ST_DWithin(d.location, r.pickup, %s)
          AND NOT EXISTS (SELECT 1 FROM rides x WHERE x.driver_id=d.user_id
                          AND x.status IN ('accepted','in_progress') AND NOT x.shared)
          AND (SELECT COUNT(*) FROM rides x WHERE x.driver_id=d.user_id
               AND x.status IN ('accepted','in_progress')) < %s
          AND d.user_id NOT IN (SELECT driver_id FROM ride_offers WHERE ride_id=%s)""",
                       (ride_id, s["pool_radius_m"], int(s["seats"]), ride_id)).fetchall()
    best = None
    for did, la, lo in cands:
        rides = load_driver_rides(c, did)
        if not rides:
            continue
        ev = evaluate((la, lo), rides, new, s)
        if ev and (best is None or ev["detour_km"] < best["detour_km"]):
            best = {**ev, "driver_id": did}
    return best
