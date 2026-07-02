"""Run-session orchestration for the OrphicOS shell.

Bridges the synchronous perceive->decide->act loop (client.loop.run_command, which
drives windows-use and blocks) to the async web shell.

THE THREADING RULE: all desktop work happens on ONE dedicated thread — DesktopWorker —
that constructs and owns the windows-use Desktop. Windows UI Automation is COM/STA-bound,
so the Desktop must be created and used on the same thread; the shell's async side only
hands the worker commands and receives events, and never touches the desktop itself.

A RunSession carries the kill switch (a stop flag) and the approval handshake for a
single command. Stop and approval decisions arrive from OTHER threads (the WebSocket
handler, the global hotkey) and simply set thread-safe events the worker's loop observes.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

from client._engine import Desktop
from client.loop import run_command
from client.net import BrainClient
from client.shell import gate


class RunSession:
    """One command's lifecycle: streams step events, obeys stop, gates risk actions."""

    def __init__(self, command: str, emit: Callable[[dict], None]) -> None:
        self.command = command
        self._emit = emit
        self._stop = threading.Event()
        self._approval_ready = threading.Event()
        self._approval_id = 0
        self._pending_id: Optional[int] = None
        self._approved: dict[int, bool] = {}

    # --- hooks handed to run_command (called on the worker thread) ----------
    def should_stop(self) -> bool:
        return self._stop.is_set()

    def approve(self, action: dict) -> bool:
        """Block the worker until a human approves a risk action (or a stop arrives)."""
        verb = gate.action_needs_approval(action)
        if verb is None:
            return True                       # safe action -> run without asking
        if self._stop.is_set():
            return False
        self._approval_id += 1
        rid = self._approval_id
        self._pending_id = rid
        self._approval_ready.clear()
        self._emit({"type": "approval_required", "id": rid, "verb": verb,
                    "summary": _describe(action)})
        # Poll so a stop that fires while we wait unblocks us promptly.
        while not self._approval_ready.wait(timeout=0.2):
            if self._stop.is_set():
                self._pending_id = None
                return False
        self._pending_id = None
        return bool(self._approved.pop(rid, False)) and not self._stop.is_set()

    # --- control from other threads ----------------------------------------
    def stop(self) -> None:
        self._stop.set()
        self._approval_ready.set()            # unblock a pending approval as denial

    def resolve_approval(self, rid: int, approved: bool) -> None:
        if rid == self._pending_id:
            self._approved[rid] = approved
            self._approval_ready.set()

    # --- executed on the DesktopWorker thread ------------------------------
    def run(self, desktop: Desktop, brain: BrainClient, max_steps: int) -> str:
        def on_event(e: dict) -> None:
            self._emit({"type": "step", **e})

        return run_command(self.command, desktop, brain, max_steps,
                           on_event, self.should_stop, self.approve)


def _describe(action: dict) -> str:
    """A short, human-readable label for the approval prompt."""
    atype = str(action.get("type") or "action")
    detail = action.get("target_selector") or action.get("value") or ""
    return f"{atype} {detail}".strip()


class DesktopWorker(threading.Thread):
    """Owns the windows-use Desktop on a single thread; runs one command at a time."""

    def __init__(self, brain: BrainClient, max_steps: int) -> None:
        super().__init__(name="orphic-desktop", daemon=True)
        self._brain = brain
        self._max_steps = max_steps
        self._jobs: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._desktop: Optional[Desktop] = None

    def run(self) -> None:  # the thread body
        # Construct + warm up the Desktop HERE so every UIA/COM call shares this thread.
        self._desktop = Desktop(use_vision=False, use_accessibility=True)
        self._desktop.warm_up()
        self._ready.set()
        while True:
            job = self._jobs.get()
            if job is None:                   # sentinel -> shut the worker down
                break
            session, on_done = job
            try:
                outcome = session.run(self._desktop, self._brain, self._max_steps)
            except Exception as e:            # noqa: BLE001 — one bad run must not kill the worker
                outcome = f"error: {type(e).__name__}: {e}"
            on_done(outcome)

    def wait_ready(self, timeout: float | None = None) -> bool:
        return self._ready.wait(timeout)

    def submit(self, session: RunSession, on_done: Callable[[str], None]) -> None:
        self._jobs.put((session, on_done))

    def shutdown(self) -> None:
        self._jobs.put(None)
