"""Unit tests for client.loop.run_command — the perceive->decide->act control flow.

Uses FakeDesktop + FakeBrain (no live desktop, no network). client.loop.sleep is
patched to a no-op so the inter-step settle doesn't slow the suite.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from client.loop import run_command
from client.tests.fakes import FakeBrain, FakeDesktop

LAUNCH = {"type": "launch", "value": "notepad"}
WAIT0 = {"type": "wait", "value": "0"}


def _decision(actions, done, summary="step"):
    return {"actions": actions, "done": done, "reasoning_summary": summary}


class ControlFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._sleep_patch = patch("client.loop.sleep", lambda *_a, **_k: None)
        self._sleep_patch.start()
        self.addCleanup(self._sleep_patch.stop)

    def _run(self, desktop, brain, max_steps=5, on_event=lambda e: None):
        return run_command("do a thing", desktop, brain, max_steps, on_event)

    def test_done_on_first_step(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Untitled - Notepad")
        brain = FakeBrain([_decision([LAUNCH], done=True)])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 1)
        self.assertIn(("app", "launch", "notepad"), desktop.calls)

    def test_multi_step_until_done(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Book1 - Excel")
        brain = FakeBrain([
            _decision([LAUNCH], done=False),
            _decision([WAIT0], done=True),
        ])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 2)

    def test_no_actions_stops(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Desktop")
        brain = FakeBrain([_decision([], done=False)])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "no_actions")
        self.assertEqual(len(brain.seen), 1)

    def test_max_steps_reached(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Loop")
        brain = FakeBrain([_decision([WAIT0], done=False)])  # never done -> repeats
        outcome = self._run(desktop, brain, max_steps=3)
        self.assertEqual(outcome, "max_steps")
        self.assertEqual(len(brain.seen), 3)

    def test_action_error_is_caught_and_loop_continues(self):
        # A target that resolves to nothing must be SKIPPED, not crash the loop.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([{"type": "click", "target_selector": "Ghost"}], done=True)])
        events = []
        outcome = self._run(desktop, brain, on_event=events.append)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(events), 1)
        result_str = events[0]["actions"][0]["result"]
        self.assertTrue(result_str.startswith("SKIPPED"), result_str)


class PerceptionAndStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._sleep_patch = patch("client.loop.sleep", lambda *_a, **_k: None)
        self._sleep_patch.start()
        self.addCleanup(self._sleep_patch.stop)

    def test_screenshot_sent_only_when_tree_empty(self):
        # Empty tree (no interactive nodes / status False) -> vision fallback fires.
        empty = FakeDesktop(node_names=[], tree_status=False, active_window=None)
        brain = FakeBrain([_decision([WAIT0], done=True)])
        run_command("cmd", empty, brain, 5, lambda e: None)
        self.assertIsNotNone(brain.seen[0]["screenshot"])

    def test_no_screenshot_when_tree_present(self):
        full = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([WAIT0], done=True)])
        run_command("cmd", full, brain, 5, lambda e: None)
        self.assertIsNone(brain.seen[0]["screenshot"])

    def test_event_shape(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([WAIT0], done=True, summary="did it")])
        events = []
        run_command("cmd", desktop, brain, 5, events.append)
        e = events[0]
        self.assertEqual(e["step"], 1)
        self.assertEqual(e["reasoning"], "did it")
        self.assertFalse(e["used_vision"])
        self.assertTrue(e["done"])
        self.assertEqual(len(e["actions"]), 1)

    def test_state_history_is_capped_at_five(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([WAIT0], done=False)])  # never done
        run_command("cmd", desktop, brain, 7, lambda e: None)
        # 7th call sees history of the prior 6 steps, truncated to the last 5.
        self.assertEqual(len(brain.seen[-1]["state"]["steps"]), 5)
        # First call has no prior history.
        self.assertEqual(len(brain.seen[0]["state"]["steps"]), 0)


if __name__ == "__main__":
    unittest.main()
