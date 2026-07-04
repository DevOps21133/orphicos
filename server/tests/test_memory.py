"""Tests for the per-user memory store (server/memory.py).

The store is pointed at a temp file via ORPHIC_MEMORY_PATH before import, so tests
never touch server/memory.json. Everything under test is the real store code — no
fixtures needed; there is no LLM or network here.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="orphic-memory-test-")
os.environ["ORPHIC_MEMORY_PATH"] = str(Path(_TMP) / "memory.json")

from server import memory  # noqa: E402 - must follow the env override above

_MEMORY_FILE = Path(_TMP) / "memory.json"
USER = "user@example.com"
OTHER = "other@example.com"


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        # Pin the store to our temp file in setUp (not just at import): the module-level
        # _MEMORY_PATH is resolved once per process, and another test module may have
        # imported `memory` first — setting it here keeps us off the real store no matter
        # the run order.
        memory._MEMORY_PATH = _MEMORY_FILE
        Path(memory._MEMORY_PATH).unlink(missing_ok=True)
        memory._cache["mtime"] = None

    def test_add_stores_full_schema(self):
        item = memory.add(USER, "people", "my accountant", "Sarah Chen <sarah@firm.com>")
        self.assertEqual(set(item), {"id", "bucket", "key", "value", "source",
                                     "created_at", "last_used"})
        self.assertEqual(item["bucket"], "people")
        self.assertEqual(item["key"], "my accountant")
        self.assertEqual(item["value"], "Sarah Chen <sarah@firm.com>")
        self.assertEqual(item["source"], "explicit")
        self.assertEqual(memory.list_items(USER), [item])

    def test_same_bucket_and_key_updates_in_place_no_duplicate(self):
        first = memory.add(USER, "people", "My Accountant", "Sarah")
        second = memory.add(USER, "people", "my accountant", "Sarah Chen <sarah@firm.com>")
        items = memory.list_items(USER)
        self.assertEqual(len(items), 1)                 # one fact, corrected — never piled up
        self.assertEqual(second["id"], first["id"])     # same identity
        self.assertEqual(items[0]["value"], "Sarah Chen <sarah@firm.com>")

    def test_same_key_in_a_different_bucket_is_a_separate_item(self):
        memory.add(USER, "people", "the deck", "Jack Deck <jack@x.com>")
        memory.add(USER, "vocabulary", "the deck", "Q3-pitch.pptx")
        self.assertEqual(len(memory.list_items(USER)), 2)

    def test_invalid_input_is_rejected_not_stored(self):
        self.assertIsNone(memory.add(USER, "nonsense", "k", "v"))   # unknown bucket
        self.assertIsNone(memory.add(USER, "people", "", "v"))      # empty key
        self.assertIsNone(memory.add(USER, "people", "k", "  "))    # empty value
        self.assertEqual(memory.list_items(USER), [])

    def test_values_are_cleaned_and_length_capped(self):
        item = memory.add(USER, "preferences", "  email\n sign-off ", "Best,\n  Alex" + "x" * 5000)
        self.assertEqual(item["key"], "email sign-off")            # whitespace collapsed
        self.assertTrue(item["value"].startswith("Best, Alex"))    # newline collapsed to a space
        self.assertLessEqual(len(item["value"]), memory.MAX_VALUE_LEN)

    def test_per_user_cap(self):
        for i in range(memory.MAX_ITEMS_PER_USER):
            self.assertIsNotNone(memory.add(USER, "people", f"person {i}", f"v{i}"))
        self.assertIsNone(memory.add(USER, "people", "one too many", "v"))
        self.assertEqual(len(memory.list_items(USER)), memory.MAX_ITEMS_PER_USER)

    def test_list_items_returns_copies(self):
        memory.add(USER, "people", "k", "v")
        got = memory.list_items(USER)
        got[0]["value"] = "tampered"
        self.assertEqual(memory.list_items(USER)[0]["value"], "v")  # cache not mutated

    def test_update_existing_and_missing(self):
        item = memory.add(USER, "preferences", "default folder", "C:\\Old")
        self.assertTrue(memory.update(USER, item["id"], "C:\\Clients"))
        self.assertEqual(memory.list_items(USER)[0]["value"], "C:\\Clients")
        self.assertFalse(memory.update(USER, "nope", "x"))
        self.assertFalse(memory.update(USER, item["id"], "   "))     # empty edit rejected

    def test_delete_one(self):
        a = memory.add(USER, "people", "a", "1")
        memory.add(USER, "people", "b", "2")
        self.assertTrue(memory.delete(USER, a["id"]))
        self.assertEqual([it["key"] for it in memory.list_items(USER)], ["b"])
        self.assertFalse(memory.delete(USER, a["id"]))               # already gone

    def test_wipe_clears_only_that_user(self):
        memory.add(USER, "people", "a", "1")
        memory.add(USER, "preferences", "b", "2")
        memory.add(OTHER, "people", "c", "3")
        self.assertEqual(memory.wipe(USER), 2)
        self.assertEqual(memory.list_items(USER), [])
        self.assertEqual(len(memory.list_items(OTHER)), 1)           # other user untouched

    def test_persists_across_a_cache_reload(self):
        memory.add(USER, "people", "k", "v")
        memory._cache["mtime"] = None                                 # force a disk re-read
        self.assertEqual(memory.list_items(USER)[0]["key"], "k")


if __name__ == "__main__":
    unittest.main()
