"""Read the live Windows screen, tree-first (CLAUDE.md Rule 5).

Primary perception is the Windows UI Automation tree via windows-use's headless
`Desktop` (no LLM, no Agent). A screenshot is captured ONLY when the tree yields no
interactive elements (canvas / DirectX / custom-drawn apps) — the vision fallback.

The Perceiver holds the shared `Desktop` so the Actor can resolve element ids to
live coordinates from the SAME snapshot this Perceiver produced.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

from client._engine import Desktop


@dataclass
class Perception:
    ui_tree: str   # compact table sent to the brain (id|window|control_type|name|coords|meta)
    is_empty: bool  # True when no interactive elements were found -> trigger vision fallback


class Perceiver:
    def __init__(self, desktop: Desktop) -> None:
        self._desktop = desktop

    def perceive(self) -> Perception:
        """Capture and serialize the current UI tree for the brain."""
        state = self._desktop.get_state()
        tree = state.tree_state
        nodes = tree.interactive_nodes or []
        active = state.active_window.name if state.active_window else "(no active window)"
        ui_tree = f"ACTIVE WINDOW: {active}\n{tree.interactive_elements_to_string()}"
        return Perception(ui_tree=ui_tree, is_empty=(not tree.status) or (not nodes))

    def capture_screenshot(self) -> str:
        """Base64 PNG of the screen — sent only on the tree-insufficient fallback (Rule 5)."""
        png = self._desktop.get_screenshot(as_bytes=True)
        return base64.b64encode(png).decode("ascii")
