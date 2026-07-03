"""The wall between the OrphicOS thin client and its perception engine.

The client uses ONE third-party engine — windows-use — and only its *headless*
`Desktop` (UI-tree perception + action). It never uses windows-use's LLM `Agent`.

The problem this file solves: windows-use's top-level package eagerly imports that
`Agent`, and `Agent` pulls in `windows_use.providers`, which imports EVERY bundled
LLM/STT/TTS SDK (openai, anthropic, google, mistral, groq, ...). Merely importing
the Desktop would therefore load a dozen provider SDKs into the thin client — a
breach of the sacred wall (CLAUDE.md Rule 1: no LLM provider SDK in the client).

The fix: before windows-use is imported anywhere in the process, we pre-register a
tiny stub for `windows_use.agent.service` in `sys.modules`. windows-use's package
`__init__` then re-exports our no-op `Agent` instead of executing the real module,
so the providers package — and all provider SDKs — never load. Everything the
Desktop actually needs (the `uia` layer, the tree/desktop modules) imports normally.

This is the SINGLE choke point: every client module imports its engine symbols from
here, never from `windows_use` directly. `assert_wall_clean()` is the runtime proof.
"""
from __future__ import annotations

import os
import sys
import types

# Telemetry off before windows-use could ever construct its posthog client (Rule 4).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")

# Inject the Agent stub before the first windows-use import triggers its package
# __init__ (which would otherwise import the real Agent -> providers -> every SDK).
if "windows_use" not in sys.modules:
    _stub = types.ModuleType("windows_use.agent.service")
    _stub.Agent = None  # the OrphicOS client never runs windows-use's LLM Agent
    _stub.__doc__ = "OrphicOS wall stub: windows-use's LLM Agent is intentionally not loaded."
    sys.modules["windows_use.agent.service"] = _stub

# License wall (Rule 9): windows-use's Desktop imports `fuzzywuzzy.process` (GPLv2, and it
# drags in Levenshtein, GPL-2.0) solely for extractOne() in window-title matching. Neither
# GPL package may ship in the client, so we pre-register our own permissive replacement
# built on stdlib difflib. Same idea as WRatio for this use: pick the closest title, or
# None below the cutoff.
if "fuzzywuzzy" not in sys.modules:
    import difflib

    def _extract_one(query: str, choices, score_cutoff: int = 0, **_ignored):
        best, best_score = None, -1.0
        q = query.lower()
        for choice in choices:
            c = str(choice).lower()
            score = difflib.SequenceMatcher(None, q, c).ratio() * 100
            # A window title usually embeds the app name ("readme - Notepad"): treat a
            # whole-word containment as a strong match, like fuzzy partial matching does.
            if q and (q in c or c in q):
                score = max(score, 90.0)
            if score > best_score:
                best, best_score = choice, score
        if best is None or best_score < score_cutoff:
            return None
        return (best, int(best_score))

    _fw = types.ModuleType("fuzzywuzzy")
    _fw_process = types.ModuleType("fuzzywuzzy.process")
    _fw_process.extractOne = _extract_one
    _fw_process.__doc__ = "OrphicOS wall stub: permissive difflib-based match (no GPL fuzzywuzzy)."
    _fw.process = _fw_process
    sys.modules["fuzzywuzzy"] = _fw
    sys.modules["fuzzywuzzy.process"] = _fw_process

# Safe now: these load only the headless UIA perception/action code, no providers.
from windows_use import uia  # noqa: E402
from windows_use.agent.desktop.service import Desktop  # noqa: E402
from windows_use.agent.desktop.utils import escape_text_for_sendkeys  # noqa: E402

_FORBIDDEN = (
    "openai", "anthropic", "google.generativeai", "groq", "cohere", "mistralai",
    "cerebras", "litellm", "ollama", "langchain", "posthog",
    "Levenshtein",  # GPL-2.0; only fuzzywuzzy (also GPL, stubbed above) would pull it in
)


def assert_wall_clean() -> None:
    """Raise if any LLM provider SDK or telemetry client leaked into this process."""
    leaked = sorted(
        m for m in sys.modules
        if any(m == f or m.startswith(f + ".") for f in _FORBIDDEN)
    )
    if leaked:
        raise RuntimeError(
            "OrphicOS client wall breached — provider/telemetry modules loaded: "
            + ", ".join(leaked)
        )


__all__ = ["Desktop", "uia", "escape_text_for_sendkeys", "assert_wall_clean"]
