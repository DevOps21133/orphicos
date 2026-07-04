"""The thin-client control loop: perceive -> ask the brain -> act, repeat.

This is the whole client brain-*less* cycle (CLAUDE.md Rule 1): read the live UI
tree, send it to the OrphicOS brain, execute the WHOLE ordered plan it returns
locally (no brain call between actions — round trips are the latency budget), and
loop until the brain reports the command done (or we hit max_steps). The brain is
only re-consulted when the plan is exhausted or an action fails. The screenshot fallback
fires only when the tree is insufficient for the active window, or when the brain's
previous decision asked to see the screen (need_screenshot) — Rule 5.
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
_PURE_WAIT = frozenset({"wait", "wait_for"})  # steps that only pass time
_WAIT_WAIVERS = 3       # pure-wait steps that don't consume the max_steps budget

# Most action results are short status strings ("opened X", "clicked (x,y)") kept
# tiny so STATE stays small. read_document/list_dir instead return CONTENT the brain
# must read in full (a PDF's text, a folder listing) — they get a far larger cap.
# The document reader already bounds its own text, so this is just a backstop.
_RESULT_CAP = 80
_CONTENT_ACTIONS = frozenset({"read_document", "list_dir"})
_CONTENT_RESULT_CAP = 6000

# Re-reading a document or re-listing a folder already gathered this run is the
# signature of a stuck brain: it lost track of its progress (typically because a
# canvas app like a spreadsheet is absent from the tree, so it cannot SEE the work it
# already did) and restarted the task from scratch. Reads are idempotent, so a couple
# of redundant ones are harmless — but past this budget the run is looping, and we stop
# it rather than let it re-type over a half-filled sheet forever (exactly the runaway
# the kill switch exists for). Enforced in the client, not trusted to the brain prompt.
_GATHER_ACTIONS = frozenset({"read_document", "list_dir"})
_STUCK_REGATHER_LIMIT = 3

# Wave 2 backstop: a question COMMAND (read/tell me/what/which…) that finishes
# "done" with no answer, no actions, and no screenshot request is the silent-
# failure signature — the brain couldn't read the value (a canvas/custom-drawn
# control like Calculator's display) and gave up instead of recovering. The
# ANSWERING prompt rule should make the brain request vision or answer honestly;
# this is the deterministic net that catches it if the brain still misfires. It
# never fires for a DOING command (open/type/save…), which correctly ends done
# with no answer. Conservative on purpose: a miss just means no backstop (safe).
_QUESTION_OPENERS = ("what", "which", "how many", "how much", "who", "whose", "where",
                     "read me", "tell me", "show me", "what's", "whats", "where's")
_QUESTION_WORDS = ("what", "which", "how many", "how much", "whose", "who is",
                   "where is", "read me", "tell me", "show me")
_UNANSWERED_REPLY = ("I couldn't read that from the screen — the value isn't exposed to "
                     "the UI tree. Try rephrasing, or I can take a screenshot to see it.")


def _looks_like_question(command: str) -> bool:
    """Heuristic: does this command ASK for on-screen content (vs. DO something)?

    Tight by design — false negatives merely skip the backstop (safe), while false
    positives would over-answer doing-commands. So we require a clear question
    signal: a wh/tell-me/read-me opener, or a question mark."""
    c = command.strip().lower()
    if not c:
        return False
    if c.endswith("?"):
        return True
    return any(c.startswith(w + " ") for w in _QUESTION_OPENERS) or any(w in c for w in _QUESTION_WORDS)


def _clip_result(result, atype: str | None) -> str:
    cap = _CONTENT_RESULT_CAP if atype in _CONTENT_ACTIONS else _RESULT_CAP
    text = str(result)
    return text if len(text) <= cap else text[:cap] + "…"


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
    actor = Actor(desktop, should_stop=should_stop)  # so the kill switch breaks wait_for polls
    history: list[dict] = []
    consecutive_empty = 0
    last_failure: dict | None = None  # a mid-batch ActionError, reported to the brain once
    gathered: set[tuple] = set()  # (type, value) of reads/lists already done this run
    redundant_gathers = 0  # how many times the brain re-gathered already-known data
    force_screenshot = False  # the brain's previous decision set need_screenshot
    steps_used = 0
    step = 0  # monotonic step label for events/history (waived steps still count up)
    wait_waivers = _WAIT_WAIVERS
    is_question = _looks_like_question(command)  # Wave 2 backstop eligibility
    answered = False  # has the brain emitted ANY answer this run?

    def _backstop_unanswered() -> None:
        """The Wave 2 net: a question ending with no answer gets an honest one,
        so the run can never finish 'done' while silently ignoring the user.
        Only fires for questions that did nothing (no actions) and got no answer."""
        if is_question and not answered:
            on_event({"step": step, "reasoning": "", "used_vision": False,
                      "actions": [], "done": True, "answer": _UNANSWERED_REPLY,
                      "timings": {}})

    while steps_used < max_steps:
        step += 1
        if should_stop is not None and should_stop():
            return "stopped"
        t_perceive = perf_counter()
        perception = perceiver.perceive()
        screenshot = (perceiver.capture_screenshot()
                      if (perception.is_empty or force_screenshot) else None)
        force_screenshot = False
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
        force_screenshot = bool(decision.get("need_screenshot"))

        # Loop guard: if the plan re-reads/re-lists targets already gathered this run,
        # the brain has lost its progress and is restarting the task. Idempotent reads
        # make a few harmless, but past the budget the run is looping — stop it here,
        # before it re-types over work already done, instead of burning the step budget.
        redundant_gathers += sum(
            1 for a in actions
            if a.get("type") in _GATHER_ACTIONS and (a.get("type"), a.get("value")) in gathered)
        if redundant_gathers >= _STUCK_REGATHER_LIMIT:
            on_event({"step": step, "reasoning": "Stopped: the engine was repeating steps it "
                      "had already completed without making progress.",
                      "used_vision": screenshot is not None, "actions": [], "done": False,
                      "timings": {"perceive_ms": perceive_ms}})
            return "stuck"

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
                if a.get("type") in _GATHER_ACTIONS:  # remember what we've read/listed
                    gathered.add((a.get("type"), a.get("value")))
                # Cheap re-snapshot after screen-changing actions so the next batched
                # action resolves names against fresh elements (ids/coords go stale).
                if a.get("type") in _SCREEN_CHANGING and i < len(actions) - 1:
                    sleep(_BATCH_SETTLE_SECONDS)
                    desktop.get_state()

        timings["actions_executed"] = executed  # the win metric: actions per round trip
        done = bool(decision.get("done")) and not stopped and last_failure is None
        event = {"step": step, "reasoning": summary, "used_vision": screenshot is not None,
                 "actions": results, "done": done, "timings": timings}
        if decision.get("locked_skill"):
            # The brain answered with a skill-store upsell instead of doing the task
            # (the actions open that skill's checkout page); the shell renders this
            # step distinctly.
            event["locked_skill"] = str(decision["locked_skill"])
        if decision.get("answer"):
            # The brain replied to a question about on-screen content (Wave 2
            # "read it back"). Surfaced as the engine's spoken answer, NOT written
            # into history/STATE (an answer is not an action; STATE stays compact,
            # and a stale answer would mislead the next plan).
            event["answer"] = str(decision["answer"])
            answered = True  # the backstop only fires if NO answer ever arrived
        if decision.get("remembered"):
            # Facts the user asked to save this turn — the shell shows a "🧠 Remembered"
            # note so saving is always visible (never silent profiling, Stage-1 consent).
            event["remembered"] = decision["remembered"]
        on_event(event)
        # History entries must carry enough evidence for the brain to know the work
        # already happened (typed text is not always readable back from the tree):
        # keep the value (truncated) and the per-action result, not just the verb.
        history.append({
            "step": step, "reasoning": summary,
            "actions": [
                {"type": r["type"], "target": r["target"],
                 "value": None if r["value"] is None else str(r["value"])[:120],
                 "result": _clip_result(r["result"], r["type"])}
                for r in results
            ],
        })

        if stopped:
            return "stopped"
        if done:
            # Wave 2 backstop: a question that ends "done" with no answer and no
            # actions was silently ignored — give the user an honest reply instead.
            if is_question and not answered and not results:
                _backstop_unanswered()
            return "done"
        if actions:
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty > _EMPTY_TOLERANCE:  # repeatedly nothing proposed -> give up
                # Same net as above: a question the brain gave up on is still answered.
                _backstop_unanswered()
                return "no_actions"                   # (a single empty response is tolerated)
        # A pure-wait step spent time, not budget: waive a few so waiting out a
        # long operation (install, download) can't eat the whole run, while a
        # brain stuck emitting waits forever still terminates.
        if actions and all(a.get("type") in _PURE_WAIT for a in actions) and wait_waivers > 0:
            wait_waivers -= 1
        else:
            steps_used += 1
        sleep(_SETTLE_SECONDS)

    # Wave 2 backstop: a question that ran out of steps without answering still
    # gets an honest reply — the worst outcome is a silent "max steps" on a question.
    _backstop_unanswered()
    return "max_steps"
