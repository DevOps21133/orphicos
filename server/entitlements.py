"""OrphicOS entitlements — per-user record of unlocked paid skills (source of truth).

The gate lives HERE, on the server, never in the client: /command checks this
store before any skill expertise enters the brain's prompt and before a tagged
skill decision is allowed through. Entitlements persist in
server/entitlements.json (gitignored), or at ORPHIC_ENTITLEMENTS_PATH (Docker
volume) — same storage pattern as auth.py's token store.

Until checkout is wired to a payment provider, grants are issued manually:
    python -m server.entitlements grant <user_id> <skill_id>
    python -m server.entitlements revoke <user_id> <skill_id>
    python -m server.entitlements list [user_id]
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from server import skills

_ENTITLEMENTS_PATH = Path(os.environ.get("ORPHIC_ENTITLEMENTS_PATH")
                          or Path(__file__).with_name("entitlements.json"))
_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": {}}  # mtime-keyed cache; avoids a disk read per request


def _load() -> dict:
    try:
        mtime = _ENTITLEMENTS_PATH.stat().st_mtime
    except OSError:
        _cache["mtime"], _cache["data"] = None, {}
        return _cache["data"]
    if _cache["mtime"] != mtime:
        try:
            _cache["data"] = json.loads(_ENTITLEMENTS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _cache["data"] = {}
        _cache["mtime"] = mtime
    return _cache["data"]


def _save(data: dict) -> None:
    # Atomic write: a torn entitlements.json would lock every paying user out.
    tmp = _ENTITLEMENTS_PATH.with_name(_ENTITLEMENTS_PATH.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_ENTITLEMENTS_PATH)
    _cache["mtime"] = None  # force a reload on next _load


def unlocked(user_id: str) -> frozenset[str]:
    """The set of skill ids this user has bought. Unknown user -> empty set."""
    with _lock:
        entry = _load().get(user_id) or {}
    return frozenset(entry.get("skills") or [])


def grant(user_id: str, skill_id: str) -> None:
    """Unlock a skill for a user. Raises ValueError for a skill not in the registry."""
    if skill_id not in skills.ALL:
        raise ValueError(f"unknown skill: {skill_id!r} (known: {', '.join(sorted(skills.ALL))})")
    with _lock:
        data = _load()
        entry = data.setdefault(user_id, {"skills": []})
        if skill_id not in entry["skills"]:
            entry["skills"].append(skill_id)
            entry[f"granted_{skill_id}_at"] = time.time()
            _save(data)


def revoke(user_id: str, skill_id: str) -> None:
    with _lock:
        data = _load()
        entry = data.get(user_id)
        if entry and skill_id in entry.get("skills", []):
            entry["skills"].remove(skill_id)
            _save(data)


def _cli(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] in ("grant", "revoke"):
        try:
            (grant if argv[0] == "grant" else revoke)(argv[1], argv[2])
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{argv[0]} {argv[2]} -> {argv[1]}: now unlocked={sorted(unlocked(argv[1]))}")
        return 0
    if argv and argv[0] == "list":
        data = _load()
        users = [argv[1]] if len(argv) > 1 else sorted(data)
        for uid in users:
            print(f"{uid}\t{','.join(sorted(unlocked(uid))) or '-'}")
        return 0
    print("usage: python -m server.entitlements grant|revoke <user_id> <skill_id> | list [user_id]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
