"""Transport-level tests for BrainClient: the incognito flag rides every /command,
and the memory methods hit the right verbs/paths and relay errors. Uses an httpx
MockTransport (CLAUDE.md Rule 14) — no network, no server, no LLM.
"""
from __future__ import annotations

import json
import unittest

import httpx

from client.net.client import BrainClient, BrainError


def _make(handler) -> BrainClient:
    brain = BrainClient("http://test", "tok")
    # Swap the internal client for one backed by the mock, keeping the auth header.
    brain._client = httpx.Client(base_url="http://test",
                                 headers={"Authorization": "Bearer tok"},
                                 transport=httpx.MockTransport(handler))
    return brain


class BrainClientTests(unittest.TestCase):
    def setUp(self):
        self.calls: list[tuple] = []

    def _handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        path, method = request.url.path, request.method
        if method == "POST" and path == "/command":
            return httpx.Response(200, json={
                "actions": [], "done": True, "reasoning_summary": "ok",
                "echo_incognito": body.get("incognito"), "remembered": []})
        if method == "GET" and path == "/memory":
            return httpx.Response(200, json=[{"id": "a1", "bucket": "people",
                                              "key": "k", "value": "v"}])
        if path == "/memory/a1" and method in ("PUT", "DELETE"):
            return httpx.Response(200, json={"ok": True})
        if method == "DELETE" and path == "/memory":
            return httpx.Response(200, json={"ok": True, "removed": 3})
        if path == "/memory/missing":
            return httpx.Response(404, json={"detail": "gone"})
        return httpx.Response(500)

    def test_command_carries_incognito_false_by_default(self):
        brain = _make(self._handler)
        d = brain.decide("do it", "a tree")
        self.assertIs(d["echo_incognito"], False)

    def test_set_incognito_makes_command_carry_true(self):
        brain = _make(self._handler)
        brain.set_incognito(True)
        d = brain.decide("do it", "a tree")
        self.assertIs(d["echo_incognito"], True)

    def test_list_memory_returns_items(self):
        brain = _make(self._handler)
        items = brain.list_memory()
        self.assertEqual(items[0]["key"], "k")
        self.assertEqual(self.calls[-1][:2], ("GET", "/memory"))

    def test_edit_memory_puts_the_value(self):
        brain = _make(self._handler)
        brain.edit_memory("a1", "new value")
        self.assertEqual(self.calls[-1], ("PUT", "/memory/a1", {"value": "new value"}))

    def test_delete_memory_deletes_one(self):
        brain = _make(self._handler)
        brain.delete_memory("a1")
        self.assertEqual(self.calls[-1][:2], ("DELETE", "/memory/a1"))

    def test_wipe_memory_returns_count(self):
        brain = _make(self._handler)
        self.assertEqual(brain.wipe_memory(), 3)

    def test_missing_item_raises_brain_error(self):
        brain = _make(self._handler)
        with self.assertRaises(BrainError):
            brain.edit_memory("missing", "x")


if __name__ == "__main__":
    unittest.main()
