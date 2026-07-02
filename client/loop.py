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
from client.net import BrainClient, BrainError
from client.perceive import Perceiver

_SETTLE_SECONDS = 0.6   # let the UI update between steps before re-reading the tree
_DECIDE_RETRIES = 2     # a transient brain hiccup (502 / timeout) shouldn't abort a run
_RETRY_BACKOFF = 1.5    # seconds to wait before retrying the same decide call
_EMPTY_TOLERANCE = 2    # consecutive empty responses tolerated before we give up


def run_command(
    command: str,
    desktop: Desktop,
    brain: BrainClient,
    max_steps: int,
    on_event: Callable[[dict], None],
) -> str:
    """Drive `command` to completion.

    Returns an outcome: done | no_actions | brain_error | max_steps. Only `done` means
    the command was satisfied (client.__main__ maps every other outcome to a nonzero exit).
    """
    perceiver = Perceiver(desktop)
    actor = Actor(desktop)
    history: list[dict] = []
    consecutive_empty = 0

    for step in range(1, max_steps + 1):
        perception = perceiver.perceive()
        screenshot = perceiver.capture_screenshot() if perception.is_empty else None
        state = {"steps": history[-5:]}  # small; the server also truncates state

        decision = None
        for attempt in range(_DECIDE_RETRIES + 1):
            try:
                decision = brain.decide(command, perception.ui_tree, state, screenshot)
                break
            except BrainError as e:
                if attempt >= _DECIDE_RETRIES:  # exhausted retries -> stop cleanly, don't crash
                    on_event({"step": step, "reasoning": f"brain error: {e}",
                              "used_vision": screenshot is not None, "actions": [], "done": False})
                    return "brain_error"
                sleep(_RETRY_BACKOFF)  # transient -> wait a beat and retry the same step

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
        if actions:
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty > _EMPTY_TOLERANCE:  # repeatedly nothing proposed -> give up
                return "no_actions"                   # (a single empty response is tolerated)
        sleep(_SETTLE_SECONDS)

    return "max_steps"
