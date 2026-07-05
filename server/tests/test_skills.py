"""Tests for the Skill Store layer: registry, entitlements, prompt injection,
skill-tag parsing, and the /command entitlement gate with its checkout upsell.

Everything is real except the LLM call boundary: brain.decide / the completion
call is patched with clearly-labeled TEST FIXTURES (CLAUDE.md Rule 14's
smoke/unit-test exception). Stores are pointed at a temp dir via
ORPHIC_*_PATH env vars before server modules import.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix="orphic-skills-test-")
os.environ["ORPHIC_USERS_PATH"] = str(Path(_TMP) / "users.json")
os.environ["ORPHIC_TOKENS_PATH"] = str(Path(_TMP) / "tokens.json")
os.environ["ORPHIC_ENTITLEMENTS_PATH"] = str(Path(_TMP) / "entitlements.json")

from fastapi.testclient import TestClient  # noqa: E402

from server import auth, brain, entitlements, skills  # noqa: E402
from server.app import app  # noqa: E402

# Another test module may have imported server.entitlements BEFORE our env var
# above was set (module paths bind at import). Force the temp path so this suite
# can never touch the real server/entitlements.json.
entitlements._ENTITLEMENTS_PATH = Path(os.environ["ORPHIC_ENTITLEMENTS_PATH"])
entitlements._cache["mtime"] = None

USER = "buyer@example.com"


def _decision(skill=None, actions=None):
    # TEST FIXTURE (Rule 14 exception): stands in for the LLM boundary only.
    return ({"actions": actions if actions is not None else
             [{"type": "click", "target_selector": "Compose", "coords": None, "value": None}],
             "done": True, "need_screenshot": False, "skill": skill,
             "reasoning_summary": "planned"},
            {"latency_ms": 1, "total_tokens": 1})


class RegistryTests(unittest.TestCase):
    def test_packs_are_complete_and_keyed_by_id(self):
        self.assertIn("gmail", skills.ALL)
        self.assertIn("excel", skills.ALL)
        for sid, pack in skills.ALL.items():
            self.assertEqual(sid, pack["id"])
            for key in ("title", "tagline", "checkout_path", "classify", "expertise"):
                self.assertTrue(pack[key], f"{sid} missing {key}")
            self.assertTrue(pack["checkout_path"].startswith("/skills/"))

    def test_expertise_never_names_a_provider(self):
        # Rule 2: pack text reaches prompts and (via upsell copy) users.
        for pack in skills.ALL.values():
            blob = " ".join(str(v) for v in pack.values()).lower()
            for name in ("deepseek", "nvidia", "z.ai", "glm", "openai"):
                self.assertNotIn(name, blob)


class EntitlementTests(unittest.TestCase):
    def setUp(self):
        Path(entitlements._ENTITLEMENTS_PATH).unlink(missing_ok=True)
        entitlements._cache["mtime"] = None

    def test_grant_revoke_roundtrip(self):
        self.assertEqual(entitlements.unlocked(USER), frozenset())
        entitlements.grant(USER, "gmail")
        entitlements.grant(USER, "gmail")  # idempotent
        self.assertEqual(entitlements.unlocked(USER), frozenset({"gmail"}))
        entitlements.grant(USER, "excel")
        self.assertEqual(entitlements.unlocked(USER), frozenset({"gmail", "excel"}))
        entitlements.revoke(USER, "gmail")
        self.assertEqual(entitlements.unlocked(USER), frozenset({"excel"}))

    def test_grant_rejects_unknown_skill(self):
        with self.assertRaises(ValueError):
            entitlements.grant(USER, "photoshop-not-built-yet")

    def test_persists_across_cache_reset(self):
        entitlements.grant(USER, "excel")
        entitlements._cache["mtime"] = None  # simulate a fresh process
        self.assertEqual(entitlements.unlocked(USER), frozenset({"excel"}))

    def test_feature_grant_revoke_roundtrip(self):
        # Features are tracked separately from skills (different threat model:
        # UX-gating only — see entitlements docstring). Default: nothing unlocked.
        self.assertEqual(entitlements.features(USER), frozenset())
        self.assertFalse(entitlements.has_feature(USER, "orphic_page_agent"))

        entitlements.grant_feature(USER, "orphic_page_agent")
        entitlements.grant_feature(USER, "orphic_page_agent")  # idempotent
        self.assertTrue(entitlements.has_feature(USER, "orphic_page_agent"))
        self.assertEqual(entitlements.features(USER), frozenset({"orphic_page_agent"}))

        # Skills and features don't bleed into each other's accessor.
        entitlements.grant(USER, "gmail")
        self.assertEqual(entitlements.unlocked(USER), frozenset({"gmail"}))
        self.assertEqual(entitlements.features(USER), frozenset({"orphic_page_agent"}))

        entitlements.revoke_feature(USER, "orphic_page_agent")
        self.assertFalse(entitlements.has_feature(USER, "orphic_page_agent"))

    def test_grant_feature_rejects_unknown_feature(self):
        with self.assertRaises(ValueError):
            entitlements.grant_feature(USER, "telepathy-not-built-yet")

    def test_feature_catalog_lists_orphic_page_agent(self):
        # The Base Premium perk must be in the registry for the shell to surface it.
        self.assertIn("orphic_page_agent", entitlements.FEATURES)
        meta = entitlements.FEATURES["orphic_page_agent"]
        self.assertEqual(meta["title"], "Orphic Page Agent")
        self.assertTrue(meta["checkout_path"])


class PromptInjectionTests(unittest.TestCase):
    def test_locked_pack_contributes_no_expertise(self):
        prompt = brain._system_prompt(frozenset())
        self.assertIn("- gmail [LOCKED]:", prompt)
        self.assertIn("- excel [LOCKED]:", prompt)
        # The recipes themselves must be absent — the paywall IS the prompt.
        self.assertNotIn("Compose", prompt)
        self.assertNotIn("alt+f1", prompt)

    def test_unlocked_pack_expertise_is_injected(self):
        prompt = brain._system_prompt(frozenset({"gmail"}))
        self.assertIn("- gmail [UNLOCKED]:", prompt)
        self.assertIn('the "Send" button', prompt)  # gmail recipe present
        self.assertNotIn("alt+f1", prompt)  # excel recipe still absent

    def test_parse_decision_validates_skill(self):
        good = brain._parse_decision('{"actions": [], "done": true, "skill": "gmail"}', False)
        self.assertEqual(good["skill"], "gmail")
        bad = brain._parse_decision('{"actions": [], "done": true, "skill": "made-up"}', False)
        self.assertIsNone(bad["skill"])
        absent = brain._parse_decision('{"actions": [], "done": true}', False)
        self.assertIsNone(absent["skill"])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        for p in (entitlements._ENTITLEMENTS_PATH, auth._TOKENS_PATH):
            Path(p).unlink(missing_ok=True)
        entitlements._cache["mtime"] = None
        auth._cache["mtime"] = None
        self.token = auth.issue_token(USER)

    def _command(self, text="do something"):
        return self.client.post("/command",
                                json={"command": text, "ui_tree": "a window"},
                                headers={"Authorization": f"Bearer {self.token}"})

    def test_base_command_passes_through(self):
        with patch("server.app.brain.decide", return_value=_decision(skill=None)):
            r = self._command()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["skill"])
        self.assertIsNone(body["locked_skill"])
        self.assertEqual(body["actions"][0]["type"], "click")

    def test_locked_skill_becomes_checkout_upsell(self):
        with patch("server.app.brain.decide", return_value=_decision(skill="gmail", actions=[])):
            r = self._command()
        body = r.json()
        self.assertEqual(body["locked_skill"], "gmail")
        self.assertTrue(body["done"])
        self.assertEqual(len(body["actions"]), 1)
        action = body["actions"][0]
        self.assertEqual(action["type"], "open_path")
        self.assertEqual(action["value"], "https://orphicos.app/skills/gmail")
        self.assertIn("Gmail", body["reasoning_summary"])
        # Warm, never scolding: no "locked"/"denied"/"can't" phrasing.
        self.assertNotIn("lock", body["reasoning_summary"].lower())

    def test_unlocked_skill_runs_and_reports_skill(self):
        entitlements.grant(USER, "gmail")
        fixture = _decision(skill="gmail")
        with patch("server.app.brain.decide", return_value=fixture) as decide:
            r = self._command()
        body = r.json()
        self.assertIsNone(body["locked_skill"])
        self.assertEqual(body["skill"], "gmail")
        self.assertEqual(body["actions"][0]["type"], "click")
        # The brain call must have received the entitlement set.
        self.assertEqual(decide.call_args.kwargs["unlocked_skills"], frozenset({"gmail"}))

    def test_store_base_env_overrides_checkout_host(self):
        with patch.dict(os.environ, {"ORPHIC_STORE_BASE": "https://store.test/"}), \
             patch("server.app.brain.decide", return_value=_decision(skill="excel")):
            r = self._command()
        self.assertEqual(r.json()["actions"][0]["value"], "https://store.test/skills/excel")

    def test_entitlements_requires_auth(self):
        r = self.client.get("/entitlements")
        self.assertEqual(r.status_code, 401)

    def test_entitlements_reports_features_and_catalog(self):
        # An entitled user: feature shows up in `features` and the catalog exposes
        # its checkout path so the shell can build the upgrade link.
        entitlements.grant_feature(USER, "orphic_page_agent")
        r = self.client.get("/entitlements",
                            headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("orphic_page_agent", body["features"])
        catalog_ids = [f["id"] for f in body["feature_catalog"]]
        self.assertIn("orphic_page_agent", catalog_ids)
        # The catalog must NOT leak internal-only keys (plan, granted_*_at) — only
        # the shape the shell renders from.
        feat = next(f for f in body["feature_catalog"] if f["id"] == "orphic_page_agent")
        self.assertEqual(set(feat), {"id", "title", "tagline", "checkout_path"})

    def test_entitlements_for_locked_user_lists_no_features(self):
        r = self.client.get("/entitlements",
                            headers={"Authorization": f"Bearer {self.token}"})
        body = r.json()
        self.assertEqual(body["features"], [])
        self.assertNotIn("orphic_page_agent", body["features"])
        # Catalog still lists the feature (for the upsell) even when locked.
        self.assertTrue(any(f["id"] == "orphic_page_agent" for f in body["feature_catalog"]))


if __name__ == "__main__":
    unittest.main()
