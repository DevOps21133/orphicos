"""Run one OrphicOS command against the live desktop (text path — Phase 2).

    python -m client "Open Notepad and type: the machine works."

WARNING: this CONTROLS THE LIVE DESKTOP. A human starts it, watches the live log,
and can Ctrl+C at any time (CLAUDE.md Rule 7). It reads the UI tree, asks the
OrphicOS brain for the next actions, executes them, and repeats until done.
"""
from __future__ import annotations

import sys

from client._engine import Desktop, assert_wall_clean
from client.config import load_config
from client.loop import run_command
from client.net import BrainClient


def _print_event(event: dict) -> None:
    tag = " [vision fallback]" if event["used_vision"] else ""
    print(f"\n[step {event['step']}]{tag} {event['reasoning']}".rstrip())
    for r in event["actions"]:
        target = r["target"] or (r["value"] if r["value"] is not None else "")
        print(f"   -> {r['type']} {target}  ::  {r['result']}")
    if event["done"]:
        print("   [brain reports the command is complete]")


def main(argv: list[str]) -> int:
    command = " ".join(argv).strip()
    if not command:
        print('Usage: python -m client "<what should the machine do>"', file=sys.stderr)
        return 2

    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    assert_wall_clean()  # fail loudly if any LLM provider SDK leaked into the client

    brain = BrainClient(cfg.server_base, cfg.token, timeout=cfg.request_timeout)
    if not brain.health():
        print(f"OrphicOS brain not reachable at {cfg.server_base}. Is it running?",
              file=sys.stderr)
        brain.close()
        return 1
    print(f"Connected to OrphicOS brain at {cfg.server_base}.")

    # Tree-first perception (Rule 5, spec 6.1): accessibility on, vision off by default.
    desktop = Desktop(use_vision=False, use_accessibility=True)
    desktop.warm_up()

    print(f'Command: "{command}"')
    try:
        outcome = run_command(command, desktop, brain, cfg.max_steps, _print_event)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    finally:
        brain.close()

    print(f"\nFinished ({outcome}).")
    return 0 if outcome in ("done", "no_actions") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
