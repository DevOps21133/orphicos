"""OrphicOS per-user tokens + usage metering (subscription foundation).

Tokens authenticate the thin client to the brain. No LLM key or provider detail
lives here — that is brain.py only. Tokens persist in server/tokens.json
(gitignored); per-user call counts are kept in memory as a metering foundation
(not yet a billing system — counts reset on restart).

CLI:
    python -m server.auth issue <user_id>   # print a new token
    python -m server.auth list              # list users + token prefixes
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
from pathlib import Path

# Deployed (Docker) installs point this at a volume so tokens survive redeploys;
# dev keeps server/tokens.json next to this file.
_TOKENS_PATH = Path(os.environ.get("ORPHIC_TOKENS_PATH")
                    or Path(__file__).with_name("tokens.json"))
_lock = threading.Lock()
_usage: dict[str, int] = {}
_cache: dict = {"mtime": None, "data": {}}  # mtime-keyed cache; avoids a disk read per request


def _load() -> dict:
    try:
        mtime = _TOKENS_PATH.stat().st_mtime
    except OSError:
        _cache["mtime"], _cache["data"] = None, {}
        return _cache["data"]
    if _cache["mtime"] != mtime:
        try:
            _cache["data"] = json.loads(_TOKENS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _cache["data"] = {}
        _cache["mtime"] = mtime
    return _cache["data"]


def _save(data: dict) -> None:
    # Atomic write: never leave a torn tokens.json that would 401 every user.
    tmp = _TOKENS_PATH.with_name(_TOKENS_PATH.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_TOKENS_PATH)
    _cache["mtime"] = None  # force a reload on next _load


def issue_token(user_id: str) -> str:
    """Create, persist, and return a new per-user OrphicOS token."""
    token = "orphic_" + secrets.token_urlsafe(24)
    with _lock:
        data = _load()
        data[token] = {"user_id": user_id}
        _save(data)
    return token


def validate_token(token: str | None) -> str | None:
    """Return the user_id for a valid token, else None."""
    if not token:
        return None
    with _lock:
        entry = _load().get(token)
    return entry["user_id"] if entry else None


def record_call(user_id: str) -> int:
    """Increment and return the user's call count (metering foundation)."""
    with _lock:
        _usage[user_id] = _usage.get(user_id, 0) + 1
        return _usage[user_id]


def get_usage(user_id: str) -> int:
    with _lock:
        return _usage.get(user_id, 0)


def _cli(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "issue":
        print(issue_token(argv[1]))
        return 0
    if argv and argv[0] == "list":
        for tok, entry in _load().items():
            print(f"{entry['user_id']}\t{tok[:16]}...")
        return 0
    print("usage: python -m server.auth issue <user_id> | list", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
