"""Test doubles for the OrphicOS client unit tests.

These are TEST FIXTURES ONLY (CLAUDE.md Rule 14): hand-built stand-ins for
windows-use's headless `Desktop` and the OrphicOS `BrainClient`, so the client's
Actor and control-loop LOGIC can be exercised WITHOUT a live desktop, a network
call, or an LLM. Nothing here is ever imported by a product path — only by
client/tests/*. The real Actor/Perceiver/loop code under test is the genuine article.
"""
from __future__ import annotations


class FakeCenter:
    def __init__(self, x: int = 50, y: int = 60) -> None:
        self.x = x
        self.y = y


class FakeNode:
    """Stands in for a windows-use TreeElementNode/ScrollElementNode."""

    def __init__(self, name: str, control_type: str = "ButtonControl",
                 window_name: str = "Test Window", metadata: dict | None = None,
                 center: FakeCenter | None = None) -> None:
        self.name = name
        self.control_type = control_type
        self.window_name = window_name
        self.metadata = metadata or {}
        self.center = center or FakeCenter()


class FakeTreeState:
    def __init__(self, nodes: list[FakeNode], status: bool = True,
                 scrollable_nodes: list[FakeNode] | None = None) -> None:
        self.interactive_nodes = list(nodes)
        self.status = status
        self.scrollable_nodes = list(scrollable_nodes or [])


class FakeWindow:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeDesktopState:
    def __init__(self, tree_state: FakeTreeState, active_window: FakeWindow | None) -> None:
        self.tree_state = tree_state
        self.active_window = active_window


class FakeDesktop:
    """Records every action performed on it; resolves labels to deterministic coords.

    `calls` is an ordered list of tuples (method_name, *args) so tests can assert the
    exact windows-use calls the Actor made, without touching a real desktop.
    """

    def __init__(self, node_names: list[str] | None = None, active_window: str | None = None,
                 tree_status: bool = True, screenshot: bytes = b"\x89PNG-fake",
                 raise_on_coords: Exception | None = None,
                 scrollable_nodes: list[FakeNode] | None = None) -> None:
        # Nodes belong to the active window, mirroring a real snapshot — the
        # perceiver treats foreign-window rows (e.g. taskbar) as non-content.
        self._window_name = active_window or "Test Window"
        nodes = [FakeNode(n, window_name=self._window_name) for n in (node_names or [])]
        self._tree = FakeTreeState(nodes, status=tree_status, scrollable_nodes=scrollable_nodes)
        win = FakeWindow(active_window) if active_window else None
        self.desktop_state = FakeDesktopState(self._tree, win)
        self._screenshot = screenshot
        # Set to simulate windows-use raising a live-COM error (e.g. a control that went
        # stale between perception and action) — see FakeDesktop.get_coordinates_from_label.
        self._raise_on_coords = raise_on_coords
        self.calls: list[tuple] = []

    # --- perception (used by Perceiver, and by the loop's intra-batch refresh) --
    def get_state(self) -> FakeDesktopState:
        self.calls.append(("get_state",))
        return self.desktop_state

    def set_nodes(self, node_names: list[str]) -> None:
        """Simulate a screen change: replace the interactive nodes of the snapshot."""
        self._tree.interactive_nodes = [FakeNode(n, window_name=self._window_name)
                                        for n in node_names]

    def get_screenshot(self, as_bytes: bool = False):
        return self._screenshot if as_bytes else "<screenshot>"

    def get_annotated_screenshot(self, nodes=None, as_bytes: bool = False):
        self.calls.append(("get_annotated_screenshot", len(nodes or [])))
        return self._screenshot if as_bytes else "<annotated>"

    # --- element resolution (used by Actor) --------------------------------
    def get_coordinates_from_label(self, label: int) -> tuple[int, int]:
        self.calls.append(("get_coordinates_from_label", label))
        if self._raise_on_coords is not None:  # mimic windows-use's live-COM failure
            raise self._raise_on_coords
        return (100 + label, 200 + label)  # unique, deterministic per label

    # --- actions (used by Actor) -------------------------------------------
    def click(self, loc, button: str = "left", clicks: int = 2) -> None:
        self.calls.append(("click", loc, button, clicks))

    def type(self, loc, text, caret_position="none", clear="false", press_enter="false") -> None:
        self.calls.append(("type", loc, text))

    def shortcut(self, chord: str) -> None:
        self.calls.append(("shortcut", chord))

    def scroll(self, loc=None, type="vertical", direction="down", wheel_times=1) -> None:
        self.calls.append(("scroll", loc, type, direction, wheel_times))

    def app(self, mode, name=None, loc=None) -> str:
        self.calls.append(("app", mode, name))
        return f"{mode}:{name}"


class FakeBrain:
    """Returns a scripted decision per decide() call; records what it was asked.

    Passing fewer decisions than steps repeats the last one (handy for max_steps tests).
    A scripted entry that is an Exception instance is RAISED instead of returned, so
    tests can exercise the loop's transient-error retry path.
    """

    def __init__(self, decisions: list, health_ok: bool = True) -> None:
        self._decisions = decisions
        self._i = 0
        self.health_ok = health_ok
        self.seen: list[dict] = []

    def health(self) -> bool:
        return self.health_ok

    def decide(self, command, ui_tree, state, screenshot=None) -> dict:
        self.seen.append({"command": command, "ui_tree": ui_tree,
                          "state": state, "screenshot": screenshot})
        decision = self._decisions[min(self._i, len(self._decisions) - 1)]
        self._i += 1
        if isinstance(decision, Exception):
            raise decision
        return decision
