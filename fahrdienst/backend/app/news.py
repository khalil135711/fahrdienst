"""Zeitungen für Kunden während der Fahrt.

Der Admin hinterlegt RSS/Atom-Feeds. Der Server holt nur Schlagzeilen (Titel, Link, Kurztext).
Den Artikel selbst öffnet die App auf der Webseite der Zeitung. Es werden keine Artikel kopiert.

Schutz: Nur https, keine internen Adressen (SSRF), Größen- und Zeitlimit, XML ohne DTD (XXE)."""
import email.utils
import html
import ipaddress
import os
import re
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
import psycopg
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import current_user, require
from .db import db

router = APIRouter()
admin = Depends(require("admin"))
CACHE_SECONDS = 300
MAX_BYTES = 2_000_000
_cache: dict[int, tuple[float, list]] = {}


def _allow_private() -> bool:
    # Nur für Entwicklung/Tests (lokaler Test-Feed). In Produktion NICHT setzen.
    return os.environ.get("NEWS_ALLOW_PRIVATE") == "1"


def validate_feed_url(url: str) -> None:
    """Wirft ValueError, wenn die Adresse unsicher oder nicht erlaubt ist."""
    p = urlparse(url)
    allowed = ("https", "http") if _allow_private() else ("https",)
    if p.scheme not in allowed or not p.hostname:
        raise ValueError("Die Feed-Adresse muss mit https:// beginnen")
    if p.username or p.password:
        raise ValueError("Adressen mit Benutzername/Passwort sind nicht erlaubt")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Die Adresse wurde nicht gefunden")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global and not _allow_private():
            raise ValueError("Interne Adressen sind nicht erlaubt")


def fetch_feed(url: str) -> bytes:
    for _ in range(4):  # Weiterleitungen werden einzeln geprüft
        validate_feed_url(url)
        with httpx.Client(timeout=8, follow_redirects=False,
                          headers={"User-Agent": "FahrdienstNews/1.0"}) as c:
            with c.stream("GET", url) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                if r.status_code != 200:
                    raise ValueError(f"Der Feed antwortet mit Status {r.status_code}")
                data = b""
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise ValueError("Der Feed ist zu groß")
                return data
    raise ValueError("Zu viele Weiterleitungen")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(text: str | None, n: int) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def parse_feed(data: bytes) -> list[dict]:
    try:
        root = ET.fromstring(data, forbid_dtd=True)
    except (DefusedXmlException, ET.ParseError, ValueError):
        raise ValueError("Der Feed ist ungültig oder enthält nicht erlaubte Inhalte")
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        f = {"title": "", "link": "", "published": None, "summary": ""}
        for ch in node:
            k = _local(ch.tag)
            if k == "title":
                f["title"] = _clean(ch.text, 200)
            elif k == "link":
                f["link"] = (ch.get("href") or ch.text or "").strip()
            elif k in ("pubDate", "published", "updated") and not f["published"]:
                raw = (ch.text or "").strip()
                try:
                    f["published"] = email.utils.parsedate_to_datetime(raw).isoformat()
                except (TypeError, ValueError):
                    f["published"] = raw or None
            elif k in ("description", "summary") and not f["summary"]:
                f["summary"] = _clean(ch.text, 220)
        if f["title"] and urlparse(f["link"]).scheme in ("http", "https"):  # keine javascript:-Links
            items.append(f)
        if len(items) >= 30:
            break
    return items


def items_for(source_id: int, url: str) -> list[dict]:
    hit = _cache.get(source_id)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    items = parse_feed(fetch_feed(url))
    _cache[source_id] = (time.time(), items)
    return items


# ---------------------------------------------------------------- Admin
class SourceBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    feed_url: str = Field(min_length=8, max_length=500)


class ActiveBody(BaseModel):
    active: bool


@router.get("/admin/news")
def admin_sources(_: dict = admin):
    with db() as c:
        rows = c.execute("SELECT id, name, feed_url, active FROM news_sources ORDER BY name").fetchall()
    return [{"id": i, "name": n, "feed_url": u, "active": a} for i, n, u, a in rows]


@router.post("/admin/news")
def add_source(b: SourceBody, _: dict = admin):
    url = b.feed_url.strip()
    try:
        validate_feed_url(url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        with db() as c:
            sid = c.execute("INSERT INTO news_sources (name, feed_url) VALUES (%s,%s) RETURNING id",
                            (b.name.strip(), url)).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Dieser Feed ist schon eingetragen")
    return {"id": sid}


@router.patch("/admin/news/{source_id}")
def set_source_active(source_id: int, b: ActiveBody, _: dict = admin):
    with db() as c:
        ok = c.execute("UPDATE news_sources SET active=%s WHERE id=%s RETURNING 1",
                       (b.active, source_id)).fetchone()
    if not ok:
        raise HTTPException(404, "Zeitung nicht gefunden")
    return {"ok": True}


@router.delete("/admin/news/{source_id}")
def delete_source(source_id: int, _: dict = admin):
    with db() as c:
        ok = c.execute("DELETE FROM news_sources WHERE id=%s RETURNING 1", (source_id,)).fetchone()
    if not ok:
        raise HTTPException(404, "Zeitung nicht gefunden")
    _cache.pop(source_id, None)
    return {"ok": True}


# ---------------------------------------------------------------- Kunde (nur während der Fahrt)
def news_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] == "admin":
        return user
    if user["role"] == "customer":
        with db() as c:
            ride = c.execute("""SELECT 1 FROM rides WHERE customer_id=%s
                                AND status IN ('accepted','in_progress') LIMIT 1""",
                             (user["id"],)).fetchone()
        if ride:
            return user
        raise HTTPException(403, "Zeitungen sind nur während einer Fahrt verfügbar")
    raise HTTPException(403, "Keine Berechtigung")


@router.get("/news/sources")
def sources(_: dict = Depends(news_user)):
    with db() as c:
        rows = c.execute("SELECT id, name FROM news_sources WHERE active ORDER BY name").fetchall()
    return [{"id": i, "name": n} for i, n in rows]


@router.get("/news/sources/{source_id}/items")
def source_items(source_id: int, _: dict = Depends(news_user)):
    with db() as c:
        row = c.execute("SELECT feed_url FROM news_sources WHERE id=%s AND active", (source_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Zeitung nicht gefunden")
    try:
        return items_for(source_id, row[0])
    except ValueError as e:
        raise HTTPException(502, str(e))
    except httpx.HTTPError:
        raise HTTPException(502, "Die Zeitung ist gerade nicht erreichbar")
