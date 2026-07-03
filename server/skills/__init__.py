"""OrphicOS skill registry — the paid expertise packs (Skill Store, money layer).

A skill is server-side PROMPT CONTENT, never client code: its "expertise" text is
injected into the brain's system prompt only for users whose entitlement says they
bought it (server/entitlements.py is the source of truth). Locked users' brains
never receive the recipes, so there is nothing in the shipped client to crack.

Each pack lives in its own module (one git branch per skill deepens one module):
    SKILL = {
      "id":            registry key, also the entitlement name,
      "title":         user-facing name (upsell copy),
      "tagline":       one-line pitch (store copy),
      "checkout_path": path under the store base URL for the locked-skill deep link,
      "classify":      one line the brain uses to TAG commands that need this skill,
      "expertise":     prompt rules injected ONLY when the user unlocked the skill.
    }
"""
from __future__ import annotations

from server.skills import excel, gmail

_REQUIRED_KEYS = ("id", "title", "tagline", "checkout_path", "classify", "expertise")

ALL: dict[str, dict] = {}
for _mod in (gmail, excel):
    _pack = _mod.SKILL
    for _key in _REQUIRED_KEYS:
        if not _pack.get(_key):
            raise RuntimeError(f"skill pack {_mod.__name__} is missing '{_key}'")
    ALL[_pack["id"]] = _pack


def get(skill_id: str) -> dict | None:
    return ALL.get(skill_id)


def ids() -> frozenset[str]:
    return frozenset(ALL)
