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

# Safe now: these load only the headless UIA perception/action code, no providers.
from windows_use import uia  # noqa: E402
from windows_use.agent.desktop.service import Desktop  # noqa: E402
from windows_use.agent.desktop.utils import escape_text_for_sendkeys  # noqa: E402

_FORBIDDEN = (
    "openai", "anthropic", "google.generativeai", "groq", "cohere", "mistralai",
    "cerebras", "litellm", "ollama", "langchain", "posthog",
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
