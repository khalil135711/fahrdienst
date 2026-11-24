"""Adresssuche: Der Server fragt einen Nominatim-kompatiblen Dienst (OpenStreetMap) ab.

Wichtig: Der öffentliche Server nominatim.openstreetmap.org erlaubt höchstens 1 Anfrage pro Sekunde,
verlangt einen erkennbaren User-Agent und ist für den Dauerbetrieb einer Firma nicht gedacht.
Für den Echtbetrieb: eigenen Nominatim-Server oder einen kommerziellen Anbieter nutzen
(GEOCODER_URL setzen). Ergebnisse werden einen Tag zwischengespeichert."""
import collections
import os
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import current_user

GEOCODER_URL = os.environ.get("GEOCODER_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = os.environ.get("GEOCODER_USER_AGENT", "FahrdienstApp/1.0 (Kontakt: bitte-in-.env-eintragen)")
COUNTRY = os.environ.get("GEOCODER_COUNTRY", "de")
MIN_INTERVAL = float(os.environ.get("GEOCODER_MIN_INTERVAL", "1.1"))  # Sekunden zwischen Anfragen
PER_USER_PER_MIN = 20
CACHE_SECONDS = 86400

router = APIRouter()
_lock = threading.Lock()
_last = 0.0
_cache: dict[str, tuple[float, list]] = {}
_user_hits: dict[int, collections.deque] = {}


def _rate_limit(user_id: int):
    now = time.time()
    q = _user_hits.setdefault(user_id, collections.deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= PER_USER_PER_MIN:
        raise HTTPException(429, "Zu viele Suchanfragen. Bitte kurz warten.")
    q.append(now)


@router.get("/geo/search")
def search(q: str = Query(min_length=3, max_length=120), user: dict = Depends(current_user)):
    global _last
    _rate_limit(user["id"])
    key = q.strip().lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        with _lock:  # höchstens eine Anfrage pro MIN_INTERVAL an den Kartendienst
            wait = MIN_INTERVAL - (time.time() - _last)
            if wait > 0:
                time.sleep(wait)
            _last = time.time()
            r = httpx.get(GEOCODER_URL, timeout=8, headers={"User-Agent": USER_AGENT},
                          params={"q": q.strip(), "format": "jsonv2", "limit": 5,
                                  "countrycodes": COUNTRY, "accept-language": "de"})
        r.raise_for_status()
        data = r.json()
        results = []
        for it in data[:5]:
            lat, lng = float(it["lat"]), float(it["lon"])
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                results.append({"label": str(it.get("display_name", ""))[:200], "lat": lat, "lng": lng})
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Die Adresssuche ist gerade nicht verfügbar")
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), results)
    return results
