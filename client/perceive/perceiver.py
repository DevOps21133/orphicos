"""Read the live Windows screen, tree-first (CLAUDE.md Rule 5).

Primary perception is the Windows UI Automation tree via windows-use's headless
`Desktop` (no LLM, no Agent). A screenshot is captured ONLY when the tree yields no
interactive elements (canvas / DirectX / custom-drawn apps) — the vision fallback.

The Perceiver holds the shared `Desktop` so the Actor can resolve element ids to
live coordinates from the SAME snapshot this Perceiver produced.

Serialization is deliberately compact: every byte of the tree becomes LLM input
tokens on the server, so noise rows and redundant columns are trimmed here. The
element ids in the serialized tree are the ORIGINAL indices into the snapshot's
interactive_nodes list — trimming never renumbers, so the Actor's id resolution
(`client/act`) stays in sync with what the brain saw.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

from client._engine import Desktop

# Payload guard: real app trees are usually < 300 interactive elements; anything
# beyond this is browser/ribbon noise that only inflates tokens and latency.
MAX_TREE_ELEMENTS = 300


@dataclass
class Perception:
    ui_tree: str   # compact table sent to the brain (id|type|name|meta)
    is_empty: bool  # True when no interactive elements were found -> trigger vision fallback


def _clean(text: str) -> str:
    """Make a value safe for one pipe-separated row (no pipes, no newlines)."""
    return " ".join(str(text).replace("|", "/").split())


def _meta_str(metadata: dict | None) -> str:
    """Encode the useful metadata compactly: `focused;value=...;shortcut=...`.

    `has_focused: false` (the overwhelmingly common case) is dropped entirely —
    only the keys that carry signal for the brain survive.
    """
    if not metadata:
        return ""
    parts = []
    if metadata.get("has_focused"):
        parts.append("focused")
    for key, label in (("value", "value"), ("shortcut", "shortcut"),
                       ("toggle_state", "toggle"), ("help_text", "help")):
        v = metadata.get(key)
        if v not in (None, ""):
            parts.append(f"{label}={_clean(v)}")
    return ";".join(parts)


def serialize_tree(active_window: str, nodes: list) -> str:
    """Serialize interactive nodes into the compact table the brain receives.

    Trims aggressively (smaller payload = fewer LLM input tokens = faster steps):
      - drops per-row coordinates (the brain targets elements by NAME; coords are
        only ever used on the vision fallback, where the tree is empty anyway)
      - drops the window column (the tree covers only the active window; a node
        from another window keeps a `win=` marker in its meta)
      - drops rows with no name and no metadata — they cannot be targeted and
        carry no signal
      - strips the redundant "Control" suffix from control types
      - caps the row count at MAX_TREE_ELEMENTS

    Ids are the original snapshot indices (see module docstring).
    """
    rows = [f"ACTIVE WINDOW: {_clean(active_window)}", "# id|type|name|meta"]
    emitted = 0
    omitted = 0
    for idx, node in enumerate(nodes):
        name = _clean(getattr(node, "name", "") or "")
        meta = _meta_str(getattr(node, "metadata", None))
        win = _clean(getattr(node, "window_name", "") or "")
        if win and win != _clean(active_window):
            meta = f"win={win};{meta}" if meta else f"win={win}"
        if not name and not meta:
            continue  # untargetable, zero-signal row
        if emitted >= MAX_TREE_ELEMENTS:
            omitted += 1
            continue
        ctype = _clean(getattr(node, "control_type", "") or "")
        if ctype.endswith("Control"):
            ctype = ctype[: -len("Control")]
        rows.append(f"{idx}|{ctype}|{name}|{meta}")
        emitted += 1
    if omitted:
        rows.append(f"# +{omitted} more elements omitted")
    return "\n".join(rows)


class Perceiver:
    def __init__(self, desktop: Desktop) -> None:
        self._desktop = desktop

    def perceive(self) -> Perception:
        """Capture and serialize the current UI tree for the brain."""
        state = self._desktop.get_state()
        tree = state.tree_state
        nodes = tree.interactive_nodes or []
        active = state.active_window.name if state.active_window else "(no active window)"
        ui_tree = serialize_tree(active, nodes)
        return Perception(ui_tree=ui_tree, is_empty=(not tree.status) or (not nodes))

    def capture_screenshot(self) -> str:
        """Base64 PNG of the screen — sent only on the tree-insufficient fallback (Rule 5)."""
        png = self._desktop.get_screenshot(as_bytes=True)
        return base64.b64encode(png).decode("ascii")
