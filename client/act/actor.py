"""Execute the brain's actions on the live Windows desktop.

Maps the server's action contract — {type, target_selector|coords, value} — onto
windows-use's headless `Desktop` methods (click / type / scroll / shortcut / app).
No LLM here: the *decide* step already happened on the server; this only acts.

Element targeting: the brain returns `target_selector` (the element's Name, as shown
in the tree it received) or, on the vision fallback, raw `coords`. We resolve a name
to the matching interactive node's id in the CURRENT snapshot, then ask the Desktop
for that element's live centre coordinates.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import monotonic, sleep

from client._engine import Desktop, escape_text_for_sendkeys, uia
from client.act._focus_guard import foreground_console_label


class ActionError(RuntimeError):
    """An action could not be executed (unknown type, or no matching element)."""


def _refuse_if_console(what: str) -> None:
    """Guard blind keystrokes: OrphicOS never drives a terminal, so if a console has
    focus these keys would run as shell commands (outside the kill switch). Skip them."""
    console = foreground_console_label()
    if console is not None:
        raise ActionError(
            f"refused to send {what} into a focused console ({console}); "
            "no GUI target is focused")


class Actor:
    def __init__(self, desktop: Desktop) -> None:
        self._desktop = desktop

    def execute(self, action: dict) -> str:
        """Run one action; return a short human-readable result for the live log."""
        atype = str(action.get("type") or "").strip()
        handler = getattr(self, f"_do_{atype}", None)
        if handler is None:
            raise ActionError(f"unsupported action type: {atype!r}")
        try:
            return handler(action, action.get("value"))
        except ActionError:
            raise
        except Exception as e:  # noqa: BLE001 — deliberate: any engine failure becomes skippable
            # windows-use reads a control's live BoundingRectangle at act time; a control
            # that went stale during the brain round-trip raises comtypes.COMError (not an
            # ActionError). Convert it so the loop SKIPS this action and re-perceives,
            # rather than crashing the whole run on a half-finished desktop.
            raise ActionError(f"{atype} failed: {type(e).__name__}: {e}") from e

    # --- element resolution ------------------------------------------------
    def _resolve_loc(self, action: dict) -> tuple[int, int] | None:
        coords = action.get("coords")
        if isinstance(coords, (list, tuple)) and len(coords) == 2:
            return int(coords[0]), int(coords[1])
        sel = action.get("target_selector")
        if not sel:
            return None
        label = self._label_for(str(sel))
        if label is None:
            raise ActionError(f"no on-screen element matches {sel!r}")
        return self._desktop.get_coordinates_from_label(label)

    def _label_for(self, sel: str) -> int | None:
        """Resolve a target_selector (element id or Name) to an interactive-node id."""
        state = self._desktop.desktop_state
        nodes = (state.tree_state.interactive_nodes or []) if state and state.tree_state else []
        if not nodes:
            return None
        s = sel.strip()
        if s.isdigit() and 0 <= int(s) < len(nodes):
            return int(s)
        low = s.lower()
        named = [(i, (n.name or "").strip()) for i, n in enumerate(nodes)]
        for i, name in named:                                   # exact, case-insensitive
            if name.lower() == low:
                return i
        for i, name in named:                                   # prefix
            if name and name.lower().startswith(low):
                return i
        for i, name in named:                                   # substring
            if name and low in name.lower():
                return i
        return None

    def _scrollable_center(self, sel: str) -> tuple[int, int] | None:
        """Resolve a scroll target against the snapshot's SCROLLABLE panes by name."""
        state = self._desktop.desktop_state
        tree = state.tree_state if state else None
        low = sel.strip().lower()
        if not low or tree is None:
            return None
        for node in (getattr(tree, "scrollable_nodes", None) or []):
            name = (getattr(node, "name", "") or "").strip().lower()
            if name and (low in name or name in low):
                center = getattr(node, "center", None)
                if center is not None:
                    return int(center.x), int(center.y)
        return None

    def _require_loc(self, action: dict) -> tuple[int, int]:
        loc = self._resolve_loc(action)
        if loc is None:
            raise ActionError("action needs a target element or coordinates")
        return loc

    # --- action handlers ---------------------------------------------------
    def _do_launch(self, action: dict, value) -> str:
        name = value or action.get("target_selector")
        if not name:
            raise ActionError("launch needs an app name in 'value'")
        result = str(self._desktop.app(mode="launch", name=str(name)))
        self._ensure_foreground(str(name))
        return result

    def _ensure_foreground(self, app_name: str, timeout: float = 6.0) -> None:
        """The brain's contract says a launched app IS the foreground window, but the
        engine's launch returns before the window exists, and focus can bounce back to
        the previous window (e.g. the browser hosting the shell). Without this, the
        next perceive shows the OLD window and the brain relaunches in a loop. Poll
        until the app owns the foreground; halfway through, try an explicit switch."""
        want = app_name.strip().lower()
        deadline = monotonic() + timeout
        tried_switch = False
        while monotonic() < deadline:
            sleep(0.4)
            state = self._desktop.get_state()
            active = (state.active_window.name if state.active_window else "") or ""
            if want in active.lower():
                return
            if not tried_switch and (deadline - monotonic()) < timeout / 2:
                tried_switch = True
                try:
                    self._desktop.app(mode="switch", name=app_name)
                except Exception:  # noqa: BLE001 — window may not exist yet; keep polling
                    pass
        # Never fail the launch over focus: the loop re-perceives and the brain
        # can still recover with focus_window.

    def _do_focus_window(self, action: dict, value) -> str:
        name = value or action.get("target_selector")
        if not name:
            raise ActionError("focus_window needs a window name")
        return str(self._desktop.app(mode="switch", name=str(name)))

    def _do_click(self, action: dict, value) -> str:
        loc = self._require_loc(action)
        self._desktop.click(loc, button="left", clicks=1)
        return f"clicked {loc}"

    def _do_double_click(self, action: dict, value) -> str:
        loc = self._require_loc(action)
        self._desktop.click(loc, button="left", clicks=2)
        return f"double-clicked {loc}"

    def _do_right_click(self, action: dict, value) -> str:
        loc = self._require_loc(action)
        self._desktop.click(loc, button="right", clicks=1)
        return f"right-clicked {loc}"

    def _do_type(self, action: dict, value) -> str:
        text = "" if value is None else str(value)
        loc = self._resolve_loc(action)
        if loc is not None:
            self._desktop.type(loc, text=text)
            return f"typed into {loc}"
        # No target -> type into whatever control currently has focus.
        _refuse_if_console("typed text")
        uia.SendKeys(escape_text_for_sendkeys(text), interval=0.01, waitTime=0.05)
        return "typed into focused control"

    def _do_press(self, action: dict, value) -> str:
        if not value:
            raise ActionError("press needs a key chord in 'value' (e.g. 'ctrl+s')")
        _refuse_if_console(f"key chord {value!r}")
        self._desktop.shortcut(str(value))
        return f"pressed {value}"

    def _do_scroll(self, action: dict, value) -> str:
        # A scroll target may name a SCROLLABLE pane (not an interactive element),
        # and a stale/wrong name should never fail a scroll — the focused window
        # is always a sane place to scroll. So resolution degrades, never raises.
        try:
            loc = self._resolve_loc(action)  # optional; None scrolls the focused window
        except ActionError:
            loc = self._scrollable_center(str(action.get("target_selector") or ""))
        direction = str(value).lower() if value else "down"
        if direction not in ("up", "down", "left", "right"):
            direction = "down"
        stype = "horizontal" if direction in ("left", "right") else "vertical"
        self._desktop.scroll(loc=loc, type=stype, direction=direction, wheel_times=3)
        return f"scrolled {direction}"

    def _do_screenshot(self, action: dict, value) -> str:
        """Capture the screen and save it ON THIS MACHINE (the user's own PC).

        The image never travels to the server — this is a local deliverable the
        user asked for, unlike the Rule 5 vision fallback in client/perceive.
        `value` may name an absolute .png path; default is Pictures\\Screenshots.
        """
        png = self._desktop.get_screenshot(as_bytes=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if value:
            path = Path(str(value)).expanduser()
            if path.suffix.lower() != ".png":  # a folder was given -> name the file inside it
                path = path / f"orphic_screenshot_{stamp}.png"
        else:
            path = Path.home() / "Pictures" / "Screenshots" / f"orphic_screenshot_{stamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        return f"screenshot saved to {path}"

    def _do_wait(self, action: dict, value) -> str:
        try:
            seconds = float(value) if value is not None else 1.0
        except (TypeError, ValueError):
            seconds = 1.0
        seconds = max(0.0, min(seconds, 10.0))  # cap so the loop stays responsive
        sleep(seconds)
        return f"waited {seconds:g}s"
