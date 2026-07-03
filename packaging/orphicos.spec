# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the OrphicOS thin client (the shell exe users install).

THE WALL, AT REST (CLAUDE.md Rules 1, 2, 9): client/_engine.py stops provider SDKs
from ever LOADING, but PyInstaller's static trace would still BUNDLE them (windows-use's
package __init__ imports its LLM Agent, which imports every provider SDK). The excludes
below keep every provider SDK, telemetry client, and GPL-flavored transitive dep OUT of
the shipped binary entirely. scripts/verify_dist.ps1 proves it after every build.

Build:  .venv\\Scripts\\python.exe -m PyInstaller packaging\\orphicos.spec --noconfirm
Output: dist\\OrphicOS\\OrphicOS.exe   (onedir; wrapped by packaging/installer.iss)
"""

_WALL_EXCLUDES = [
    # LLM / STT / TTS provider SDKs (Rule 1: none may ship in the client)
    "openai", "anthropic", "google.generativeai", "google.genai", "groq", "cohere",
    "mistralai", "cerebras", "litellm", "ollama", "together", "fireworks",
    "elevenlabs", "deepgram",
    # windows-use's provider/CLI layers (the client uses ONLY its headless Desktop)
    "windows_use.providers", "windows_use.cli",
    # windows-use's agent stack (client uses only the headless Desktop)
    "langchain", "langchain_core", "langchain_community", "langchain_openai",
    "langchain_anthropic", "langchain_google_genai", "langchain_groq",
    "langchain_ollama", "langchain_mistralai", "langchain_cerebras", "langgraph",
    "langsmith",
    # GPL deps (Rule 9): client/_engine.py replaces fuzzywuzzy with a difflib stub
    "fuzzywuzzy", "Levenshtein", "rapidfuzz",
    # telemetry (Rule 4) and misc heavy junk the client never uses
    "posthog", "tkinter", "matplotlib", "IPython", "pytest", "setuptools",
]

# No provider/GPL name may appear even as package METADATA in the shipped app (Rule 2):
# PyInstaller copies dist-info for traced distributions (e.g. elevenlabs, a TTS provider
# windows-use depends on but the client never loads). Drop those data entries outright.
_BANNED_DATA = ("elevenlabs", "fuzzywuzzy", "levenshtein", "rapidfuzz", "posthog",
                "openai", "anthropic", "groq", "cohere", "mistralai", "langchain")


def _data_ok(entry):
    dest = entry[0].replace("\\", "/").lower()
    return not any(b in dest for b in _BANNED_DATA)

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    datas=[("../client/shell/static", "client/shell/static")],
    hiddenimports=[],
    excludes=_WALL_EXCLUDES,
    noarchive=False,
)
a.datas = [d for d in a.datas if _data_ok(d)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OrphicOS",
    console=True,   # keeps startup/config errors visible; the product UI is the browser
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OrphicOS")
