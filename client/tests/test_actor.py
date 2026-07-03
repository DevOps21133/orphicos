"""Unit tests for client.act.actor.Actor — the action executor's mapping logic.

No live desktop: a FakeDesktop records calls; the one path that reaches real
windows-use (the focused-type SendKeys fallback) is patched so no keystrokes fire.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from client.act import ActionError, Actor
from client.tests.fakes import FakeDesktop

# The client's side of the server action contract (server/brain.py ALLOWED_ACTIONS).
# Kept explicit here so a drift between server verbs and client handlers fails a test.
EXPECTED_VERBS = (
    "launch", "click", "double_click", "right_click",
    "type", "press", "scroll", "focus_window", "wait", "wait_for",
    "set_clipboard", "open_path", "screenshot",
)


class LabelResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = FakeDesktop(node_names=["Save", "Save As", "Cancel", "Text editor"])
        self.actor = Actor(self.desktop)

    def test_exact_case_insensitive_wins_over_prefix(self):
        # "Save" must resolve to index 0 (exact), NOT "Save As" (a prefix match).
        self.assertEqual(self.actor._label_for("save"), 0)

    def test_prefix_match(self):
        self.assertEqual(self.actor._label_for("Save A"), 1)

    def test_substring_match(self):
        self.assertEqual(self.actor._label_for("editor"), 3)

    def test_digit_index(self):
        self.assertEqual(self.actor._label_for("2"), 2)

    def test_out_of_range_digit_falls_through_to_no_match(self):
        # "9" is not a valid index and matches no name -> None (-> ActionError upstream).
        self.assertIsNone(self.actor._label_for("9"))

    def test_stale_digit_id_falls_back_to_name_match(self):
        # A batched action's id can go stale after the screen changes: an out-of-range
        # digit id must still resolve if an element NAME matches it.
        actor = Actor(FakeDesktop(node_names=["Save", "7-Zip"]))
        self.assertEqual(actor._label_for("7"), 1)

    def test_unknown_name_is_none(self):
        self.assertIsNone(self.actor._label_for("nonexistent-element"))

    def test_empty_tree_is_none(self):
        empty = Actor(FakeDesktop(node_names=[]))
        self.assertIsNone(empty._label_for("Save"))


class ResolveLocTests(unittest.TestCase):
    def test_coords_used_directly_and_int_cast(self):
        actor = Actor(FakeDesktop(node_names=[]))
        loc = actor._resolve_loc({"type": "click", "coords": [12.5, 34.9]})
        self.assertEqual(loc, (12, 34))  # truncated to int, no label lookup needed

    def test_target_selector_resolves_via_label(self):
        desktop = FakeDesktop(node_names=["Save", "Cancel"])
        actor = Actor(desktop)
        loc = actor._resolve_loc({"type": "click", "target_selector": "Cancel"})
        self.assertEqual(loc, (101, 201))  # label 1 -> (100+1, 200+1)

    def test_unresolvable_selector_raises(self):
        actor = Actor(FakeDesktop(node_names=["Save"]))
        with self.assertRaises(ActionError):
            actor._resolve_loc({"type": "click", "target_selector": "Ghost"})

    def test_no_target_and_no_coords_returns_none(self):
        actor = Actor(FakeDesktop(node_names=["Save"]))
        self.assertIsNone(actor._resolve_loc({"type": "scroll"}))


class ActionDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = FakeDesktop(node_names=["Save", "Cancel", "Text editor"])
        self.actor = Actor(self.desktop)

    def test_every_allowlisted_verb_has_a_handler(self):
        for verb in EXPECTED_VERBS:
            self.assertTrue(hasattr(self.actor, f"_do_{verb}"),
                            f"Actor is missing a handler for allowlisted verb {verb!r}")

    def test_unknown_verb_raises(self):
        with self.assertRaises(ActionError):
            self.actor.execute({"type": "teleport"})

    def test_execute_converts_foreign_exception_to_actionerror(self):
        # A control that went stale makes windows-use raise a live-COM error; execute() must
        # convert it to ActionError so the loop SKIPS the action instead of crashing the run.
        desktop = FakeDesktop(node_names=["Save"],
                              raise_on_coords=RuntimeError("UIA_E_ELEMENTNOTAVAILABLE"))
        actor = Actor(desktop)
        with self.assertRaises(ActionError) as ctx:
            actor.execute({"type": "click", "target_selector": "Save"})
        self.assertIn("click failed", str(ctx.exception))

    def test_click_is_single_left_click(self):
        self.actor.execute({"type": "click", "target_selector": "Save"})
        self.assertIn(("click", (100, 200), "left", 1), self.desktop.calls)

    def test_double_click(self):
        self.actor.execute({"type": "double_click", "target_selector": "Save"})
        self.assertIn(("click", (100, 200), "left", 2), self.desktop.calls)

    def test_right_click(self):
        self.actor.execute({"type": "right_click", "target_selector": "Save"})
        self.assertIn(("click", (100, 200), "right", 1), self.desktop.calls)

    def test_type_into_resolved_target(self):
        self.actor.execute({"type": "type", "target_selector": "Text editor", "value": "hello"})
        self.assertIn(("type", (102, 202), "hello"), self.desktop.calls)

    def test_type_into_focus_uses_sendkeys_fallback(self):
        # No target -> type into whatever has focus, via uia.SendKeys (patched: no real keys).
        # foreground_console_label -> None: a normal GUI window has focus, so keys are allowed.
        with patch("client.act.actor.uia.SendKeys") as send, \
                patch("client.act.actor.foreground_console_label", return_value=None):
            result = self.actor.execute({"type": "type", "value": "focused text"})
        send.assert_called_once()
        # windows-use is never asked to click/type when there's no target.
        self.assertFalse(any(c[0] == "type" for c in self.desktop.calls))
        self.assertEqual(result, "typed into focused control")

    def test_untargeted_type_refused_when_console_focused(self):
        # A focused terminal must NOT receive blind keystrokes (they'd run as shell commands).
        with patch("client.act.actor.uia.SendKeys") as send, \
                patch("client.act.actor.foreground_console_label", return_value="ConsoleWindowClass"):
            with self.assertRaises(ActionError) as ctx:
                self.actor.execute({"type": "type", "value": "test_orphic"})
        send.assert_not_called()  # nothing typed into the console
        self.assertIn("console", str(ctx.exception).lower())

    def test_targeted_type_not_blocked_by_console_guard(self):
        # A resolved on-screen target types into that element, not the foreground, so the
        # console guard does not apply even if a terminal happens to be foreground.
        with patch("client.act.actor.foreground_console_label", return_value="ConsoleWindowClass"):
            self.actor.execute({"type": "type", "target_selector": "Text editor", "value": "hi"})
        self.assertIn(("type", (102, 202), "hi"), self.desktop.calls)

    def test_press_dispatches_shortcut(self):
        with patch("client.act.actor.foreground_console_label", return_value=None):
            self.actor.execute({"type": "press", "value": "ctrl+s"})
        self.assertIn(("shortcut", "ctrl+s"), self.desktop.calls)

    def test_press_refused_when_console_focused(self):
        # Shortcuts (ctrl+shift+n, f2, enter, ...) must not fire into a focused console either.
        with patch("client.act.actor.foreground_console_label", return_value="powershell.exe"):
            with self.assertRaises(ActionError) as ctx:
                self.actor.execute({"type": "press", "value": "ctrl+shift+n"})
        self.assertFalse(any(c[0] == "shortcut" for c in self.desktop.calls))
        self.assertIn("console", str(ctx.exception).lower())

    def test_press_without_value_raises(self):
        with self.assertRaises(ActionError):
            self.actor.execute({"type": "press", "value": None})

    def test_launch_uses_value(self):
        self.actor.execute({"type": "launch", "value": "notepad"})
        self.assertIn(("app", "launch", "notepad"), self.desktop.calls)

    def test_launch_falls_back_to_target_selector(self):
        self.actor.execute({"type": "launch", "target_selector": "Excel"})
        self.assertIn(("app", "launch", "Excel"), self.desktop.calls)

    def test_launch_without_name_raises(self):
        with self.assertRaises(ActionError):
            self.actor.execute({"type": "launch"})

    def test_focus_window_switches(self):
        self.actor.execute({"type": "focus_window", "value": "Book1 - Excel"})
        self.assertIn(("app", "switch", "Book1 - Excel"), self.desktop.calls)


class ScreenshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = FakeDesktop(node_names=[], screenshot=b"\x89PNG-fake")
        self.actor = Actor(self.desktop)

    def test_screenshot_saves_png_to_given_path(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "shot.png"
            result = self.actor.execute({"type": "screenshot", "value": str(target)})
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), b"\x89PNG-fake")
            self.assertIn(str(target), result)

    def test_screenshot_directory_value_gets_named_file_inside(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            self.actor.execute({"type": "screenshot", "value": td})
            files = list(Path(td).glob("orphic_screenshot_*.png"))
            self.assertEqual(len(files), 1)

    def test_screenshot_default_path_is_pictures_screenshots(self):
        # Patch home so the default path never touches the real user profile.
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            with patch("client.act.actor.Path.home", return_value=Path(td)):
                result = self.actor.execute({"type": "screenshot", "value": None})
            files = list((Path(td) / "Pictures" / "Screenshots").glob("orphic_screenshot_*.png"))
            self.assertEqual(len(files), 1)
            self.assertIn("Screenshots", result)


class ScrollAndWaitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = FakeDesktop(node_names=[])
        self.actor = Actor(self.desktop)

    def test_scroll_up_is_vertical(self):
        self.actor.execute({"type": "scroll", "value": "up"})
        self.assertIn(("scroll", None, "vertical", "up", 3), self.desktop.calls)

    def test_scroll_left_is_horizontal(self):
        self.actor.execute({"type": "scroll", "value": "left"})
        self.assertIn(("scroll", None, "horizontal", "left", 3), self.desktop.calls)

    def test_scroll_unknown_direction_defaults_down(self):
        self.actor.execute({"type": "scroll", "value": "sideways"})
        self.assertIn(("scroll", None, "vertical", "down", 3), self.desktop.calls)

    def test_scroll_targets_scrollable_pane_by_name(self):
        # "Document" is a SCROLLABLE pane, not an interactive element: the scroll
        # must land at the pane's centre instead of failing resolution.
        from client.tests.fakes import FakeCenter, FakeNode
        desktop = FakeDesktop(
            node_names=["Save"],
            scrollable_nodes=[FakeNode("Document", "PaneControl",
                                       center=FakeCenter(400, 300))])
        Actor(desktop).execute({"type": "scroll", "target_selector": "Document",
                                "value": "down"})
        self.assertIn(("scroll", (400, 300), "vertical", "down", 3), desktop.calls)

    def test_scroll_with_unknown_target_falls_back_to_focused_window(self):
        # A bad scroll target must never fail the action — scrolling the focused
        # window is always sane.
        self.actor.execute({"type": "scroll", "target_selector": "Ghost pane",
                            "value": "down"})
        self.assertIn(("scroll", None, "vertical", "down", 3), self.desktop.calls)

    def test_wait_clamps_high(self):
        self.assertEqual(self.actor.execute({"type": "wait", "value": "20"}), "waited 10s")

    def test_wait_clamps_negative(self):
        self.assertEqual(self.actor.execute({"type": "wait", "value": "-5"}), "waited 0s")

    def test_wait_non_numeric_defaults_to_one(self):
        self.assertEqual(self.actor.execute({"type": "wait", "value": "soon"}), "waited 1s")


class WaitForTests(unittest.TestCase):
    def setUp(self) -> None:
        import client.act.actor as actor_module
        self._mod = actor_module
        # Fast polling for tests; sleep is real but 0-length via the poll constant.
        self._patches = [
            patch.object(actor_module, "_WAIT_FOR_TIMEOUT", 0.2),
            patch.object(actor_module, "_WAIT_FOR_POLL", 0.01),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_returns_when_element_already_present(self):
        actor = Actor(FakeDesktop(node_names=["Download complete"]))
        result = actor.execute({"type": "wait_for", "value": "Download complete"})
        self.assertIn("appeared", result)

    def test_matches_active_window_title(self):
        actor = Actor(FakeDesktop(node_names=[], active_window="Setup - Finished"))
        result = actor.execute({"type": "wait_for", "value": "Finished"})
        self.assertIn("appeared", result)

    def test_returns_when_element_appears_later(self):
        desktop = FakeDesktop(node_names=[])
        polls = {"n": 0}
        real_get_state = desktop.get_state

        def appearing_get_state():
            polls["n"] += 1
            if polls["n"] == 3:
                desktop.set_nodes(["Install finished"])
            return real_get_state()

        desktop.get_state = appearing_get_state
        result = Actor(desktop).execute({"type": "wait_for", "value": "Install finished"})
        self.assertIn("appeared", result)

    def test_gone_prefix_waits_for_disappearance(self):
        actor = Actor(FakeDesktop(node_names=["Save"]))  # "Installing" is not present
        result = actor.execute({"type": "wait_for", "value": "gone:Installing"})
        self.assertIn("disappeared", result)

    def test_timeout_raises_actionerror_for_replan(self):
        actor = Actor(FakeDesktop(node_names=[]))
        with self.assertRaises(ActionError) as ctx:
            actor.execute({"type": "wait_for", "value": "Never appears"})
        self.assertIn("timed out", str(ctx.exception))

    def test_kill_switch_breaks_the_poll(self):
        actor = Actor(FakeDesktop(node_names=[]), should_stop=lambda: True)
        result = actor.execute({"type": "wait_for", "value": "Never appears"})
        self.assertIn("interrupted", result)

    def test_missing_name_raises(self):
        actor = Actor(FakeDesktop(node_names=[]))
        with self.assertRaises(ActionError):
            actor.execute({"type": "wait_for", "value": "gone:"})


class ClipboardAndPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = FakeDesktop(node_names=["Text editor"])
        self.actor = Actor(self.desktop)

    def test_set_clipboard_writes_text(self):
        with patch("client.act.actor.uia.SetClipboardText", return_value=True) as put:
            result = self.actor.execute({"type": "set_clipboard", "value": "hello"})
        put.assert_called_once_with("hello")
        self.assertEqual(result, "clipboard set (5 chars)")

    def test_set_clipboard_failure_raises(self):
        with patch("client.act.actor.uia.SetClipboardText", return_value=False):
            with self.assertRaises(ActionError):
                self.actor.execute({"type": "set_clipboard", "value": "hello"})

    def test_set_clipboard_without_value_raises(self):
        with self.assertRaises(ActionError):
            self.actor.execute({"type": "set_clipboard", "value": None})

    def test_open_path_starts_default_handler(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "report.txt"
            target.write_text("x")
            with patch("client.act.actor.os.startfile") as start:
                result = self.actor.execute({"type": "open_path", "value": str(target)})
            start.assert_called_once_with(str(target))
            self.assertIn("report.txt", result)

    def test_open_path_missing_raises_without_launching(self):
        with patch("client.act.actor.os.startfile") as start:
            with self.assertRaises(ActionError) as ctx:
                self.actor.execute({"type": "open_path",
                                    "value": r"C:\definitely\not\here.xyz"})
        start.assert_not_called()
        self.assertIn("does not exist", str(ctx.exception))

    def test_open_path_without_value_raises(self):
        with self.assertRaises(ActionError):
            self.actor.execute({"type": "open_path", "value": None})


class LongTextPasteTests(unittest.TestCase):
    LONG = "x" * 250  # over the clipboard threshold

    def setUp(self) -> None:
        self.desktop = FakeDesktop(node_names=["Text editor"])
        self.actor = Actor(self.desktop)

    def test_long_targeted_type_pastes_via_clipboard(self):
        with patch("client.act.actor.uia.SetClipboardText", return_value=True) as put:
            result = self.actor.execute({"type": "type", "target_selector": "Text editor",
                                         "value": self.LONG})
        put.assert_called_once_with(self.LONG)
        # Click focuses the target, then ctrl+v delivers the text — no char typing.
        self.assertIn(("click", (100, 200), "left", 1), self.desktop.calls)
        self.assertIn(("shortcut", "ctrl+v"), self.desktop.calls)
        self.assertFalse(any(c[0] == "type" for c in self.desktop.calls))
        self.assertIn("pasted 250 chars", result)

    def test_long_untargeted_type_pastes_into_focus(self):
        with patch("client.act.actor.uia.SetClipboardText", return_value=True), \
                patch("client.act.actor.foreground_console_label", return_value=None):
            result = self.actor.execute({"type": "type", "value": self.LONG})
        self.assertIn(("shortcut", "ctrl+v"), self.desktop.calls)
        self.assertIn("pasted 250 chars", result)

    def test_long_untargeted_paste_refused_when_console_focused(self):
        with patch("client.act.actor.uia.SetClipboardText", return_value=True), \
                patch("client.act.actor.foreground_console_label",
                      return_value="ConsoleWindowClass"):
            with self.assertRaises(ActionError):
                self.actor.execute({"type": "type", "value": self.LONG})
        self.assertNotIn(("shortcut", "ctrl+v"), self.desktop.calls)

    def test_clipboard_failure_falls_back_to_typing(self):
        with patch("client.act.actor.uia.SetClipboardText", return_value=False):
            result = self.actor.execute({"type": "type", "target_selector": "Text editor",
                                         "value": self.LONG})
        self.assertIn(("type", (100, 200), self.LONG), self.desktop.calls)
        self.assertIn("typed into", result)

    def test_short_text_still_typed_directly(self):
        with patch("client.act.actor.uia.SetClipboardText") as put:
            self.actor.execute({"type": "type", "target_selector": "Text editor",
                                "value": "short"})
        put.assert_not_called()
        self.assertIn(("type", (100, 200), "short"), self.desktop.calls)


if __name__ == "__main__":
    unittest.main()
