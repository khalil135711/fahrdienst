"""Anmeldung: Passwort-Hashing (bcrypt), JWT-Token, Rollenprüfung."""
import datetime as dt
import os

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import db

JWT_SECRET = os.environ.get("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET fehlt oder ist zu kurz (mindestens 32 Zeichen). "
        "Erzeugen mit: openssl rand -hex 32")
ALGO = "HS256"
TOKEN_HOURS = int(os.environ.get("TOKEN_HOURS", "12"))
MAX_FAILED = 5          # Fehlversuche bis zur Sperre
LOCK_MINUTES = 15       # Dauer der Sperre

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


# Gleicht die Antwortzeit aus, wenn die E-Mail nicht existiert (verhindert Nutzer-Erkennung)
DUMMY_HASH = hash_password("dummy-password-for-timing")


def create_token(user_id: int, role: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now,
               "exp": now + dt.timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Prüft das Token und lädt den Benutzer frisch aus der Datenbank.
    Rolle und Sperre kommen aus der DB, nicht aus dem Token: Eine Sperrung wirkt sofort."""
    unauthorized = {"WWW-Authenticate": "Bearer"}
    if creds is None:
        raise HTTPException(401, "Nicht angemeldet", headers=unauthorized)
    try:
        data = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGO],
                          options={"require": ["exp", "sub"]})
        user_id = int(data["sub"])
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Sitzung abgelaufen oder ungültig", headers=unauthorized)
    with db() as c:
        row = c.execute("SELECT id, name, role, active FROM users WHERE id=%s",
                        (user_id,)).fetchone()
    if not row or not row[3]:
        raise HTTPException(401, "Konto nicht mehr gültig", headers=unauthorized)
    return {"id": row[0], "name": row[1], "role": row[2]}


def require(*roles: str):
    """Abhängigkeit für Endpunkte: nur die genannten Rollen dürfen zugreifen."""
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Keine Berechtigung")
        return user
    return dep
