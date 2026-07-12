"""Simple username/password auth for the demo.

Login-or-signup: an unknown username creates an account; a known one must match.
Users live in a JSON file on the (ephemeral) writable store; the `admin` account
is always seeded. Sessions are in-memory tokens. This is intentionally minimal —
no email, no reset flow — enough to give each user their own company profile.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request

from quotepilot import config

ADMIN_USER = "admin"
ADMIN_PASSWORD = os.getenv("QP_ADMIN_PASSWORD", "88888888")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

_lock = threading.Lock()
_SESSIONS: dict[str, str] = {}  # token -> username


def _store_path() -> Path:
    raw = os.getenv("QP_USER_STORE")
    return Path(raw) if raw else config.DATA_DIR / "users.local.json"


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()


def _load_users() -> dict:
    path = _store_path()
    users = {}
    if path.exists():
        try:
            users = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            users = {}
    if ADMIN_USER not in users:  # always seed admin
        salt = secrets.token_hex(16)
        users[ADMIN_USER] = {"salt": salt, "hash": _hash(ADMIN_PASSWORD, salt),
                             "created_at": datetime.now(timezone.utc).isoformat()}
        _save_users(users)
    return users


def _save_users(users: dict) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def authenticate(username: str, password: str) -> str:
    """Login or auto-signup. Returns a session token. Raises 401/422 on bad input."""
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=422, detail="Username: 3–32 chars, letters/digits/._- only")
    if not password or len(password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    with _lock:
        users = _load_users()
        rec = users.get(username)
        if rec is None:  # new account
            salt = secrets.token_hex(16)
            users[username] = {"salt": salt, "hash": _hash(password, salt),
                               "created_at": datetime.now(timezone.utc).isoformat()}
            _save_users(users)
        else:  # existing -> verify
            if not hmac.compare_digest(_hash(password, rec["salt"]), rec["hash"]):
                raise HTTPException(status_code=401, detail="Wrong password for this username")
        token = secrets.token_urlsafe(24)
        _SESSIONS[token] = username
        return token


def user_for_token(token: str) -> str | None:
    with _lock:
        return _SESSIONS.get(token)


def logout(token: str) -> None:
    with _lock:
        _SESSIONS.pop(token, None)


def _token_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-qp-token", "").strip()


def current_user(request: Request) -> str:
    """FastAPI dependency: the logged-in username, or 401."""
    user = user_for_token(_token_from_request(request))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def optional_user(request: Request) -> str | None:
    return user_for_token(_token_from_request(request))
