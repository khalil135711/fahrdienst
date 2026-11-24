"""Musik im Fahrzeug: Admin lädt Titel in Bibliotheken hoch, Fahrer spielt sie ab.
Die Wiedergabe läuft über kurzlebige, titelbezogene Stream-Links (funktioniert auch im Browser)."""
import datetime as dt
import hashlib
import os
import re
import uuid

import jwt
import mutagen
import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .auth import ALGO, JWT_SECRET, require
from .db import db

MUSIC_DIR = os.environ.get("MUSIC_DIR", "/data/music")
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "30")) * 1024 * 1024
ALLOWED = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".wav": "audio/wav"}
STREAM_HOURS = 12
# Eigener Schlüssel: Ein Stream-Token kann nie als Anmelde-Token missbraucht werden
STREAM_SECRET = hashlib.sha256((JWT_SECRET + "|stream").encode()).hexdigest()

router = APIRouter()
admin = Depends(require("admin"))
staff = Depends(require("driver", "admin"))


def stream_url(track_id: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    t = jwt.encode({"sub": str(track_id), "typ": "stream",
                    "exp": now + dt.timedelta(hours=STREAM_HOURS)}, STREAM_SECRET, algorithm=ALGO)
    return f"/music/stream/{track_id}?t={t}"


class LibraryBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=300)


def _remove_file(filename: str):
    try:
        os.remove(os.path.join(MUSIC_DIR, filename))
    except OSError:
        pass


# ---------------------------------------------------------------- Admin
@router.get("/admin/music/libraries")
def admin_libraries(_: dict = admin):
    with db() as c:
        rows = c.execute("""SELECT l.id, l.name, l.description, COUNT(t.id), COALESCE(SUM(t.duration_s),0)
                            FROM music_libraries l LEFT JOIN music_tracks t ON t.library_id=l.id
                            GROUP BY l.id ORDER BY l.name""").fetchall()
    return [{"id": i, "name": n, "description": d, "tracks": c_, "duration_s": int(du)}
            for i, n, d, c_, du in rows]


@router.post("/admin/music/libraries")
def create_library(b: LibraryBody, _: dict = admin):
    try:
        with db() as c:
            lid = c.execute("INSERT INTO music_libraries (name, description) VALUES (%s,%s) RETURNING id",
                            (b.name.strip(), b.description.strip())).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Eine Bibliothek mit diesem Namen gibt es schon")
    return {"id": lid}


@router.delete("/admin/music/libraries/{library_id}")
def delete_library(library_id: int, _: dict = admin):
    """Löscht die Bibliothek samt aller Titel und Dateien."""
    with db() as c:
        files = [r[0] for r in c.execute("SELECT filename FROM music_tracks WHERE library_id=%s",
                                         (library_id,)).fetchall()]
        ok = c.execute("DELETE FROM music_libraries WHERE id=%s RETURNING 1", (library_id,)).fetchone()
    if not ok:
        raise HTTPException(404, "Bibliothek nicht gefunden")
    for f in files:
        _remove_file(f)
    return {"deleted_tracks": len(files)}


@router.get("/admin/music/tracks")
def admin_tracks(library_id: int | None = None, _: dict = admin):
    with db() as c:
        rows = c.execute("""SELECT t.id, t.title, t.artist, t.duration_s, t.size_bytes, t.license_note,
                                   t.library_id, l.name, t.created_at
                            FROM music_tracks t JOIN music_libraries l ON l.id=t.library_id
                            WHERE (%s::int IS NULL OR t.library_id=%s)
                            ORDER BY l.name, t.title LIMIT 500""", (library_id, library_id)).fetchall()
    return [{"id": i, "title": ti, "artist": ar, "duration_s": du, "size_bytes": sz,
             "license_note": ln, "library_id": li, "library": lname, "created_at": ca.isoformat(),
             "stream_url": stream_url(i)}
            for i, ti, ar, du, sz, ln, li, lname, ca in rows]


@router.post("/admin/music/tracks")
def upload_track(file: UploadFile = File(...), library_id: int = Form(...),
                 title: str = Form(""), artist: str = Form(""),
                 license_note: str = Form(..., min_length=3, max_length=300),
                 user: dict = admin):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Erlaubt sind nur MP3, M4A, OGG und WAV")
    with db() as c:
        if not c.execute("SELECT 1 FROM music_libraries WHERE id=%s", (library_id,)).fetchone():
            raise HTTPException(404, "Bibliothek nicht gefunden")
    os.makedirs(MUSIC_DIR, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(MUSIC_DIR, stored)
    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, f"Datei ist größer als {MAX_BYTES // (1024 * 1024)} MB")
                out.write(chunk)
        # Echte Prüfung: Nur wirklich lesbare Audiodateien werden akzeptiert
        try:
            meta = mutagen.File(path)
        except Exception:
            meta = None
        if meta is None or meta.info is None or not getattr(meta.info, "length", 0):
            raise HTTPException(400, "Das ist keine gültige Audiodatei")
        duration = int(meta.info.length)
        tags = mutagen.File(path, easy=True)
        tag = lambda k: (tags.get(k) or [""])[0] if tags is not None and tags.tags else ""
        final_title = (title.strip() or tag("title") or os.path.splitext(file.filename or "Titel")[0])[:150]
        final_artist = (artist.strip() or tag("artist"))[:150]
        with db() as c:
            tid = c.execute("""INSERT INTO music_tracks
                  (library_id,title,artist,filename,mime,duration_s,size_bytes,license_note,uploaded_by)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                            (library_id, final_title, final_artist, stored, ALLOWED[ext], duration,
                             size, license_note.strip(), user["id"])).fetchone()[0]
    except Exception:
        _remove_file(stored)
        raise
    return {"id": tid, "title": final_title, "duration_s": duration}


@router.delete("/admin/music/tracks/{track_id}")
def delete_track(track_id: int, _: dict = admin):
    with db() as c:
        row = c.execute("DELETE FROM music_tracks WHERE id=%s RETURNING filename", (track_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Titel nicht gefunden")
    _remove_file(row[0])
    return {"ok": True}


# ---------------------------------------------------------------- Fahrer (und Admin)
@router.get("/music/libraries")
def libraries(_: dict = staff):
    with db() as c:
        rows = c.execute("""SELECT l.id, l.name, l.description, COUNT(t.id)
                            FROM music_libraries l JOIN music_tracks t ON t.library_id=l.id
                            GROUP BY l.id ORDER BY l.name""").fetchall()
    return [{"id": i, "name": n, "description": d, "tracks": c_} for i, n, d, c_ in rows]


@router.get("/music/libraries/{library_id}/tracks")
def library_tracks(library_id: int, _: dict = staff):
    with db() as c:
        rows = c.execute("""SELECT id, title, artist, duration_s FROM music_tracks
                            WHERE library_id=%s ORDER BY title""", (library_id,)).fetchall()
    return [{"id": i, "title": t, "artist": a, "duration_s": d, "stream_url": stream_url(i)}
            for i, t, a, d in rows]


@router.get("/music/stream/{track_id}")
def stream(track_id: int, request: Request, t: str = ""):
    """Liefert die Audiodatei (mit Range-Unterstützung zum Vor- und Zurückspulen).
    Zugriff nur mit dem kurzlebigen Link, den der Server an Fahrer und Admin ausgibt."""
    try:
        data = jwt.decode(t, STREAM_SECRET, algorithms=[ALGO], options={"require": ["exp", "sub"]})
        if data.get("typ") != "stream" or int(data["sub"]) != track_id:
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Link abgelaufen oder ungültig")
    with db() as c:
        row = c.execute("SELECT filename, mime FROM music_tracks WHERE id=%s", (track_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Titel nicht gefunden")
    path = os.path.join(MUSIC_DIR, row[0])
    if not os.path.isfile(path):
        raise HTTPException(404, "Datei fehlt auf dem Server")
    size = os.path.getsize(path)
    start, end, status = 0, size - 1, 200
    rng = request.headers.get("range")
    if rng:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
        bad = HTTPException(416, "Ungültiger Bereich", headers={"Content-Range": f"bytes */{size}"})
        if not m or (m.group(1) == "" and m.group(2) == ""):
            raise bad
        s_, e_ = m.groups()
        if s_ == "":
            start = max(0, size - int(e_))
        else:
            start = int(s_)
            end = min(int(e_), size - 1) if e_ else size - 1
        if start > end or start >= size:
            raise bad
        status = 206
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1),
               "Cache-Control": "private, max-age=0"}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def chunks():
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                buf = f.read(min(65536, left))
                if not buf:
                    break
                left -= len(buf)
                yield buf

    return StreamingResponse(chunks(), status_code=status, media_type=row[1], headers=headers)
