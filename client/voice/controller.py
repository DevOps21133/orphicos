"""The voice front door: push-to-talk / mic-button recording -> local STT -> command bar.

VoiceController glues the pieces together: the Ctrl+Alt+V push-to-talk watcher and the
shell's mic button both drive ONE state machine (idle -> recording -> transcribing ->
idle) and every state change plus the final transcript is emitted as a shell event, so
the browser UI can animate the mic and fill the command bar.

CONFIRM GATE (CLAUDE.md §7.3, non-negotiable): this module emits {"type": "transcript"}
and NOTHING ELSE with the text. It never emits "run", never touches the run loop, never
submits. The transcript only fills the bar; the human reads it and presses Enter.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from client.voice import stt
from client.voice.ptt import HOTKEY_LABEL, PushToTalk
from client.voice.recorder import Recorder

_MIN_SECONDS = 0.3  # anything shorter is a key-tap, not an utterance


class VoiceController:
    """Owns the recorder, the push-to-talk watcher, and the transcription hand-off."""

    HOTKEY = HOTKEY_LABEL

    def __init__(self, recorder: Optional[Recorder] = None,
                 transcribe_fn: Optional[Callable[..., str]] = None) -> None:
        # The injectable seams exist for the unit tests (fake recorder / fake STT);
        # the shell constructs this with no arguments and gets the real thing.
        self._recorder = recorder if recorder is not None else Recorder()
        self._transcribe = transcribe_fn if transcribe_fn is not None else stt.transcribe
        self._preload = transcribe_fn is None  # only the real engine has weights to warm
        self._emit: Callable[[dict], None] = lambda event: None
        self._lock = threading.Lock()
        self._busy = False  # a transcription is in flight
        self._ptt = PushToTalk(self.start_recording, self.stop_and_transcribe)

    def bind_emit(self, emit: Callable[[dict], None]) -> None:
        """Attach the shell hub's thread-safe event sink."""
        self._emit = emit

    def start(self) -> None:
        """Arm push-to-talk and warm the STT model so the first utterance is fast."""
        self._ptt.start()
        if self._preload:
            threading.Thread(target=stt.preload, name="orphic-stt-preload",
                             daemon=True).start()

    def stop(self) -> None:
        self._ptt.stop()
        if self._recorder.recording:
            self._recorder.stop()

    # --- state machine (each entry point may be called from any thread) ---------

    def toggle(self) -> None:
        """The mic button: click to start recording, click again to transcribe."""
        if self._recorder.recording:
            self.stop_and_transcribe()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        with self._lock:
            if self._busy or self._recorder.recording:
                return
            try:
                self._recorder.start()
            except Exception:  # noqa: BLE001 — no/blocked microphone must not crash the shell
                self._emit({"type": "voice", "state": "idle",
                            "message": "Microphone unavailable. Check your input device."})
                return
        self._emit({"type": "voice", "state": "recording"})

    def stop_and_transcribe(self) -> None:
        with self._lock:
            if not self._recorder.recording:
                return
            audio = self._recorder.stop()
            self._busy = True
        if audio.size < int(_MIN_SECONDS * self._recorder.sample_rate):
            with self._lock:
                self._busy = False
            self._emit({"type": "voice", "state": "idle",
                        "message": f"Too short — hold {self.HOTKEY} while you speak."})
            return
        self._emit({"type": "voice", "state": "transcribing"})
        # Transcribe off the caller's thread (the PTT watcher / WS handler must not block).
        threading.Thread(target=self._finish, args=(audio,), name="orphic-stt",
                         daemon=True).start()

    def _finish(self, audio) -> None:
        try:
            text = self._transcribe(audio)
        except Exception:  # noqa: BLE001 — surface a clean message, never a stack trace
            text = None
        with self._lock:
            self._busy = False
        if text is None:
            self._emit({"type": "voice", "state": "idle",
                        "message": "Voice input failed. Try again."})
        elif not text:
            self._emit({"type": "voice", "state": "idle",
                        "message": "Didn't catch that — try again."})
        else:
            # CONFIRM GATE: the transcript FILLS the bar; the human presses Enter.
            self._emit({"type": "transcript", "text": text})
            self._emit({"type": "voice", "state": "idle"})
