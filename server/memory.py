"""OrphicOS memory — per-user facts the user CHOSE to have OrphicOS remember.

This is what turns OrphicOS from obedient (needs exact steps every time) into
intelligent (needs a destination). It is NOT the transient screen data: the UI tree
and any screenshot are used for one decision and dropped (CLAUDE.md Rule 4). Memory
items are the opposite — a small, structured, human-readable set of opt-in facts the
user can see, edit, and wipe at any time (the View + Wipe controls in the shell).

Buckets (Stage 1 ships people + preferences; vocabulary shares the same store):
  - people        names -> emails / relationships          ("my accountant" -> Sarah Chen <sarah@firm.com>)
  - preferences   sign-offs, default folders, tone, formats ("email sign-off" -> "Best, Alex")
  - vocabulary    the user's shorthand -> real target/path  ("the deck" -> Q3-pitch.pptx)

Each item: {id, bucket, key, value, source, created_at, last_used}. Storage mirrors
auth.py / entitlements.py: one JSON file, keyed by user_id, at server/memory.json
(gitignored) or ORPHIC_MEMORY_PATH (Docker volume) so it survives redeploys. Memory
lives ONLY on the server, per user account — it cannot be scraped from the thin
client, works across the user's devices, and stays user-owned (Rule 1, the split).

Inspect / clear from the shell UI, or manually:
    python -m server.memory list [user_id]
    python -m server.memory forget <user_id>
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

# The buckets Stage 1 recognises. Kept here as the single source of truth so the
# brain (which validates a model's "remember" output) and the API agree.
BUCKETS = ("people", "preferences", "vocabulary")

# Guardrails: memory is meant to be a SMALL, readable set of facts, not a data lake.
# Caps keep the prompt cheap (every item rides in every decision) and bound abuse.
MAX_ITEMS_PER_USER = 200
MAX_KEY_LEN = 200
MAX_VALUE_LEN = 1000

_MEMORY_PATH = Path(os.environ.get("ORPHIC_MEMORY_PATH")
                    or Path(__file__).with_name("memory.json"))
_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": {}}  # mtime-keyed cache; avoids a disk read per request


def _load() -> dict:
    try:
        mtime = _MEMORY_PATH.stat().st_mtime
    except OSError:
        _cache["mtime"], _cache["data"] = None, {}
        return _cache["data"]
    if _cache["mtime"] != mtime:
        try:
            _cache["data"] = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _cache["data"] = {}
        _cache["mtime"] = mtime
    return _cache["data"]


def _save(data: dict) -> None:
    # Atomic write: a torn memory.json would corrupt every user's memory at once.
    tmp = _MEMORY_PATH.with_name(_MEMORY_PATH.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_MEMORY_PATH)
    _cache["mtime"] = None  # force a reload on next _load


def _clean(text: str, limit: int) -> str:
    # One-line, trimmed, length-capped — memory items are short facts, never blobs.
    return " ".join(str(text).split())[:limit].strip()


def list_items(user_id: str) -> list[dict]:
    """Every memory item for this user, oldest first. Unknown user -> []."""
    with _lock:
        items = _load().get(user_id) or []
        return [dict(it) for it in items]  # copies: callers must not mutate the cache


def add(user_id: str, bucket: str, key: str, value: str, source: str = "explicit") -> dict | None:
    """Remember a fact. Same (bucket, key) UPDATES in place (no duplicates); a new
    key appends. Returns the stored item, or None if bucket/key/value was invalid or
    the per-user cap is reached. Never raises on bad input — a bad "remember" from the
    model must not 500 a command."""
    bucket = str(bucket).strip().lower()
    key = _clean(key, MAX_KEY_LEN)
    value = _clean(value, MAX_VALUE_LEN)
    if bucket not in BUCKETS or not key or not value:
        return None
    now = time.time()
    with _lock:
        data = _load()
        items = data.setdefault(user_id, [])
        for it in items:  # dedup on (bucket, case-insensitive key): correct a fact, don't pile up
            if it.get("bucket") == bucket and it.get("key", "").lower() == key.lower():
                it["value"], it["source"], it["last_used"] = value, source, now
                _save(data)
                return dict(it)
        if len(items) >= MAX_ITEMS_PER_USER:
            return None
        item = {"id": uuid.uuid4().hex[:12], "bucket": bucket, "key": key, "value": value,
                "source": source, "created_at": now, "last_used": now}
        items.append(item)
        _save(data)
        return dict(item)


def update(user_id: str, item_id: str, value: str) -> bool:
    """Correct one item's value (the shell's inline edit). True if it existed."""
    value = _clean(value, MAX_VALUE_LEN)
    if not value:
        return False
    with _lock:
        data = _load()
        for it in data.get(user_id) or []:
            if it.get("id") == item_id:
                it["value"], it["last_used"] = value, time.time()
                _save(data)
                return True
    return False


def delete(user_id: str, item_id: str) -> bool:
    """Forget one item (the shell's ✕). True if something was removed."""
    with _lock:
        data = _load()
        items = data.get(user_id) or []
        kept = [it for it in items if it.get("id") != item_id]
        if len(kept) == len(items):
            return False
        data[user_id] = kept
        _save(data)
        return True


def wipe(user_id: str) -> int:
    """Forget EVERYTHING for this user ('Forget everything'). Returns count removed."""
    with _lock:
        data = _load()
        removed = len(data.get(user_id) or [])
        if user_id in data:
            del data[user_id]
            _save(data)
        return removed


def _cli(argv: list[str]) -> int:
    if argv and argv[0] == "list":
        data = _load()
        users = [argv[1]] if len(argv) > 1 else sorted(data)
        for uid in users:
            print(f"# {uid}")
            for it in list_items(uid):
                print(f"  [{it['bucket']}] {it['key']} = {it['value']}  ({it['source']})")
        return 0
    if len(argv) >= 2 and argv[0] == "forget":
        print(f"forgot {wipe(argv[1])} item(s) for {argv[1]}")
        return 0
    print("usage: python -m server.memory list [user_id] | forget <user_id>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
