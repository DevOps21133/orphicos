"""Launch the OrphicOS shell — the local dark UI that drives the desktop by command.

    python -m client.shell            (normally via scripts/run_shell.ps1)

Starts a local web server on 127.0.0.1, opens the shell in the browser, warms up the
desktop worker, and arms the global Ctrl+Alt+Space kill switch. A human uses the UI to
send commands to the live desktop and can STOP instantly (CLAUDE.md Rule 7 & §9). No LLM
key or provider lives here — the client only talks to SERVER_BASE (Rules 1 & 6).
"""
from __future__ import annotations

import sys
import threading
import webbrowser

import uvicorn

from client._engine import assert_wall_clean
from client.config import load_config
from client.net import BrainClient
from client.shell.app import create_app
from client.shell.hotkey import GlobalKillHotkey
from client.shell.runner import DesktopWorker


def main() -> int:
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    assert_wall_clean()  # Rule 1: no LLM key / provider SDK may live in the client

    brain = BrainClient(cfg.server_base, cfg.token, timeout=cfg.request_timeout)

    worker = DesktopWorker(brain, cfg.max_steps)
    worker.start()  # constructs + warms the windows-use Desktop on its own (COM) thread

    app = create_app(submit=worker.submit, health_check=brain.health,
                     server_base=cfg.server_base)

    # Global kill switch: halt the active run even if the UI is buried (§9.3).
    def panic() -> None:
        hub = app.state.hub
        session = hub.active  # capture: the worker thread may clear it as a run ends
        if session is not None:
            session.stop()
        chord = app.state.kill_label or "kill switch"
        hub.emit({"type": "status", "message": f"Kill switch pressed ({chord})."})

    hotkey = GlobalKillHotkey(panic)
    armed = hotkey.start()  # may fall back to another chord, or None if all are taken
    app.state.kill_label = armed  # the UI shows the real chord (or STOP-button-only) via /api/status

    host, port = cfg.shell_host, cfg.shell_port
    url = f"http://{host}:{port}/"
    # Open the browser once the server has had a moment to bind (§9.5: instantly demo-able).
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"OrphicOS shell -> {url}   (Ctrl+C to quit)")

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        hotkey.stop()
        worker.shutdown()
        brain.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
