"""Tests for OrphicOS sign-in (register/login) and its wiring into /command auth.

Everything is real except the LLM call boundary: brain.decide is patched with a
clearly-labeled TEST FIXTURE (CLAUDE.md Rule 14's smoke/unit-test exception) so
no network or provider is touched. User/token stores are pointed at a temp dir
via ORPHIC_USERS_PATH / ORPHIC_TOKENS_PATH before server modules import — tests
never write into server/.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix="orphic-signin-test-")
os.environ["ORPHIC_USERS_PATH"] = str(Path(_TMP) / "users.json")
os.environ["ORPHIC_TOKENS_PATH"] = str(Path(_TMP) / "tokens.json")

from fastapi.testclient import TestClient  # noqa: E402

from server import accounts, auth  # noqa: E402
from server.app import app  # noqa: E402

# TEST FIXTURE (Rule 14 exception): stands in for the LLM boundary only.
FAKE_DECISION = ({"actions": [{"type": "click", "target_selector": "Save"}],
                  "done": True, "reasoning_summary": "clicked Save"},
                 {"latency_ms": 1, "total_tokens": 1})

EMAIL = "user@example.com"
PASSWORD = "correct-horse-9"


class SignInTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Fresh stores + lockout state per test.
        for p in (accounts._USERS_PATH, auth._TOKENS_PATH):
            Path(p).unlink(missing_ok=True)
        accounts._cache["mtime"] = None
        auth._cache["mtime"] = None
        accounts._fails.clear()

    def _register(self, email=EMAIL, password=PASSWORD):
        return self.client.post("/auth/register", json={"email": email, "password": password})

    def test_register_returns_token_and_normalizes_email(self):
        r = self._register(email="  User@Example.COM ")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertTrue(body["token"].startswith("orphic_"))
        self.assertEqual(body["user_id"], EMAIL)

    def test_register_duplicate_is_409(self):
        self._register()
        r = self._register(password="another-pass-1")
        self.assertEqual(r.status_code, 409)

    def test_register_rejects_bad_inputs(self):
        self.assertEqual(self._register(email="not-an-email").status_code, 422)
        self.assertEqual(self._register(password="short").status_code, 422)

    def test_login_returns_same_token(self):
        token = self._register().json()["token"]
        r = self.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["token"], token)

    def test_login_wrong_password_is_401(self):
        self._register()
        r = self.client.post("/auth/login", json={"email": EMAIL, "password": "wrong-password"})
        self.assertEqual(r.status_code, 401)

    def test_login_unknown_email_is_401(self):
        r = self.client.post("/auth/login", json={"email": "nobody@example.com",
                                                  "password": PASSWORD})
        self.assertEqual(r.status_code, 401)

    def test_lockout_after_repeated_failures(self):
        self._register()
        for _ in range(accounts.MAX_FAILS):
            r = self.client.post("/auth/login", json={"email": EMAIL, "password": "wrong-pw-x"})
            self.assertEqual(r.status_code, 401)
        # Even the CORRECT password is refused while locked out.
        r = self.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(r.status_code, 429)
        # After the window passes, login works again.
        accounts._fails[EMAIL]["locked_until"] = 0.0
        r = self.client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        self.assertEqual(r.status_code, 200)

    def test_registered_token_works_on_command(self):
        token = self._register().json()["token"]
        with patch("server.app.brain.decide", return_value=FAKE_DECISION):
            r = self.client.post("/command",
                                 json={"command": "click save", "ui_tree": "Button 'Save'"},
                                 headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["actions"][0]["target_selector"], "Save")

    def test_command_rejects_bad_token(self):
        r = self.client.post("/command", json={"command": "x"},
                             headers={"Authorization": "Bearer orphic_bogus"})
        self.assertEqual(r.status_code, 401)

    def test_users_file_stores_hash_not_password(self):
        self._register()
        raw = accounts._USERS_PATH.read_text(encoding="utf-8")
        self.assertNotIn(PASSWORD, raw)
        self.assertIn("pbkdf2_sha256", raw)

    def test_cli_issue_still_works(self):
        token = auth.issue_token("ops-user")
        self.assertEqual(auth.validate_token(token), "ops-user")


if __name__ == "__main__":
    unittest.main()
