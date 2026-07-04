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
import ctypes
import io
from ctypes import wintypes
from dataclasses import dataclass

from client._engine import Desktop

# Payload guard: real app trees are usually < 300 interactive elements; anything
# beyond this is browser/ribbon noise that only inflates tokens and latency.
MAX_TREE_ELEMENTS = 300
# A handful of scrollable panes is plenty of signal; more is nested-container noise.
MAX_SCROLLABLE_ELEMENTS = 8
# Readable on-screen text lines (Wave 2 "read it back"). Most answerable questions
# are settled by the first pageful of text; the cap keeps the payload bounded when
# a long document/web page is open. Trailing lines are summarized, not dropped.
MAX_TEXT_ELEMENTS = 40

# --- Vision-fallback framing (Rule 5) --------------------------------------------
# windows-use captures the ENTIRE multi-monitor virtual desktop. The vision model
# downscales any image to its own max input size, so a full-desktop shot renders
# small on-screen text (a stock price, a spreadsheet cell) into an illegible smudge
# and the model guesses (it once wrote a from-memory BTC price over the real one).
# We crop the fallback to the ACTIVE window: the relevant content fills the frame,
# stays legible after downscaling, and the payload roughly halves (also faster).
_ANNOTATION_PAD = 5  # windows-use pads the annotated image 5px at the top-left


def _virtual_origin() -> tuple[int, int]:
    """Top-left of the virtual desktop in screen coords (the multi-monitor offset)."""
    u = ctypes.windll.user32
    return u.GetSystemMetrics(76), u.GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN


def _foreground_rect() -> tuple[int, int, int, int] | None:
    """The active window's screen rectangle, or None if it can't be read."""
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    r = wintypes.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(r)) or r.right <= r.left or r.bottom <= r.top:
        return None
    return r.left, r.top, r.right, r.bottom


def _crop_to_active_window(img, pad: int):
    """Crop a full-virtual-desktop capture down to the active window so its text
    survives the vision model's downscaling. Returns the image unchanged if the
    active window can't be located or the crop would be a degenerate sliver.
    Assumes 100% display scaling (CLAUDE.md Rule 11) — physical and logical pixels
    coincide, so window rect and screenshot pixels share one coordinate space."""
    rect = _foreground_rect()
    if rect is None:
        return img
    vx, vy = _virtual_origin()
    left, top, right, bottom = rect
    box = (max(left - vx + pad, 0), max(top - vy + pad, 0),
           min(right - vx + pad, img.width), min(bottom - vy + pad, img.height))
    if box[2] - box[0] < 100 or box[3] - box[1] < 100:
        return img  # a sliver of the wrong thing is worse than the whole frame
    return img.crop(box)


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


def serialize_windows(windows: list, active_name: str) -> str:
    """List every open top-level window as its OWN section above the tree.

    The tree itself shows only the ACTIVE window's contents plus taskbar buttons,
    and a taskbar button cannot distinguish an app that is RUNNING from one merely
    pinned. That gap is exactly what makes the brain re-"launch" an already-open app
    and clobber the user's document (the launch trap). An explicit list of the real
    open windows removes the ambiguity — a name here means "already running: focus
    it, do not launch" — and gives the brain exact window titles to target for
    focus_window / snap. Duplicate titles collapse to one row (identical windows
    cannot be told apart anyway).
    """
    rows = []
    seen = set()
    active = _clean(active_name)
    for w in windows:
        name = _clean(getattr(w, "name", "") or "")
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        status = getattr(getattr(w, "status", None), "value", "") or ""
        extra = f" ({status})" if status and status not in ("Normal", "") else ""
        mark = " [active]" if name == active else ""
        rows.append(f"- {name}{extra}{mark}")
    if not rows:
        return ""
    return ("OPEN WINDOWS (already running — focus_window these, never launch them again):\n"
            + "\n".join(rows))


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


def serialize_text(nodes: list) -> str:
    """The ON-SCREEN TEXT section appended under the tree (Wave 2 "read it back").

    windows-use already collects the active window's readable text — labels, cell
    values, error messages, document body — as `dom_informative_nodes`. The
    interactive tree above carries element NAMES (button labels, edit fields) but is
    blind to static text, so "what does this error say?", "read the total in A6",
    or "what's the selected file?" could not be answered. This section gives the
    brain that text without a screenshot (Rule 5's tree-first principle): fast,
    exact, and cheap, where vision would be slow and lossy.

    Trimmed to stay payload-bounded: near-empty lines dropped, exact duplicates
    collapsed (a status bar that repeats a label), capped at MAX_TEXT_ELEMENTS with
    a "+N more lines" tail when a long document or web page is open.
    """
    seen: set[str] = set()
    rows: list[str] = []
    omitted = 0
    for node in nodes:
        line = _clean(getattr(node, "text", "") or "")
        if not line:
            continue
        if line in seen:  # a status bar / breadcrumb that repeats a nearby label
            continue
        seen.add(line)
        if len(rows) >= MAX_TEXT_ELEMENTS:
            omitted += 1
            continue
        rows.append(line)
    if not rows:
        return ""
    header = "ON-SCREEN TEXT (readable content the brain can read back / answer from):"
    if omitted:
        header += f"  (+{omitted} more lines omitted)"
    return "\n".join([header] + rows)


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
        windows_block = serialize_windows(getattr(state, "windows", None) or [], active)
        if windows_block:
            ui_tree = f"{windows_block}\n\n{ui_tree}"
        scroll_block = serialize_scrollables(getattr(tree, "scrollable_nodes", None) or [])
        if scroll_block:
            ui_tree = f"{ui_tree}\n{scroll_block}"
        text_block = serialize_text(getattr(tree, "dom_informative_nodes", None) or [])
        if text_block:
            ui_tree = f"{ui_tree}\n{text_block}"
        insufficient = (not tree.status) or tree_insufficient(active, nodes)
        return Perception(ui_tree=ui_tree, is_empty=insufficient)

    def capture_screenshot(self) -> str:
        """Base64 PNG of the ACTIVE WINDOW — sent only on the vision fallback (Rule 5).

        The capture is cropped to the foreground window so small on-screen text
        (prices, cell values) stays legible after the vision model downscales it; a
        full multi-monitor frame shrinks that text into an unreadable smudge and the
        model guesses. When the snapshot has interactive elements, the shot is
        annotated with numbered boxes whose labels ARE the tree ids, so the brain can
        keep answering with ids/names instead of raw coordinates.
        """
        state = getattr(self._desktop, "desktop_state", None)
        nodes = state.tree_state.interactive_nodes if state and state.tree_state else []
        img = None
        pad = 0
        if nodes:
            try:
                img = self._desktop.get_annotated_screenshot(nodes=nodes, as_bytes=False)
                pad = _ANNOTATION_PAD
            except Exception:
                img = None  # annotation is best-effort; the plain screen still helps
        if img is None:
            img = self._desktop.get_screenshot(as_bytes=False)
            pad = 0
        img = _crop_to_active_window(img, pad)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        png = buffer.getvalue()
        buffer.close()
        return base64.b64encode(png).decode("ascii")
