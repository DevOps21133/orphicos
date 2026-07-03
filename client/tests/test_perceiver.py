"""Unit tests for the compact UI-tree serializer (client/perceive).

Uses FakeNode/FakeDesktop test fixtures only (CLAUDE.md Rule 14) — the
serialize_tree / Perceiver code under test is the genuine product code.
"""
from __future__ import annotations

import unittest

from client.perceive import Perceiver
from client.perceive.perceiver import (MAX_SCROLLABLE_ELEMENTS, MAX_TREE_ELEMENTS,
                                       serialize_scrollables, serialize_tree)
from client.tests.fakes import FakeDesktop, FakeNode

WIN = "Untitled - Notepad"


def n(name, ctype="ButtonControl", win=WIN, meta=None):
    return FakeNode(name, control_type=ctype, window_name=win, metadata=meta)


class SerializeTreeTest(unittest.TestCase):
    def test_basic_row_format(self) -> None:
        out = serialize_tree(WIN, [n("Save"), n("File", "MenuItemControl")])
        self.assertEqual(out.splitlines(), [
            f"ACTIVE WINDOW: {WIN}",
            "# id|type|name|meta",
            "0|Button|Save|",
            "1|MenuItem|File|",
        ])

    def test_ids_are_original_indices_after_trimming(self) -> None:
        # The unnamed, meta-less node at index 1 is dropped, but ids 0 and 2 keep
        # their snapshot indices so the Actor resolves them against the same list.
        out = serialize_tree(WIN, [n("Save"), n(""), n("Cancel")])
        rows = out.splitlines()[2:]
        self.assertEqual(rows, ["0|Button|Save|", "2|Button|Cancel|"])

    def test_unnamed_node_with_metadata_is_kept(self) -> None:
        out = serialize_tree(WIN, [n("", "EditControl",
                                     meta={"has_focused": True, "value": "hello"})])
        self.assertIn("0|Edit||focused;value=hello", out)

    def test_false_focus_and_empty_metadata_dropped(self) -> None:
        out = serialize_tree(WIN, [n("Save", meta={"has_focused": False})])
        self.assertIn("0|Button|Save|", out)
        self.assertNotIn("focused", out)
        self.assertNotIn("{", out)  # no JSON metadata blobs survive

    def test_metadata_keys_encoded_compactly(self) -> None:
        out = serialize_tree(WIN, [n("Bold", meta={
            "has_focused": True, "shortcut": "Ctrl+B", "toggle_state": "on"})])
        self.assertIn("0|Button|Bold|focused;shortcut=Ctrl+B;toggle=on", out)

    def test_no_coords_or_window_column(self) -> None:
        out = serialize_tree(WIN, [n("Save")])
        self.assertNotIn("(", out.splitlines()[2])  # no per-row coordinates
        self.assertEqual(out.count(WIN), 1)          # window only in the header

    def test_foreign_window_marked_in_meta(self) -> None:
        out = serialize_tree(WIN, [n("OK", win="Some Dialog")])
        self.assertIn("0|Button|OK|win=Some Dialog", out)

    def test_pipes_and_newlines_sanitized(self) -> None:
        out = serialize_tree(WIN, [n("A|B\nC")])
        self.assertIn("0|Button|A/B C|", out)

    def test_row_cap_with_omitted_note(self) -> None:
        nodes = [n(f"El{i}") for i in range(MAX_TREE_ELEMENTS + 25)]
        out = serialize_tree(WIN, nodes)
        rows = [r for r in out.splitlines() if r and r[0].isdigit()]
        self.assertEqual(len(rows), MAX_TREE_ELEMENTS)
        self.assertIn("# +25 more elements omitted", out)

    def test_empty_tree_is_header_only(self) -> None:
        out = serialize_tree(WIN, [])
        self.assertEqual(out.splitlines(), [f"ACTIVE WINDOW: {WIN}", "# id|type|name|meta"])


class SerializeScrollablesTest(unittest.TestCase):
    def test_scroll_position_and_format(self) -> None:
        out = serialize_scrollables([
            n("Document", "PaneControl", meta={"vertical_scroll_percent": 35.4}),
            n("Settings list", "ListControl", meta={"vertical_scroll_percent": 0}),
        ])
        lines = out.splitlines()
        self.assertIn("SCROLLABLE PANES", lines[0])
        self.assertEqual(lines[2], "Pane|Document|v=35%")
        self.assertEqual(lines[3], "List|Settings list|v=0%")

    def test_unscrollable_percent_shown_as_unknown(self) -> None:
        # UIA reports -1 when the pane cannot scroll right now.
        out = serialize_scrollables([n("Doc", meta={"vertical_scroll_percent": -1})])
        self.assertIn("Button|Doc|v=?", out)

    def test_no_scrollables_yields_empty_string(self) -> None:
        self.assertEqual(serialize_scrollables([]), "")

    def test_capped_at_max(self) -> None:
        nodes = [n(f"Pane{i}", "PaneControl") for i in range(MAX_SCROLLABLE_ELEMENTS + 5)]
        out = serialize_scrollables(nodes)
        rows = [r for r in out.splitlines() if r.startswith("Pane|")]
        self.assertEqual(len(rows), MAX_SCROLLABLE_ELEMENTS)


class PerceiverTest(unittest.TestCase):
    def test_perceive_uses_compact_serialization(self) -> None:
        desktop = FakeDesktop(node_names=["Save", "Cancel"], active_window="Test Window")
        p = Perceiver(desktop).perceive()
        self.assertFalse(p.is_empty)
        self.assertEqual(p.ui_tree.splitlines(), [
            "ACTIVE WINDOW: Test Window",
            "# id|type|name|meta",
            "0|Button|Save|",
            "1|Button|Cancel|",
        ])

    def test_empty_tree_flags_vision_fallback(self) -> None:
        desktop = FakeDesktop(node_names=[], active_window="Game")
        p = Perceiver(desktop).perceive()
        self.assertTrue(p.is_empty)

    def test_scrollable_section_appended_under_tree(self) -> None:
        desktop = FakeDesktop(
            node_names=["Save"], active_window="App",
            scrollable_nodes=[n("Document", "PaneControl",
                                meta={"vertical_scroll_percent": 50})])
        p = Perceiver(desktop).perceive()
        self.assertIn("0|Button|Save|", p.ui_tree)
        self.assertIn("Pane|Document|v=50%", p.ui_tree)

    def test_no_scrollable_section_when_none(self) -> None:
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        p = Perceiver(desktop).perceive()
        self.assertNotIn("SCROLLABLE", p.ui_tree)


if __name__ == "__main__":
    unittest.main()
