"""Unit + integration tests for the OrphicOS shell (Phase 5).

Everything here runs headless with FakeDesktop + FakeBrain (CLAUDE.md Rule 14): no live
desktop, no network, no LLM. Covers the risk-verb gate, the new loop stop/approve hooks,
the RunSession approval handshake, and the full WebSocket run path through create_app().
client.loop.sleep is patched to a no-op so the inter-step settle doesn't slow the suite.
"""
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from client.loop import run_command
from client.shell import gate
from client.shell.app import create_app
from client.shell.runner import RunSession
from client.tests.fakes import FakeBrain, FakeDesktop

LAUNCH = {"type": "launch", "value": "notepad"}
WAIT0 = {"type": "wait", "value": "0"}
RISKY_PRESS = {"type": "press", "value": "delete"}


def _decision(actions, done, summary="step"):
    return {"actions": actions, "done": done, "reasoning_summary": summary}


class GateTests(unittest.TestCase):
    def test_command_flags_each_risk_verb_once(self):
        verbs = gate.command_has_risk("delete the file then delete the folder and send it")
        self.assertEqual(sorted(verbs), ["delete", "send"])

    def test_command_with_no_risk_is_empty(self):
        self.assertEqual(gate.command_has_risk("open notepad and type hello"), [])

    def test_word_boundary_avoids_false_positives(self):
        # "removable" / "information" must NOT trip "remove" / "format".
        self.assertEqual(gate.command_has_risk("show removable drive information"), [])

    def test_action_risk_in_target(self):
        self.assertEqual(gate.action_needs_approval({"type": "click", "target_selector": "Delete"}), "delete")

    def test_action_risk_in_pressed_key(self):
        self.assertEqual(gate.action_needs_approval(RISKY_PRESS), "delete")

    def test_del_key_abbreviation_is_risky(self):
        # The Del key deletes but carries no spelled-out verb; both bare and combined.
        self.assertEqual(gate.action_needs_approval({"type": "press", "value": "del"}), "delete")
        self.assertEqual(gate.action_needs_approval({"type": "press", "value": "shift+del"}), "delete")

    def test_ctrl_enter_chord_is_risky_send(self):
        self.assertEqual(gate.action_needs_approval({"type": "press", "value": "ctrl+enter"}), "send")

    def test_typing_the_letters_del_is_not_risky(self):
        # Typing d-e-l into a document is not a delete; only key-press actions count.
        self.assertIsNone(gate.action_needs_approval({"type": "type", "value": "del"}))

    def test_benign_chords_need_no_approval(self):
        self.assertIsNone(gate.action_needs_approval({"type": "press", "value": "ctrl+s"}))
        self.assertIsNone(gate.action_needs_approval({"type": "press", "value": "enter"}))

    def test_safe_action_needs_no_approval(self):
        self.assertIsNone(gate.action_needs_approval({"type": "type", "value": "the machine works"}))


class LoopHookTests(unittest.TestCase):
    """The optional should_stop / approve hooks added to run_command for the shell."""

    def setUp(self) -> None:
        p = patch("client.loop.sleep", lambda *_a, **_k: None)
        p.start()
        self.addCleanup(p.stop)

    def test_stop_before_first_step_does_nothing(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([LAUNCH], done=True)])
        outcome = run_command("cmd", desktop, brain, 5, lambda e: None,
                              should_stop=lambda: True)
        self.assertEqual(outcome, "stopped")
        self.assertEqual(brain.seen, [])          # never even perceived/decided
        self.assertEqual(desktop.calls, [])

    def test_stop_between_actions_halts_mid_step(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([LAUNCH, WAIT0], done=True)])
        seq = {"n": 0}

        def should_stop():  # top-of-step (F), before a1 (F), before a2 (T)
            seq["n"] += 1
            return seq["n"] >= 3

        events = []
        outcome = run_command("cmd", desktop, brain, 5, events.append, should_stop=should_stop)
        self.assertEqual(outcome, "stopped")
        self.assertEqual(len(events[0]["actions"]), 1)   # only the first action ran
        self.assertFalse(events[0]["done"])              # a stopped step is never "done"

    def test_approve_denied_skips_action_and_stops(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([RISKY_PRESS], done=True)])
        events = []
        outcome = run_command("cmd", desktop, brain, 5, events.append,
                              approve=lambda a: False)
        self.assertEqual(outcome, "stopped")
        self.assertEqual(events[0]["actions"][0]["result"], "SKIPPED: not approved")
        self.assertEqual(desktop.calls, [])              # the risky key was never pressed

    def test_approve_allowed_action_runs(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([LAUNCH], done=True)])
        outcome = run_command("cmd", desktop, brain, 5, lambda e: None,
                              approve=lambda a: True)
        self.assertEqual(outcome, "done")
        self.assertIn(("app", "launch", "notepad"), desktop.calls)


class ApprovalHandshakeTests(unittest.TestCase):
    """RunSession.approve blocks the worker until a decision (or stop) arrives."""

    def _call_approve_async(self, session, action):
        result: dict = {}
        t = threading.Thread(target=lambda: result.__setitem__("v", session.approve(action)))
        t.start()
        return t, result

    def _wait_for_pending(self, emits):
        for _ in range(200):
            if emits and emits[-1].get("type") == "approval_required":
                return emits[-1]["id"]
            time.sleep(0.005)
        self.fail("no approval_required event was emitted")

    def test_safe_action_approved_without_prompt(self):
        emits = []
        session = RunSession("cmd", emits.append)
        self.assertTrue(session.approve({"type": "type", "value": "hi"}))
        self.assertEqual(emits, [])               # no human prompt for a safe action

    def test_risky_action_approved(self):
        emits = []
        session = RunSession("cmd", emits.append)
        t, result = self._call_approve_async(session, RISKY_PRESS)
        rid = self._wait_for_pending(emits)
        session.resolve_approval(rid, True)
        t.join(timeout=2)
        self.assertTrue(result["v"])

    def test_risky_action_denied(self):
        emits = []
        session = RunSession("cmd", emits.append)
        t, result = self._call_approve_async(session, RISKY_PRESS)
        rid = self._wait_for_pending(emits)
        session.resolve_approval(rid, False)
        t.join(timeout=2)
        self.assertFalse(result["v"])

    def test_stop_unblocks_pending_approval_as_denial(self):
        emits = []
        session = RunSession("cmd", emits.append)
        t, result = self._call_approve_async(session, RISKY_PRESS)
        self._wait_for_pending(emits)
        session.stop()                            # kill switch while waiting -> deny
        t.join(timeout=2)
        self.assertFalse(result["v"])


def _fake_submitter(desktop, brain, max_steps=5):
    """Runs a session on a worker thread with fakes — the shell's DesktopWorker stand-in."""
    def submit(session, on_done):
        def worker():
            on_done(session.run(desktop, brain, max_steps))
        threading.Thread(target=worker, daemon=True).start()
    return submit


class ShellAppTests(unittest.TestCase):
    def setUp(self) -> None:
        p = patch("client.loop.sleep", lambda *_a, **_k: None)
        p.start()
        self.addCleanup(p.stop)

    def test_index_serves_the_shell(self):
        app = create_app(submit=lambda s, d: None, health_check=lambda: True)
        with TestClient(app) as client:
            r = client.get("/")
            self.assertEqual(r.status_code, 200)
            self.assertIn("OrphicOS", r.text)
            self.assertIn("What should the machine do?", r.text)

    def test_status_reflects_health(self):
        app_up = create_app(submit=lambda s, d: None, health_check=lambda: True,
                            server_base="http://localhost:8000")
        with TestClient(app_up) as client:
            body = client.get("/api/status").json()
            self.assertTrue(body["connected"])
            self.assertEqual(body["server_base"], "http://localhost:8000")
            self.assertFalse(body["running"])

        app_down = create_app(submit=lambda s, d: None, health_check=lambda: False)
        with TestClient(app_down) as client:
            self.assertFalse(client.get("/api/status").json()["connected"])

    def test_ws_streams_a_run_to_completion(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="Untitled - Notepad")
        brain = FakeBrain([_decision([LAUNCH], done=True)])
        app = create_app(submit=_fake_submitter(desktop, brain), health_check=lambda: True)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "run", "command": "open notepad"})
                types = []
                for _ in range(12):
                    ev = ws.receive_json()
                    types.append(ev["type"])
                    if ev["type"] == "run_finished":
                        self.assertEqual(ev["outcome"], "done")
                        break
                self.assertEqual(types[0], "run_started")
                self.assertIn("step", types)
                self.assertEqual(types[-1], "run_finished")

    def test_ws_flags_risky_command(self):
        desktop = FakeDesktop(node_names=["Save"], active_window="App")
        brain = FakeBrain([_decision([WAIT0], done=True)])
        app = create_app(submit=_fake_submitter(desktop, brain), health_check=lambda: True)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "run", "command": "delete the old backup"})
                started = ws.receive_json()
                self.assertEqual(started["type"], "run_started")
                self.assertEqual(started["flagged"], ["delete"])

    def test_ws_rejects_empty_command(self):
        app = create_app(submit=lambda s, d: None, health_check=lambda: True)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "run", "command": "   "})
                ev = ws.receive_json()
                self.assertEqual(ev["type"], "error")

    def test_ws_rejects_second_concurrent_run(self):
        # A submitter that never completes keeps hub.active set, so a second run is refused.
        submitted = []
        app = create_app(submit=lambda s, d: submitted.append(s), health_check=lambda: True)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "run", "command": "first"})
                self.assertEqual(ws.receive_json()["type"], "run_started")
                ws.send_json({"type": "run", "command": "second"})
                ev = ws.receive_json()
                self.assertEqual(ev["type"], "error")
                self.assertIn("already running", ev["message"])
        self.assertEqual(len(submitted), 1)

    def test_ws_rejects_cross_origin_handshake(self):
        # CSWSH defense: a socket from a foreign origin must be refused before it can drive.
        app = create_app(submit=lambda s, d: None, health_check=lambda: True,
                         allowed_origins={"http://127.0.0.1:8700"})
        with TestClient(app) as client:
            with self.assertRaises(Exception):  # handshake closed with policy-violation 1008
                with client.websocket_connect("/ws", headers={"origin": "http://evil.example"}):
                    pass
            # The shell's own origin still connects.
            with client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:8700"}) as ws:
                ws.send_json({"type": "run", "command": "   "})
                self.assertEqual(ws.receive_json()["type"], "error")

    def test_validation_error_reaches_only_the_requesting_tab(self):
        # Two tabs open; a second tab's "already running" error must NOT reset tab one.
        submitted = []
        app = create_app(submit=lambda s, d: submitted.append(s), health_check=lambda: True)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
                ws1.send_json({"type": "run", "command": "first"})
                self.assertEqual(ws1.receive_json()["type"], "run_started")  # broadcast
                self.assertEqual(ws2.receive_json()["type"], "run_started")  # broadcast
                ws2.send_json({"type": "run", "command": "second"})
                self.assertEqual(ws2.receive_json()["type"], "error")        # sender only
                # Tab one's next event is its own stop's status — proving the error skipped it.
                ws1.send_json({"type": "stop"})
                ev = ws1.receive_json()
                self.assertEqual(ev["type"], "status")


class FakeVoice:
    """Test fixture: a VoiceController stand-in (duck-typed .toggle / .HOTKEY)."""

    HOTKEY = "Ctrl+Alt+V"

    def __init__(self) -> None:
        self.toggles = 0
        self.emit = lambda e: None  # bound to hub.emit by the test, like __main__ does

    def toggle(self) -> None:
        self.toggles += 1
        if self.toggles % 2:
            self.emit({"type": "voice", "state": "recording"})
        else:
            self.emit({"type": "transcript", "text": "open notepad"})
            self.emit({"type": "voice", "state": "idle"})


class VoiceShellTests(unittest.TestCase):
    """The Phase 3 voice front door as seen by the shell (mic message + events)."""

    def test_status_reports_voice_and_hotkey(self):
        app = create_app(submit=lambda s, d: None, health_check=lambda: True,
                         voice=FakeVoice())
        with TestClient(app) as client:
            body = client.get("/api/status").json()
            self.assertTrue(body["voice"])
            self.assertEqual(body["voice_hotkey"], "Ctrl+Alt+V")

    def test_status_without_voice(self):
        app = create_app(submit=lambda s, d: None, health_check=lambda: True)
        with TestClient(app) as client:
            body = client.get("/api/status").json()
            self.assertFalse(body["voice"])
            self.assertIsNone(body["voice_hotkey"])

    def test_mic_without_voice_is_a_clean_error(self):
        app = create_app(submit=lambda s, d: None, health_check=lambda: True)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "mic"})
                ev = ws.receive_json()
                self.assertEqual(ev["type"], "error")
                self.assertIn("Voice input", ev["message"])

    def test_mic_toggles_and_transcript_reaches_the_browser_without_a_run(self):
        voice = FakeVoice()
        submitted = []
        app = create_app(submit=lambda s, d: submitted.append(s),
                         health_check=lambda: True, voice=voice)
        with TestClient(app) as client:
            voice.emit = app.state.hub.emit  # as __main__ binds the real controller
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "mic"})
                self.assertEqual(ws.receive_json(),
                                 {"type": "voice", "state": "recording"})
                ws.send_json({"type": "mic"})
                self.assertEqual(ws.receive_json(),
                                 {"type": "transcript", "text": "open notepad"})
                self.assertEqual(ws.receive_json(),
                                 {"type": "voice", "state": "idle"})
        self.assertEqual(voice.toggles, 2)
        # CONFIRM GATE: a transcript must never start a run by itself.
        self.assertEqual(submitted, [])


if __name__ == "__main__":
    unittest.main()
