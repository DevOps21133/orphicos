"""The OrphicOS shell web app: a local dark UI over the thin-client loop.

Serves the single-page shell (command bar, live log, kill switch, approval gate) and a
WebSocket that streams each perceive->decide->act step as it happens, so the brain's
think time reads as visible progress. The desktop is driven on a dedicated worker thread
(runner.DesktopWorker); this async layer only relays commands and fans events out to
every connected browser. One command runs at a time: submissions that arrive mid-run
queue FIFO in the Hub and start when their predecessor finishes; the kill switch stops
the active run AND discards the queue. No LLM/provider anything lives here — the client
stays brain-less (Rules 1 & 6).

create_app() takes its desktop `submit` and brain `health_check` as injected callables,
so the WebSocket->loop->events path can be exercised in tests with fakes (no live
desktop, no network) — the real app injects the DesktopWorker and BrainClient.
"""
from __future__ import annotations

import asyncio
import threading
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from client.shell import gate
from client.shell.runner import RunSession

_INDEX = Path(__file__).with_name("static") / "index.html"

SubmitFn = Callable[[RunSession, Callable[[str], None]], None]


class Hub:
    """Fan-out of shell events to every connected browser, safe to call from any thread."""

    def __init__(self) -> None:
        self._conns: set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self.active: Optional[RunSession] = None
        self._pending: deque[RunSession] = deque()  # commands waiting their turn, FIFO
        self._qlock = threading.Lock()

    def bind(self, loop: asyncio.AbstractEventLoop, q: asyncio.Queue) -> None:
        self._loop, self._queue = loop, q

    def emit(self, event: dict) -> None:
        """Schedule an event onto the event loop for broadcast (thread-safe)."""
        loop, q = self._loop, self._queue
        if loop is not None and q is not None:
            loop.call_soon_threadsafe(q.put_nowait, event)

    async def broadcast(self, event: dict) -> None:
        for ws in list(self._conns):
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001 — drop a dead socket, keep serving the rest
                self._conns.discard(ws)

    def add(self, ws: WebSocket) -> None:
        self._conns.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._conns.discard(ws)

    # --- one-command-at-a-time queue -----------------------------------------
    # The desktop is a single shared surface: two commands interleaving their clicks
    # would fight over focus. One command runs at a time; anything submitted while it
    # runs queues FIFO and starts only when its predecessor finishes. The lock guards
    # active/_pending against the WebSocket handler (event loop) and the desktop
    # worker (its own thread) transitioning them concurrently.

    def admit(self, session: RunSession) -> int:
        """Claim the desktop for this session (0 = run now) or queue it (1-based position)."""
        with self._qlock:
            if self.active is None:
                self.active = session
                return 0
            self._pending.append(session)
            return len(self._pending)

    def finish_active(self) -> Optional[RunSession]:
        """Retire the finished run; promote and return the next queued session, if any."""
        with self._qlock:
            self.active = self._pending.popleft() if self._pending else None
            return self.active

    def stop_all(self) -> tuple[Optional[RunSession], int]:
        """Kill switch: discard everything queued FIRST, then stop the active run —
        a queued command silently starting right after a panic press would be a betrayal."""
        with self._qlock:
            dropped = len(self._pending)
            self._pending.clear()
            session = self.active
        if session is not None:
            session.stop()
        return session, dropped

    def queued_commands(self) -> list[str]:
        with self._qlock:
            return [s.command for s in self._pending]


def create_app(submit: SubmitFn, health_check: Callable[[], bool],
               server_base: str = "", allowed_origins: Optional[set[str]] = None,
               voice: Optional[object] = None) -> FastAPI:
    # `voice` is the Phase 3 VoiceController (duck-typed: .toggle() and .HOTKEY), or None
    # when voice isn't wired (tests). Its transcripts arrive as hub events and only FILL
    # the command bar in the browser — submission stays a human keypress (confirm gate).
    # allowed_origins guards /ws against Cross-Site WebSocket Hijacking: a page on any other
    # origin could otherwise open ws://127.0.0.1:<port>/ws and drive the desktop, since
    # browsers apply no Same-Origin Policy to the WS handshake. Browsers ALWAYS send an
    # Origin header on that handshake and JS cannot forge it, so allowing only our own
    # origin blocks every cross-origin drive-by. __main__ passes the shell's real origin(s);
    # None means "not configured" (used by tests) and disables the check.
    hub = Hub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        hub.bind(loop, q)

        async def _drain() -> None:
            while True:
                event = await q.get()
                await hub.broadcast(event)

        drain = asyncio.create_task(_drain())
        try:
            yield
        finally:
            drain.cancel()

    app = FastAPI(title="OrphicOS shell", lifespan=lifespan)
    app.state.hub = hub  # the kill-switch hotkey reaches the active session through this
    app.state.kill_label = None  # set by __main__ to the chord that actually armed (or None)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _INDEX.read_text(encoding="utf-8")

    @app.get("/api/status")
    async def status() -> JSONResponse:
        connected = await asyncio.to_thread(health_check)
        active = hub.active  # snapshot: it can retire between the two reads below
        queued = hub.queued_commands()
        return JSONResponse({"connected": bool(connected),
                             "server_base": server_base,
                             "running": active is not None,
                             # A freshly loaded page replays these so a refresh mid-run
                             # doesn't look idle (submitting would then say "queued"
                             # with no visible reason — the active run must stay visible).
                             "active_command": active.command if active else None,
                             "queued_commands": queued,
                             "queued": len(queued),
                             "kill_hotkey": app.state.kill_label,
                             "voice": voice is not None,
                             "voice_hotkey": getattr(voice, "HOTKEY", None)})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        # Reject a cross-origin handshake before accepting it (CSWSH defense). A missing
        # Origin is a non-browser client (tests/tooling), which is outside this threat model.
        if allowed_origins is not None and origin is not None and origin not in allowed_origins:
            await ws.close(code=1008)  # policy violation
            return
        await ws.accept()
        hub.add(ws)
        try:
            while True:
                msg = await ws.receive_json()
                await _handle(msg, hub, submit, ws, voice)
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove(ws)

    return app


async def _handle(msg: dict, hub: Hub, submit: SubmitFn, ws: WebSocket,
                  voice: Optional[object] = None) -> None:
    kind = msg.get("type")

    if kind == "mic":
        # The mic button toggles recording; the resulting transcript comes back as a
        # broadcast hub event and only fills the bar (confirm gate — never a run).
        if voice is None:
            await ws.send_json({"type": "error", "message": "Voice input isn't available."})
        else:
            await asyncio.to_thread(voice.toggle)
        return

    if kind == "run":
        command = (msg.get("command") or "").strip()
        # Validation errors answer the ONE socket that asked — broadcasting them would
        # reset an unrelated tab that is legitimately mid-run.
        if not command:
            await ws.send_json({"type": "error", "message": "Type a command first."})
            return
        session = RunSession(command, hub.emit)
        position = hub.admit(session)
        if position:
            # Real state, not a validation error: every tab should see the queue grow.
            hub.emit({"type": "queued", "command": command, "position": position})
            hub.emit({"type": "queue", "commands": hub.queued_commands()})
        else:
            _start_session(session, hub, submit)

    elif kind == "stop":
        session, dropped = hub.stop_all()
        if session is not None:
            note = f" {dropped} queued command(s) discarded." if dropped else ""
            hub.emit({"type": "status", "message": f"Stopping…{note}"})
            if dropped:
                hub.emit({"type": "queue", "commands": []})

    elif kind == "approve":
        session = hub.active
        if session is not None:
            session.resolve_approval(int(msg.get("id", 0)),
                                     msg.get("decision") == "approve")


def _start_session(session: RunSession, hub: Hub, submit: SubmitFn) -> None:
    """Announce and launch a session; when it finishes, promote the next queued one."""
    hub.emit({"type": "run_started", "command": session.command,
              "flagged": gate.command_has_risk(session.command)})

    def on_done(outcome: str) -> None:  # called on the worker thread when the run ends
        hub.emit({"type": "run_finished", "outcome": outcome})
        nxt = hub.finish_active()
        hub.emit({"type": "queue", "commands": hub.queued_commands()})
        if nxt is not None:
            _start_session(nxt, hub, submit)

    submit(session, on_done)
