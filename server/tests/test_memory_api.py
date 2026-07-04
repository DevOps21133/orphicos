"""End-to-end tests for the memory layer through the real API: a "remember …"
command persists, /memory reflects it, edit/delete/wipe work, and incognito saves
nothing. Stores point at a temp dir; only the LLM boundary (brain.decide) is a
labeled TEST FIXTURE (CLAUDE.md Rule 14) — the app wiring and store are real.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix="orphic-memapi-test-")
os.environ["ORPHIC_USERS_PATH"] = str(Path(_TMP) / "users.json")
os.environ["ORPHIC_TOKENS_PATH"] = str(Path(_TMP) / "tokens.json")
os.environ["ORPHIC_MEMORY_PATH"] = str(Path(_TMP) / "memory.json")

from fastapi.testclient import TestClient  # noqa: E402

from server import accounts, auth, brain, memory  # noqa: E402
from server.app import app  # noqa: E402

_MEMORY_FILE = Path(_TMP) / "memory.json"
EMAIL = "owner@example.com"
PASSWORD = "correct-horse-9"


def _decision(remember=None, reasoning="Noted."):
    # TEST FIXTURE (Rule 14 exception): a remember-only decision (no desktop actions).
    return ({"actions": [], "done": True, "need_screenshot": False, "skill": None,
             "reasoning_summary": reasoning, "remember": remember or []},
            {"latency_ms": 1, "total_tokens": 1})


class MemoryApiTests(unittest.TestCase):
    def setUp(self):
        memory._MEMORY_PATH = _MEMORY_FILE
        for p in (accounts._USERS_PATH, auth._TOKENS_PATH, memory._MEMORY_PATH):
            Path(p).unlink(missing_ok=True)
        for mod in (accounts, auth, memory):
            mod._cache["mtime"] = None
        accounts._fails.clear()
        self.client = TestClient(app)
        r = self.client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        self.auth = {"Authorization": f"Bearer {r.json()['token']}"}

    def _command(self, text, decision, incognito=False):
        with patch.object(brain, "decide", return_value=decision):
            return self.client.post("/command",
                                    json={"command": text, "ui_tree": "", "incognito": incognito},
                                    headers=self.auth)

    def test_remember_command_persists_and_is_returned(self):
        fact = {"bucket": "people", "key": "my accountant", "value": "Sarah <s@x.com>"}
        r = self._command("remember my accountant is Sarah", _decision([fact]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["remembered"]), 1)
        self.assertEqual(r.json()["remembered"][0]["value"], "Sarah <s@x.com>")
        # ...and it shows up on the view endpoint with a full schema + id.
        got = self.client.get("/memory", headers=self.auth).json()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["bucket"], "people")
        self.assertIn("id", got[0])

    def test_incognito_saves_nothing_and_says_so(self):
        fact = {"bucket": "people", "key": "my accountant", "value": "Sarah <s@x.com>"}
        r = self._command("remember my accountant is Sarah", _decision([fact]), incognito=True)
        self.assertEqual(r.json()["remembered"], [])
        self.assertIn("Incognito", r.json()["reasoning_summary"])
        self.assertEqual(self.client.get("/memory", headers=self.auth).json(), [])

    def test_edit_and_delete_one(self):
        fact = {"bucket": "preferences", "key": "default folder", "value": "C:\\Old"}
        self._command("remember my folder", _decision([fact]))
        item_id = self.client.get("/memory", headers=self.auth).json()[0]["id"]

        r = self.client.put(f"/memory/{item_id}", json={"value": "C:\\Clients"}, headers=self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/memory", headers=self.auth).json()[0]["value"], "C:\\Clients")

        r = self.client.delete(f"/memory/{item_id}", headers=self.auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/memory", headers=self.auth).json(), [])

    def test_edit_and_delete_missing_are_404(self):
        self.assertEqual(self.client.put("/memory/nope", json={"value": "x"}, headers=self.auth).status_code, 404)
        self.assertEqual(self.client.delete("/memory/nope", headers=self.auth).status_code, 404)

    def test_wipe_forgets_everything(self):
        self._command("a", _decision([{"bucket": "people", "key": "a", "value": "1"}]))
        self._command("b", _decision([{"bucket": "preferences", "key": "b", "value": "2"}]))
        r = self.client.delete("/memory", headers=self.auth)
        self.assertEqual(r.json()["removed"], 2)
        self.assertEqual(self.client.get("/memory", headers=self.auth).json(), [])

    def test_memory_endpoints_require_auth(self):
        self.assertEqual(self.client.get("/memory").status_code, 401)
        self.assertEqual(self.client.delete("/memory").status_code, 401)

    def test_saved_memory_is_passed_into_the_next_decision(self):
        fact = {"bucket": "people", "key": "my accountant", "value": "Sarah <s@x.com>"}
        self._command("remember my accountant", _decision([fact]))
        # Next command: the stored fact must be handed to the brain as user_memory.
        with patch.object(brain, "decide", return_value=_decision()) as spy:
            self.client.post("/command", json={"command": "email my accountant", "ui_tree": ""},
                             headers=self.auth)
        passed = spy.call_args.kwargs["user_memory"]
        self.assertEqual(passed[0]["key"], "my accountant")


if __name__ == "__main__":
    unittest.main()
