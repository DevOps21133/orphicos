"""Unit tests for the Phase 3 voice front door.

FakeRecorder / fake transcribe functions here are TEST FIXTURES only (CLAUDE.md
Rule 14) — they exercise the VoiceController state machine and the confirm gate
without a microphone. The one real-engine test feeds stt.transcribe a generated
sine-wave WAV-equivalent buffer (no speech in it) and asserts the wiring returns a
string without crashing; it downloads the model on first run and is skippable via
ORPHIC_SKIP_STT_TEST=1 for quick suite runs.
"""
from __future__ import annotations

import os
import threading
import time
import unittest

import numpy as np

from client.voice.controller import VoiceController


class FakeRecorder:
    """Test fixture: a Recorder stand-in that returns canned audio (no microphone)."""

    def __init__(self, audio: np.ndarray, fail_start: bool = False) -> None:
        self.sample_rate = 16000
        self.recording = False
        self._audio = audio
        self._fail_start = fail_start
        self.starts = 0

    def start(self) -> None:
        if self._fail_start:
            raise RuntimeError("no mic")
        self.starts += 1
        self.recording = True

    def stop(self) -> np.ndarray:
        self.recording = False
        return self._audio


def _speech_length_audio() -> np.ndarray:
    return np.zeros(16000, dtype=np.float32)  # 1s: above the too-short threshold


def _wait_for(emits, match, timeout=2.0):
    """Wait until an event satisfies `match` (an event type name, or a predicate)."""
    pred = match if callable(match) else (lambda e, t=match: e.get("type") == t)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for e in list(emits):
            if pred(e):
                return e
        time.sleep(0.005)
    raise AssertionError(f"no matching event was emitted: {emits}")


def _is_idle(e):
    return e.get("type") == "voice" and e.get("state") == "idle"


class ControllerTests(unittest.TestCase):
    def _controller(self, recorder, transcribe):
        emits: list[dict] = []
        vc = VoiceController(recorder=recorder, transcribe_fn=transcribe)
        vc.bind_emit(emits.append)
        return vc, emits

    def test_record_then_transcript_fills_bar_and_never_submits(self):
        vc, emits = self._controller(FakeRecorder(_speech_length_audio()),
                                     lambda audio: "open notepad")
        vc.start_recording()
        self.assertEqual(emits[0], {"type": "voice", "state": "recording"})
        vc.stop_and_transcribe()
        ev = _wait_for(emits, "transcript")
        self.assertEqual(ev["text"], "open notepad")
        _wait_for(emits, "voice", timeout=2.0)
        # CONFIRM GATE: the controller must never emit a run — only the transcript.
        self.assertEqual([e["type"] for e in emits if e["type"] not in ("voice",)],
                         ["transcript"])

    def test_toggle_starts_then_stops(self):
        rec = FakeRecorder(_speech_length_audio())
        vc, emits = self._controller(rec, lambda audio: "hello")
        vc.toggle()
        self.assertTrue(rec.recording)
        vc.toggle()
        _wait_for(emits, "transcript")
        self.assertFalse(rec.recording)
        self.assertEqual(rec.starts, 1)

    def test_too_short_audio_is_discarded_with_a_hint(self):
        vc, emits = self._controller(FakeRecorder(np.zeros(800, dtype=np.float32)),
                                     lambda audio: "should never be called")
        vc.start_recording()
        vc.stop_and_transcribe()
        idle = _wait_for(emits, _is_idle)
        self.assertIn("Too short", idle["message"])
        self.assertFalse(any(e["type"] == "transcript" for e in emits))

    def test_empty_transcript_reports_didnt_catch(self):
        vc, emits = self._controller(FakeRecorder(_speech_length_audio()),
                                     lambda audio: "")
        vc.start_recording()
        vc.stop_and_transcribe()
        idle = _wait_for(emits, _is_idle)
        self.assertIn("Didn't catch", idle["message"])
        self.assertFalse(any(e["type"] == "transcript" for e in emits))

    def test_transcribe_error_reports_cleanly(self):
        def boom(audio):
            raise RuntimeError("engine exploded")
        vc, emits = self._controller(FakeRecorder(_speech_length_audio()), boom)
        vc.start_recording()
        vc.stop_and_transcribe()
        idle = _wait_for(emits, _is_idle)
        self.assertIn("failed", idle["message"])
        self.assertFalse(any(e["type"] == "transcript" for e in emits))

    def test_mic_failure_is_a_message_not_a_crash(self):
        vc, emits = self._controller(FakeRecorder(_speech_length_audio(), fail_start=True),
                                     lambda audio: "x")
        vc.start_recording()
        self.assertEqual(emits[0]["state"], "idle")
        self.assertIn("Microphone unavailable", emits[0]["message"])

    def test_start_while_transcribing_is_ignored(self):
        release = threading.Event()

        def slow(audio):
            release.wait(2)
            return "slow result"

        rec = FakeRecorder(_speech_length_audio())
        vc, emits = self._controller(rec, slow)
        vc.start_recording()
        vc.stop_and_transcribe()          # busy now
        vc.start_recording()              # must be a no-op while busy
        self.assertEqual(rec.starts, 1)
        release.set()
        _wait_for(emits, "transcript")

    def test_stop_without_recording_is_a_noop(self):
        vc, emits = self._controller(FakeRecorder(_speech_length_audio()),
                                     lambda audio: "x")
        vc.stop_and_transcribe()
        self.assertEqual(emits, [])


@unittest.skipIf(os.environ.get("ORPHIC_SKIP_STT_TEST") == "1",
                 "real STT engine test skipped by ORPHIC_SKIP_STT_TEST")
class RealEngineTests(unittest.TestCase):
    """Exercises the real faster-whisper path (downloads the model on first run)."""

    def test_transcribe_sine_wave_returns_a_string(self):
        from client.voice import stt
        t = np.linspace(0, 1.0, stt.SAMPLE_RATE, endpoint=False)
        tone = (0.1 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        started = time.monotonic()
        out = stt.transcribe(tone)
        elapsed = time.monotonic() - started
        self.assertIsInstance(out, str)   # a pure tone may yield "" — that's correct
        print(f"[stt] 1s tone transcribed in {elapsed:.2f}s -> {out!r}")

    def test_transcribe_rejects_wrong_sample_rate(self):
        from client.voice import stt
        with self.assertRaises(ValueError):
            stt.transcribe(np.zeros(100, dtype=np.float32), sample_rate=44100)


if __name__ == "__main__":
    unittest.main()
