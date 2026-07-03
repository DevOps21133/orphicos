"""Unit tests for client.loop.run_command — the perceive->decide->act control flow.

Uses FakeDesktop + FakeBrain (no live desktop, no network). client.loop.sleep is
patched to a no-op so the inter-step settle doesn't slow the suite.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from client.loop import (_DECIDE_RETRIES, _EMPTY_TOLERANCE, _STUCK_REGATHER_LIMIT,
                         run_command)
from client.net import BrainError
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
        # active_window is the empty desktop, so "launch notepad" is a real launch
        # (not the already-open fresh-surface path — that is covered in test_actor).
        desktop = FakeDesktop(node_names=["Save"], active_window="Desktop")
        brain = FakeBrain([_decision([LAUNCH], done=True)])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 1)
        self.assertIn(("app", "launch", "notepad"), desktop.calls)

    def test_step_event_carries_latency_breakdown(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Untitled - Notepad")
        decision = _decision([LAUNCH], done=True)
        decision["timings"] = {"llm_ms": 900, "server_ms": 1000}
        brain = FakeBrain([decision])
        events = []
        self._run(desktop, brain, on_event=events.append)
        t = events[0]["timings"]
        self.assertIn("perceive_ms", t)
        self.assertIn("decide_ms", t)
        self.assertEqual(t["brain_ms"], 900)
        self.assertEqual(t["server_ms"], 1000)
        self.assertEqual(t["net_ms"], max(t["decide_ms"] - 1000, 0))

    def test_locked_skill_reaches_the_step_event(self):
        # A skill-store upsell decision: the shell needs locked_skill on the event
        # to render the step distinctly; plain decisions must NOT carry the key.
        desktop = FakeDesktop(node_names=["Save"], active_window="Desktop")
        upsell = _decision([WAIT0], done=True, summary="skill offer")
        upsell["locked_skill"] = "gmail"
        brain = FakeBrain([upsell])
        events = []
        self._run(desktop, brain, on_event=events.append)
        self.assertEqual(events[0]["locked_skill"], "gmail")

        brain = FakeBrain([_decision([WAIT0], done=True)])
        events = []
        self._run(desktop, brain, on_event=events.append)
        self.assertNotIn("locked_skill", events[0])

    def test_multi_step_until_done(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Book1 - Excel")
        brain = FakeBrain([
            _decision([LAUNCH], done=False),
            _decision([WAIT0], done=True),
        ])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 2)

    def test_repeated_empty_responses_stop(self):
        # A single empty response is tolerated; only after _EMPTY_TOLERANCE+1 in a row do we quit.
        desktop = FakeDesktop(node_names=["Save"], active_window="Desktop")
        brain = FakeBrain([_decision([], done=False)])  # always empty
        outcome = self._run(desktop, brain, max_steps=10)
        self.assertEqual(outcome, "no_actions")
        self.assertEqual(len(brain.seen), _EMPTY_TOLERANCE + 1)

    def test_transient_empty_response_is_tolerated(self):
        # One empty response mid-run must NOT abort; the next non-empty step proceeds.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([
            _decision([], done=False),       # transient empty response
            _decision([WAIT0], done=True),   # brain recovers
        ])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 2)

    def test_brain_error_stops_cleanly_after_retries(self):
        # A persistent BrainError is retried, then the run stops with "brain_error" — no crash.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([BrainError("brain down (502)")])  # every decide raises
        events = []
        outcome = self._run(desktop, brain, on_event=events.append)
        self.assertEqual(outcome, "brain_error")
        self.assertEqual(len(brain.seen), _DECIDE_RETRIES + 1)  # initial attempt + retries
        self.assertEqual(events[-1]["actions"], [])
        self.assertFalse(events[-1]["done"])

    def test_transient_brain_error_then_recovers(self):
        # A single BrainError is retried and the run continues once the brain answers.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([
            BrainError("transient 502"),
            _decision([WAIT0], done=True),
        ])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 2)  # failed attempt + successful retry

    def test_stale_control_error_aborts_batch_not_crash(self):
        # windows-use raising a live-COM error (a control went stale) must become a
        # FAILED action + re-plan, not crash the run.
        desktop = FakeDesktop(node_names=["Save"], active_window="App",
                              raise_on_coords=RuntimeError("UIA_E_ELEMENTNOTAVAILABLE"))
        brain = FakeBrain([
            _decision([{"type": "click", "target_selector": "Save"}], done=True),
            _decision([WAIT0], done=True),  # the re-plan after the failure
        ])
        events = []
        outcome = self._run(desktop, brain, on_event=events.append)
        self.assertEqual(outcome, "done")
        result_str = events[0]["actions"][0]["result"]
        self.assertTrue(result_str.startswith("FAILED"), result_str)
        self.assertFalse(events[0]["done"])  # a failed batch can never claim done

    def test_max_steps_reached(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Loop")
        # Clicks (not waits — those get waived) that never reach done -> budget runs out.
        brain = FakeBrain([_decision([{"type": "click", "target_selector": "Save"}],
                                     done=False)])
        outcome = self._run(desktop, brain, max_steps=3)
        self.assertEqual(outcome, "max_steps")
        self.assertEqual(len(brain.seen), 3)

    def test_pure_wait_steps_do_not_consume_step_budget(self):
        # Three pure-wait steps are waived, so the closing click still fits in a
        # 1-step budget — waiting out a slow operation can't starve the run.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([
            _decision([WAIT0], done=False),
            _decision([WAIT0], done=False),
            _decision([WAIT0], done=False),
            _decision([{"type": "click", "target_selector": "Save"}], done=True),
        ])
        outcome = self._run(desktop, brain, max_steps=1)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 4)

    def test_wait_waivers_are_limited(self):
        # A brain stuck emitting waits forever must still terminate: only the
        # first _WAIT_WAIVERS pure-wait steps are free.
        from client.loop import _WAIT_WAIVERS
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([WAIT0], done=False)])  # waits forever
        outcome = self._run(desktop, brain, max_steps=2)
        self.assertEqual(outcome, "max_steps")
        self.assertEqual(len(brain.seen), _WAIT_WAIVERS + 2)

    def test_action_error_triggers_single_replan_with_failure_state(self):
        # A target that resolves to nothing must FAIL the action, abort the rest of the
        # batch, and cause exactly ONE re-plan call whose state names the failed action.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([
            _decision([{"type": "click", "target_selector": "Ghost"},
                       {"type": "click", "target_selector": "Save"},
                       WAIT0], done=True),
            _decision([WAIT0], done=True),
        ])
        events = []
        outcome = self._run(desktop, brain, on_event=events.append)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 2)  # failed batch + exactly one re-plan
        # Remainder of the batch was aborted: only the failed action was attempted.
        self.assertEqual(len(events[0]["actions"]), 1)
        self.assertTrue(events[0]["actions"][0]["result"].startswith("FAILED"))
        self.assertNotIn(("click", (100, 200), "left", 1), desktop.calls)
        # The re-plan call carries the failure in state; the first call does not.
        self.assertNotIn("failed_action", brain.seen[0]["state"])
        failure = brain.seen[1]["state"]["failed_action"]
        self.assertEqual(failure["action"]["type"], "click")
        self.assertEqual(failure["action"]["target"], "Ghost")
        self.assertIn("Ghost", failure["error"])
        self.assertEqual(failure["plan_actions_dropped"], 2)
        # The failure is reported once, then cleared.
        self.assertEqual(len(brain.seen), 2)

    def test_batch_executes_in_order_without_extra_brain_calls(self):
        desktop = FakeDesktop(node_names=["Save", "Close"], active_window="App")
        brain = FakeBrain([_decision([
            {"type": "click", "target_selector": "Save"},
            {"type": "click", "target_selector": "Close"},
            WAIT0,
        ], done=True)])
        events = []
        outcome = self._run(desktop, brain, on_event=events.append)
        self.assertEqual(outcome, "done")
        self.assertEqual(len(brain.seen), 1)  # ONE round trip for the whole plan
        clicks = [c for c in desktop.calls if c[0] == "click"]
        self.assertEqual(clicks, [("click", (100, 200), "left", 1),
                                  ("click", (101, 201), "left", 1)])
        self.assertEqual(events[0]["timings"]["actions_executed"], 3)

    def test_kill_switch_interrupts_between_batch_actions(self):
        desktop = FakeDesktop(node_names=["Save", "Close"], active_window="App")
        brain = FakeBrain([_decision([
            {"type": "click", "target_selector": "Save"},
            {"type": "click", "target_selector": "Close"},
        ], done=True)])
        checks = {"n": 0}

        def stop_after_first_action():  # step check + action-1 check pass, then stop
            checks["n"] += 1
            return checks["n"] > 2

        outcome = self._run_with_hooks(desktop, brain, should_stop=stop_after_first_action)
        self.assertEqual(outcome, "stopped")
        clicks = [c for c in desktop.calls if c[0] == "click"]
        self.assertEqual(len(clicks), 1)  # first action ran, second was interrupted

    def test_approval_gate_scans_whole_batch_before_action_one(self):
        # A denied risky action LATER in the plan must prevent even the safe first
        # action from running — the gate pre-scans the entire batch.
        desktop = FakeDesktop(node_names=["Save", "Delete file"], active_window="App")
        brain = FakeBrain([_decision([
            {"type": "click", "target_selector": "Save"},
            {"type": "click", "target_selector": "Delete file"},
        ], done=True)])
        asked = []

        def deny_risky(action):
            asked.append(action)
            return "delete" not in str(action.get("target_selector") or "").lower()

        events = []
        outcome = self._run_with_hooks(desktop, brain, approve=deny_risky,
                                       on_event=events.append)
        self.assertEqual(outcome, "stopped")
        self.assertEqual(len(asked), 2)  # every batch action was inspected
        self.assertEqual([c for c in desktop.calls if c[0] == "click"], [])  # NOTHING ran
        self.assertEqual(events[0]["actions"][0]["result"], "SKIPPED: not approved")
        self.assertEqual(events[0]["timings"]["actions_executed"], 0)

    def test_screen_changing_action_refreshes_snapshot_mid_batch(self):
        # An element that only exists AFTER the batch's press must still resolve,
        # because the loop re-snapshots the desktop between batched actions.
        desktop = FakeDesktop(node_names=["Address bar"], active_window="App")
        real_get_state = desktop.get_state
        seen = {"n": 0}

        def refreshing_get_state():
            seen["n"] += 1
            if seen["n"] == 2:  # the intra-batch refresh (call 1 is the perceive)
                desktop.set_nodes(["Save"])
            return real_get_state()

        desktop.get_state = refreshing_get_state
        brain = FakeBrain([_decision([
            {"type": "press", "value": "ctrl+l"},
            {"type": "click", "target_selector": "Save"},
        ], done=True)])
        with patch("client.act.actor.foreground_console_label", return_value=None):
            outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertGreaterEqual(seen["n"], 2)
        self.assertIn(("click", (100, 200), "left", 1), desktop.calls)

    def test_scroll_refreshes_snapshot_mid_batch(self):
        # An element revealed BY the batch's scroll must resolve: scroll is a
        # screen-changing action, so the loop re-snapshots before the next action.
        desktop = FakeDesktop(node_names=["Address bar"], active_window="App")
        real_get_state = desktop.get_state
        seen = {"n": 0}

        def refreshing_get_state():
            seen["n"] += 1
            if seen["n"] == 2:  # the intra-batch refresh (call 1 is the perceive)
                desktop.set_nodes(["Accept"])
            return real_get_state()

        desktop.get_state = refreshing_get_state
        brain = FakeBrain([_decision([
            {"type": "scroll", "value": "down"},
            {"type": "click", "target_selector": "Accept"},
        ], done=True)])
        outcome = self._run(desktop, brain)
        self.assertEqual(outcome, "done")
        self.assertIn(("click", (100, 200), "left", 1), desktop.calls)

    def test_regathering_already_read_data_stops_the_run(self):
        # The horror case: the brain loses its progress (a filled spreadsheet is a
        # canvas it can't see in the tree) and restarts the task, re-listing/re-reading
        # forever. The loop guard must stop it as "stuck" instead of looping to the
        # step limit and re-typing over the sheet.
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.pdf").write_text("x", encoding="utf-8")
            desktop = FakeDesktop(node_names=[], active_window="Calc")
            brain = FakeBrain([_decision([{"type": "list_dir", "value": td}], done=False)])
            events = []
            outcome = self._run(desktop, brain, max_steps=8, on_event=events.append)
        self.assertEqual(outcome, "stuck")               # stopped, not looped to max_steps
        # One free gather (step 1) + _STUCK_REGATHER_LIMIT redundant re-gathers, then stop.
        self.assertEqual(len(brain.seen), _STUCK_REGATHER_LIMIT + 1)
        self.assertEqual(events[-1]["actions"], [])
        self.assertIn("repeating", events[-1]["reasoning"].lower())

    def test_distinct_gathers_do_not_trip_the_guard(self):
        # Reading DIFFERENT files/folders is normal progress and must never be mistaken
        # for a loop, no matter how many — only RE-reading already-gathered data counts.
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            desktop = FakeDesktop(node_names=[], active_window="App")
            brain = FakeBrain([
                _decision([{"type": "list_dir", "value": a}], done=False),
                _decision([{"type": "list_dir", "value": b}], done=True),
            ])
            outcome = self._run(desktop, brain, max_steps=8)
        self.assertEqual(outcome, "done")

    def _run_with_hooks(self, desktop, brain, should_stop=None, approve=None,
                        on_event=lambda e: None):
        return run_command("do a thing", desktop, brain, 5, on_event, should_stop, approve)


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

    def test_chrome_only_tree_triggers_vision(self):
        # A canvas app exposing only its titlebar buttons is unreadable: fallback fires.
        desktop = FakeDesktop(node_names=["Minimize", "Maximize", "Close"],
                              active_window="Game")
        brain = FakeBrain([_decision([WAIT0], done=True)])
        run_command("cmd", desktop, brain, 5, lambda e: None)
        self.assertIsNotNone(brain.seen[0]["screenshot"])

    def test_brain_requested_screenshot_arrives_on_next_call(self):
        # need_screenshot=true in a decision makes the NEXT request carry a shot,
        # and only that one — the flag does not stick.
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        first = _decision([WAIT0], done=False)
        first["need_screenshot"] = True
        brain = FakeBrain([first, _decision([WAIT0], done=False),
                           _decision([], done=True)])
        run_command("cmd", desktop, brain, 5, lambda e: None)
        self.assertIsNone(brain.seen[0]["screenshot"])
        self.assertIsNotNone(brain.seen[1]["screenshot"])
        self.assertIsNone(brain.seen[2]["screenshot"])

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
