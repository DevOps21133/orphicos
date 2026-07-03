"""OrphicOS user accounts — email + password sign-in over the token store.

Onboarding is "install → sign in → speak" (CLAUDE.md Phase 6.2): register/login
here yields the same per-user OrphicOS token that auth.py already validates on
/command, so nothing downstream changes. Passwords are hashed with stdlib
PBKDF2-HMAC-SHA256 (600k iterations, per-user random salt) — no new dependencies.
Users persist in users.json (gitignored) next to tokens.json, or at
ORPHIC_USERS_PATH (Docker volume). Passwords and tokens are NEVER logged.

Login rate-limiting is an in-memory per-email failure counter with a lockout
window — sufficient for the single-worker deployment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from server import auth

_USERS_PATH = Path(os.environ.get("ORPHIC_USERS_PATH")
                   or Path(__file__).with_name("users.json"))
_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": {}}

PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
MIN_PASSWORD_LEN = 8

# Login lockout: after MAX_FAILS consecutive failures for an email, refuse
# further attempts until LOCKOUT_SECONDS have passed. In-memory (1 worker).
MAX_FAILS = 5
LOCKOUT_SECONDS = 300
_fails: dict[str, dict] = {}  # email -> {"count": int, "locked_until": float}


class AccountError(Exception):
    """Base for account failures; message is safe to show the user."""


class EmailTaken(AccountError):
    pass


class InvalidCredentials(AccountError):
    pass


class LockedOut(AccountError):
    pass


def _load() -> dict:
    try:
        mtime = _USERS_PATH.stat().st_mtime
    except OSError:
        _cache["mtime"], _cache["data"] = None, {}
        return _cache["data"]
    if _cache["mtime"] != mtime:
        try:
            _cache["data"] = json.loads(_USERS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _cache["data"] = {}
        _cache["mtime"] = mtime
    return _cache["data"]


def _save(data: dict) -> None:
    # Atomic write, same pattern as auth._save: never leave a torn users.json.
    tmp = _USERS_PATH.with_name(_USERS_PATH.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_USERS_PATH)
    _cache["mtime"] = None


def _hash_password(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_new_credentials(email: str, password: str) -> str | None:
    """Return an error message for malformed inputs, else None."""
    e = normalize_email(email)
    if "@" not in e[1:-1] or " " in e or len(e) > 254:
        return "Enter a valid email address."
    if len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    return None


def register(email: str, password: str) -> str:
    """Create an account and return its OrphicOS token. Raises EmailTaken."""
    email = normalize_email(email)
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _hash_password(password, salt)  # hash outside the lock (slow by design)
    with _lock:
        users = _load()
        if email in users:
            raise EmailTaken("An account with this email already exists.")
        token = auth.issue_token(email)
        users[email] = {
            "password": {
                "algorithm": "pbkdf2_sha256",
                "iterations": PBKDF2_ITERATIONS,
                "salt": salt.hex(),
                "hash": digest,
            },
            "token": token,
            "created_at": time.time(),
        }
        _save(users)
    return token


def login(email: str, password: str) -> str:
    """Verify credentials and return the account's token.

    Raises LockedOut after MAX_FAILS consecutive failures (per email) until the
    lockout window passes, InvalidCredentials otherwise. Unknown emails burn the
    same PBKDF2 cost as real ones so timing does not reveal which emails exist.
    """
    email = normalize_email(email)
    now = time.time()
    with _lock:
        state = _fails.get(email)
        if state and now < state["locked_until"]:
            raise LockedOut("Too many failed attempts. Try again later.")
        user = _load().get(email)

    if user:
        pw = user["password"]
        digest = _hash_password(password, bytes.fromhex(pw["salt"]), pw["iterations"])
        ok = hmac.compare_digest(digest, pw["hash"])
    else:
        _hash_password(password, b"orphicos-dummy-salt")  # equalize timing
        ok = False

    with _lock:
        if not ok:
            state = _fails.setdefault(email, {"count": 0, "locked_until": 0.0})
            state["count"] += 1
            if state["count"] >= MAX_FAILS:
                state["locked_until"] = now + LOCKOUT_SECONDS
                state["count"] = 0
            raise InvalidCredentials("Invalid email or password.")
        _fails.pop(email, None)
    return user["token"]
