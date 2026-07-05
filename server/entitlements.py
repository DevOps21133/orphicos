"""OrphicOS entitlements — per-user record of unlocked paid skills + features (source of truth).

The gate lives HERE, on the server, never in the client: /command checks this
store before any skill expertise enters the brain's prompt and before a tagged
skill decision is allowed through. Entitlements persist in
server/entitlements.json (gitignored), or at ORPHIC_ENTITLEMENTS_PATH (Docker
volume) — same storage pattern as auth.py's token store.

Two kinds of entitlement are tracked, because they have DIFFERENT threat models:

  * SKILLS (gmail, excel, …) — server-side PROMPT CONTENT. Locked users' brains
    never receive the recipes, so there is nothing in the shipped client to crack.
    This is the crack-proof gate; the source of OrphicOS's monetization integrity.

  * FEATURES (orphic_page_agent, …) — client-side CAPABILITIES the user can run
    on their own machine (often on their own provider key). The server can only
    gate VISIBILITY/UX for these, never cryptographic access: everything needed
    to run them ships in the client, so a determined user with devtools could
    bypass the check. We gate the UX honestly and record the caveat in CLAUDE.md
    ("Accepted debt — Orphic Page Agent vs Rule 1"). Do NOT add a feature here
    expecting strong enforcement — that requires moving the secret server-side
    (which is what skills are for).

Until checkout is wired to a payment provider, grants are issued manually:
    python -m server.entitlements grant <user_id> <skill_id>
    python -m server.entitlements revoke <user_id> <skill_id>
    python -m server.entitlements grant-feature <user_id> <feature_id>
    python -m server.entitlements revoke-feature <user_id> <feature_id>
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

# ---- feature registry --------------------------------------------------------
# Known client-side features that can be entitlement-gated. Each carries the same
# metadata shape as a skill pack (title/tagline/checkout_path) so the shell can
# render one consistent upsell for both locked skills and locked features.
# Add a feature here in the same commit that ships the client capability.
FEATURES: dict[str, dict] = {
    "orphic_page_agent": {
        "id": "orphic_page_agent",
        "title": "Orphic Page Agent",
        "tagline": "Voice-driven web navigation, right in the page.",
        # Base Premium plan feature: included for every paid subscriber. The
        # checkout path points at the plans page (this is a plan-level perk, not
        # an individual skill purchase).
        "checkout_path": "/plans",
        "plan": "base-premium",
    },
}


def _known_features() -> frozenset[str]:
    return frozenset(FEATURES)


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


# ---- feature entitlements (UX-gated client capabilities) ----------------------
# Read the module docstring's threat-model note before adding a feature here:
# features gate VISIBILITY only, never access. Never rely on a feature check for
# anything that needs strong enforcement (use a skill instead).

def features(user_id: str) -> frozenset[str]:
    """The set of client-side feature ids unlocked for this user. Unknown -> empty."""
    with _lock:
        entry = _load().get(user_id) or {}
    return frozenset(entry.get("features") or [])


def has_feature(user_id: str, feature_id: str) -> bool:
    """True iff `feature_id` is unlocked for `user_id`."""
    return feature_id in features(user_id)


def grant_feature(user_id: str, feature_id: str) -> None:
    """Unlock a client-side feature for a user. Raises ValueError if unknown."""
    if feature_id not in FEATURES:
        raise ValueError(f"unknown feature: {feature_id!r} "
                         f"(known: {', '.join(sorted(FEATURES))})")
    with _lock:
        data = _load()
        entry = data.setdefault(user_id, {"skills": [], "features": []})
        feats = entry.setdefault("features", [])
        if feature_id not in feats:
            feats.append(feature_id)
            entry[f"granted_feature_{feature_id}_at"] = time.time()
            _save(data)


def revoke_feature(user_id: str, feature_id: str) -> None:
    with _lock:
        data = _load()
        entry = data.get(user_id)
        if entry and feature_id in entry.get("features", []):
            entry["features"].remove(feature_id)
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
    if len(argv) >= 3 and argv[0] in ("grant-feature", "revoke-feature"):
        try:
            (grant_feature if argv[0] == "grant-feature" else revoke_feature)(argv[1], argv[2])
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{argv[0]} {argv[2]} -> {argv[1]}: "
              f"features={sorted(features(argv[1])) or '-'}")
        return 0
    if argv and argv[0] == "list":
        data = _load()
        users = [argv[1]] if len(argv) > 1 else sorted(data)
        for uid in users:
            print(f"{uid}\tskills={','.join(sorted(unlocked(uid))) or '-'}\t"
                  f"features={','.join(sorted(features(uid))) or '-'}")
        return 0
    print("usage: python -m server.entitlements grant|revoke <user_id> <skill_id> "
          "| grant-feature|revoke-feature <user_id> <feature_id> | list [user_id]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
