"""Risk-verb approval gate for the OrphicOS shell (CLAUDE.md §9.4).

Some verbs are destructive or outward-facing: delete a file, send a message, submit
a form, make a purchase, uninstall an app, format a drive. Before the client executes
any action carrying one of these, a human must confirm it in the shell. This module is
PURE DETECTION — the shell wires the confirmation UI around it and the control loop
stays brain-less (Rule 1). It is deliberately conservative: a false positive only costs
one extra confirmation, while a missed risky action could be irreversible.
"""
from __future__ import annotations

import re

# The verbs called out in the spec (§9.4). Word-boundary matched so "remove" does not
# fire on "removable" and "format" does not fire on "information".
RISK_VERBS = ("delete", "remove", "send", "submit", "purchase", "uninstall", "format")
_RISK_RE = re.compile(r"\b(" + "|".join(RISK_VERBS) + r")\b", re.IGNORECASE)

# Some risk actions arrive as a key chord with NO spelled-out verb, so the word match
# above can't see them: the Del key deletes, Ctrl+Enter is the near-universal send/submit.
# (Chords that DO spell it out — "delete", "shift+delete" — are already caught above.)
# Only chords pressed as keys count; typing the letters "del" into a document is harmless,
# so this is checked for key-press actions only.
_KEY_ACTION_TYPES = frozenset({"press", "hotkey", "shortcut", "key", "keypress"})
_RISK_KEY_TOKENS = {"del": "delete"}          # any chord containing this key is risky
_RISK_KEY_CHORDS = {                          # exact-chord matches
    frozenset({"ctrl", "enter"}): "send",     # near-universal send/submit
    frozenset({"alt", "f4"}): "close",        # closes the active window (may lose work)
    frozenset({"win", "l"}): "lock",          # locks the session — kills the whole run
}


def command_has_risk(command: str) -> list[str]:
    """Risk verbs mentioned in the raw command text, for an up-front caution banner."""
    seen: dict[str, None] = {}
    for m in _RISK_RE.findall(command or ""):
        seen[m.lower()] = None
    return list(seen)


def action_needs_approval(action: dict) -> str | None:
    """The risk verb an action would carry out, or None if it is safe to auto-run.

    A verb can hide in the element an action targets (click "Delete"), the text it
    types, or the key chord it presses (the Delete key). The action *type* itself
    (click/type/press/…) is never a risk verb, so only the target and value are scanned.
    """
    haystack = " ".join(str(action.get(k) or "") for k in ("target_selector", "value"))
    m = _RISK_RE.search(haystack)
    if m:
        return m.group(1).lower()
    return _risky_key_chord(action)


def _risky_key_chord(action: dict) -> str | None:
    """The verb a risky key chord carries out (Del, Ctrl+Enter), or None — key actions only."""
    if str(action.get("type") or "").strip().lower() not in _KEY_ACTION_TYPES:
        return None
    keys = frozenset(k for k in re.split(r"[+\-\s]+", str(action.get("value") or "").lower()) if k)
    if not keys:
        return None
    for key, verb in _RISK_KEY_TOKENS.items():
        if key in keys:
            return verb
    return _RISK_KEY_CHORDS.get(keys)
