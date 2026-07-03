"""Read the live Windows screen, tree-first (CLAUDE.md Rule 5).

Primary perception is the Windows UI Automation tree via windows-use's headless
`Desktop` (no LLM, no Agent). A screenshot is captured ONLY when the tree is
insufficient for the active window (no elements, or window chrome only — canvas /
DirectX / custom-drawn apps) or when the brain explicitly asked to see the screen
(`need_screenshot`) — the vision fallback.

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
# A handful of scrollable panes is plenty of signal; more is nested-container noise.
MAX_SCROLLABLE_ELEMENTS = 8


@dataclass
class Perception:
    ui_tree: str   # compact table sent to the brain (id|type|name|meta)
    is_empty: bool  # True when the tree is insufficient for the active window -> vision fallback


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


def _scroll_pos(metadata: dict | None) -> str:
    """Compact scroll position: `v=35%` (0%=top, 100%=bottom). UIA reports the
    percent as 0-100, or -1 when the pane cannot actually scroll right now."""
    v = (metadata or {}).get("vertical_scroll_percent")
    if not isinstance(v, (int, float)) or v < 0:
        return "v=?"
    return f"v={min(max(v, 0), 100):.0f}%"


def serialize_scrollables(nodes: list) -> str:
    """The SCROLLABLE PANES section appended under the tree.

    Off-screen elements are filtered out of the interactive tree entirely, so
    without this section the brain cannot tell "the element does not exist" from
    "the element is below the fold" — it would re-plan against the same viewport
    forever instead of scrolling.
    """
    rows = []
    for node in nodes[:MAX_SCROLLABLE_ELEMENTS]:
        name = _clean(getattr(node, "name", "") or "")
        ctype = _clean(getattr(node, "control_type", "") or "")
        if ctype.endswith("Control"):
            ctype = ctype[: -len("Control")]
        if not name and not ctype:
            continue
        rows.append(f"{ctype}|{name}|{_scroll_pos(getattr(node, 'metadata', None))}")
    if not rows:
        return ""
    return "\n".join(
        ["SCROLLABLE PANES (more content off-screen; v=0% top, v=100% bottom):",
         "# type|name|scrolled"] + rows)


# Bare window-chrome names: when the active window's OWN rows are only these, the
# app paints its content itself (canvas/DirectX/custom-drawn) and the tree gives
# the brain nothing to act on — the vision fallback must fire (Rule 5).
_CHROME_NAMES = frozenset(
    {"minimize", "maximize", "restore", "close", "system", "system menu bar"})


def tree_insufficient(active_window: str, nodes: list) -> bool:
    """True when the tree carries no actionable content for the ACTIVE window.

    Foreign-window rows (the taskbar is always present) do not count as content —
    they would mask an unreadable foreground app. A row counts as content when it
    has a non-chrome name, or no name but real metadata (the same signal rule the
    serializer uses to keep a row).
    """
    active = _clean(active_window).lower()
    for node in nodes:
        win = _clean(getattr(node, "window_name", "") or "").lower()
        if win and win != active:
            continue
        name = _clean(getattr(node, "name", "") or "").lower()
        if name and name not in _CHROME_NAMES:
            return False
        if not name and _meta_str(getattr(node, "metadata", None)):
            return False
    return True


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
        scroll_block = serialize_scrollables(getattr(tree, "scrollable_nodes", None) or [])
        if scroll_block:
            ui_tree = f"{ui_tree}\n{scroll_block}"
        insufficient = (not tree.status) or tree_insufficient(active, nodes)
        return Perception(ui_tree=ui_tree, is_empty=insufficient)

    def capture_screenshot(self) -> str:
        """Base64 PNG of the screen — sent only on the vision fallback (Rule 5).

        When the snapshot has interactive elements, the shot is annotated with
        numbered boxes whose labels ARE the tree ids, so the brain can keep
        answering with ids/names instead of raw coordinates.
        """
        state = getattr(self._desktop, "desktop_state", None)
        nodes = state.tree_state.interactive_nodes if state and state.tree_state else []
        png = None
        if nodes:
            try:
                png = self._desktop.get_annotated_screenshot(nodes=nodes, as_bytes=True)
            except Exception:
                png = None  # annotation is best-effort; the plain screen still helps
        if png is None:
            png = self._desktop.get_screenshot(as_bytes=True)
        return base64.b64encode(png).decode("ascii")
