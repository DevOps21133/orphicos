"""The thin-client control loop: perceive -> ask the brain -> act, repeat.

This is the whole client brain-*less* cycle (CLAUDE.md Rule 1): read the live UI
tree, send it to the OrphicOS brain, execute the WHOLE ordered plan it returns
locally (no brain call between actions — round trips are the latency budget), and
loop until the brain reports the command done (or we hit max_steps). The brain is
only re-consulted when the plan is exhausted or an action fails. The screenshot fallback
fires only when the tree yields no interactive elements (Rule 5).
"""
from __future__ import annotations

from time import perf_counter, sleep
from typing import Callable

from client._engine import Desktop
from client.act import ActionError, Actor
from client.net import BrainClient, BrainError
from client.perceive import Perceiver

_SETTLE_SECONDS = 0.6   # let the UI update between steps before re-reading the tree
_BATCH_SETTLE_SECONDS = 0.4  # let the UI update between actions WITHIN a batch
# Actions after which the screen (and thus element geometry) may have changed:
# re-snapshot the desktop before the next batched action so name-based
# target_selector resolution uses fresh elements/coordinates.
_SCREEN_CHANGING = frozenset(
    {"launch", "focus_window", "click", "double_click", "right_click", "press", "scroll"})
_DECIDE_RETRIES = 2     # a transient brain hiccup (502 / timeout) shouldn't abort a run
_RETRY_BACKOFF = 1.5    # seconds to wait before retrying the same decide call
_EMPTY_TOLERANCE = 2    # consecutive empty responses tolerated before we give up


def run_command(
    command: str,
    desktop: Desktop,
    brain: BrainClient,
    max_steps: int,
    on_event: Callable[[dict], None],
    should_stop: Callable[[], bool] | None = None,
    approve: Callable[[dict], bool] | None = None,
) -> str:
    """Drive `command` to completion.

    Returns an outcome: done | no_actions | brain_error | max_steps | stopped. Only
    `done` means the command was satisfied (client.__main__ maps every other outcome
    to a nonzero exit).

    Optional hooks (both default off, so the plain CLI path is unchanged):
      should_stop() -> the shell's kill switch; when it returns True the run ends as
        "stopped", checked before each step and before each action within a step.
      approve(action) -> the shell's risk-verb gate; called before executing an action.
        Returning False (a human denied it, or a stop arrived while asking) skips that
        action and ends the run as "stopped".
    """
    perceiver = Perceiver(desktop)
    actor = Actor(desktop)
    history: list[dict] = []
    consecutive_empty = 0
    last_failure: dict | None = None  # a mid-batch ActionError, reported to the brain once

    for step in range(1, max_steps + 1):
        if should_stop is not None and should_stop():
            return "stopped"
        t_perceive = perf_counter()
        perception = perceiver.perceive()
        screenshot = perceiver.capture_screenshot() if perception.is_empty else None
        perceive_ms = int((perf_counter() - t_perceive) * 1000)
        state = {"steps": history[-5:]}  # small; the server also truncates state
        if last_failure is not None:
            state["failed_action"] = last_failure  # tell the brain what broke, so it re-plans
            last_failure = None

        decision = None
        for attempt in range(_DECIDE_RETRIES + 1):
            try:
                t_decide = perf_counter()
                decision = brain.decide(command, perception.ui_tree, state, screenshot)
                decide_ms = int((perf_counter() - t_decide) * 1000)
                break
            except BrainError as e:
                if attempt >= _DECIDE_RETRIES:  # exhausted retries -> stop cleanly, don't crash
                    on_event({"step": step, "reasoning": f"brain error: {e}",
                              "used_vision": screenshot is not None, "actions": [],
                              "done": False, "timings": {"perceive_ms": perceive_ms}})
                    return "brain_error"
                sleep(_RETRY_BACKOFF)  # transient -> wait a beat and retry the same step

        actions = decision.get("actions") or []
        summary = decision.get("reasoning_summary", "")

        # Per-step latency breakdown (metadata only — never screen data, Rule 4):
        # perceive = UIA read+serialize here; decide = full round trip; brain/server
        # come from the server's own timings; net = round trip minus server time.
        timings = {"perceive_ms": perceive_ms, "decide_ms": decide_ms}
        server_timings = decision.get("timings") or {}
        if isinstance(server_timings, dict):
            llm_ms, server_ms = server_timings.get("llm_ms"), server_timings.get("server_ms")
            if isinstance(llm_ms, int):
                timings["brain_ms"] = llm_ms
            if isinstance(server_ms, int):
                timings["server_ms"] = server_ms
                timings["net_ms"] = max(decide_ms - server_ms, 0)
        results = []
        stopped = False

        # Approval pre-scan: the ENTIRE batch is inspected BEFORE action 1 runs, so a
        # risk verb later in the plan can't ride in behind safe actions. approve() is
        # instant for safe actions and only blocks (asks the human) for risky ones.
        if approve is not None:
            for a in actions:
                if should_stop is not None and should_stop():
                    stopped = True
                    break
                if not approve(a):  # risk verb denied, or stop while asking
                    results.append(
                        {"type": a.get("type"), "target": a.get("target_selector"),
                         "value": a.get("value"), "result": "SKIPPED: not approved"}
                    )
                    stopped = True
                    break

        executed = 0
        if not stopped:
            for i, a in enumerate(actions):
                if should_stop is not None and should_stop():  # kill switch between actions
                    stopped = True
                    break
                try:
                    outcome = actor.execute(a)
                except ActionError as e:
                    # Abort the REST of the batch: the plan assumed this step succeeded.
                    # Re-perceive and let the brain re-plan, telling it what failed.
                    results.append(
                        {"type": a.get("type"), "target": a.get("target_selector"),
                         "value": a.get("value"), "result": f"FAILED: {e}"}
                    )
                    last_failure = {
                        "action": {"type": a.get("type"), "target": a.get("target_selector"),
                                   "value": a.get("value")},
                        "error": str(e),
                        "plan_actions_dropped": len(actions) - i - 1,
                    }
                    break
                executed += 1
                results.append(
                    {"type": a.get("type"), "target": a.get("target_selector"),
                     "value": a.get("value"), "result": outcome}
                )
                # Cheap re-snapshot after screen-changing actions so the next batched
                # action resolves names against fresh elements (ids/coords go stale).
                if a.get("type") in _SCREEN_CHANGING and i < len(actions) - 1:
                    sleep(_BATCH_SETTLE_SECONDS)
                    desktop.get_state()

        timings["actions_executed"] = executed  # the win metric: actions per round trip
        done = bool(decision.get("done")) and not stopped and last_failure is None
        on_event({"step": step, "reasoning": summary, "used_vision": screenshot is not None,
                  "actions": results, "done": done, "timings": timings})
        # History entries must carry enough evidence for the brain to know the work
        # already happened (typed text is not always readable back from the tree):
        # keep the value (truncated) and the per-action result, not just the verb.
        history.append({
            "step": step, "reasoning": summary,
            "actions": [
                {"type": r["type"], "target": r["target"],
                 "value": None if r["value"] is None else str(r["value"])[:120],
                 "result": str(r["result"])[:80]}
                for r in results
            ],
        })

        if stopped:
            return "stopped"
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
