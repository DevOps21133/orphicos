"""The thin-client control loop: perceive -> ask the brain -> act, repeat.

This is the whole client brain-*less* cycle (CLAUDE.md Rule 1): read the live UI
tree, send it to the OrphicOS brain, execute the actions it returns, and loop until
the brain reports the command done (or we hit max_steps). The screenshot fallback
fires only when the tree yields no interactive elements (Rule 5).
"""
from __future__ import annotations

from time import sleep
from typing import Callable

from client._engine import Desktop
from client.act import ActionError, Actor
from client.net import BrainClient
from client.perceive import Perceiver

_SETTLE_SECONDS = 0.6  # let the UI update between steps before re-reading the tree


def run_command(
    command: str,
    desktop: Desktop,
    brain: BrainClient,
    max_steps: int,
    on_event: Callable[[dict], None],
) -> str:
    """Drive `command` to completion. Returns an outcome: done | no_actions | max_steps."""
    perceiver = Perceiver(desktop)
    actor = Actor(desktop)
    history: list[dict] = []

    for step in range(1, max_steps + 1):
        perception = perceiver.perceive()
        screenshot = perceiver.capture_screenshot() if perception.is_empty else None
        state = {"steps": history[-5:]}  # small; the server also truncates state
        decision = brain.decide(command, perception.ui_tree, state, screenshot)

        actions = decision.get("actions") or []
        summary = decision.get("reasoning_summary", "")
        results = []
        for a in actions:
            try:
                outcome = actor.execute(a)
            except ActionError as e:
                outcome = f"SKIPPED: {e}"
            results.append(
                {"type": a.get("type"), "target": a.get("target_selector"),
                 "value": a.get("value"), "result": outcome}
            )

        done = bool(decision.get("done"))
        on_event({"step": step, "reasoning": summary, "used_vision": screenshot is not None,
                  "actions": results, "done": done})
        history.append({"step": step, "reasoning": summary,
                        "actions": [{"type": r["type"], "target": r["target"]} for r in results]})

        if done:
            return "done"
        if not actions:
            return "no_actions"  # nothing proposed and not done -> stop rather than spin
        sleep(_SETTLE_SECONDS)

    return "max_steps"
