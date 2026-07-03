"""Wall-at-rest check for the frozen OrphicOS client (CLAUDE.md Rules 1, 2, 9).

Scans dist/OrphicOS for any trace of an LLM provider SDK, telemetry client, or
windows-use agent-stack dependency — in bundled files AND inside the PYZ module
archive. Exits non-zero (and names the leaks) if anything forbidden shipped.

Build-time tool only: never bundled, never shipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

FORBIDDEN = (
    "openai", "anthropic", "google.generativeai", "google.genai", "groq", "cohere",
    "mistralai", "cerebras", "litellm", "ollama", "langchain", "langgraph",
    "langsmith", "posthog",
    "elevenlabs",                             # provider name may not ship, even as metadata
    "fuzzywuzzy", "levenshtein", "rapidfuzz", # GPL pair + their backend (stubbed in _engine)
)


def _is_forbidden(name: str) -> bool:
    n = name.replace("\\", "/").replace("/", ".").replace("-", "_").lower()
    return any(n == f or n.startswith(f + ".") or ("." + f + ".") in ("." + n + ".")
               for f in (x.replace("-", "_") for x in FORBIDDEN))


def main(dist: str = "dist/OrphicOS") -> int:
    root = Path(dist)
    exe = root / "OrphicOS.exe"
    if not exe.exists():
        print(f"FAIL: {exe} not found — build first.")
        return 2

    leaks: list[str] = []

    # 1) Bundled files/dirs under _internal (compiled extensions, package data).
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if any(_is_forbidden(part) for part in rel.split("/")):
            leaks.append(f"file: {rel}")

    # 2) Pure-Python modules inside the PYZ, which PyInstaller 6 embeds in the exe itself.
    carchive = CArchiveReader(str(exe))
    pyz_names = [n for n in carchive.toc if n.lower().endswith(".pyz")]
    if not pyz_names:
        print("FAIL: no embedded PYZ found in the exe — cannot verify pure modules.")
        return 2
    for name in pyz_names:
        pyz = carchive.open_embedded_archive(name)
        for mod in pyz.toc:
            if _is_forbidden(mod):
                leaks.append(f"pyz module: {mod}")

    if leaks:
        print("FAIL — the shipped client contains forbidden provider/telemetry/GPL-stack code:")
        for l in sorted(set(leaks)):
            print("  " + l)
        return 1
    print("PASS — wall clean at rest: no provider SDK, telemetry, or agent-stack module in dist/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
