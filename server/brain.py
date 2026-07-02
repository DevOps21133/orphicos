"""OrphicOS server brain — the decision cortex.

This is the ONLY module in the codebase that names or talks to the big-brain LLM
provider (CLAUDE.md Rule 2). Everything else depends on the provider-neutral
interface `decide(...)`. To swap providers, change only this file.

Provider: NVIDIA's OpenAI-compatible API gateway (integrate.api.nvidia.com),
model `deepseek-ai/deepseek-v4-pro`. Credentials come from the server environment
(server/.env): LLM_API_KEY, LLM_MODEL, LLM_BASE_URL. No key or provider name ever
lives outside this file, THIRD-PARTY-NOTICES.txt, and the gitignored server/.env.

Zero-retention (Rule 4): screen data (ui_tree, screenshot) passed in here is used
only to build the single request and is never written to disk or logs.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import BadRequestError, OpenAI

# Action verbs the thin client (Windows-Use, Phase 2) knows how to execute.
ALLOWED_ACTIONS = (
    "launch", "click", "double_click", "right_click",
    "type", "press", "scroll", "focus_window", "wait",
)

_SYSTEM_PROMPT = """You are the OrphicOS engine: the decision cortex that drives a Windows 11 desktop.
You receive a user COMMAND and a compact UI-Automation TREE of the current screen (element names, roles, states).
Decide the next concrete Windows action(s) that move the task forward.

Return ONLY a JSON object (no prose, no markdown) with this exact shape:
{
  "actions": [
    {"type": "<verb>", "target_selector": "<element name from the tree, or null>",
     "coords": [x, y] or null, "value": "<text/keys/appname, or null>"}
  ],
  "done": <true if the COMMAND is already fully satisfied by the current screen, else false>,
  "reasoning_summary": "<one short sentence; never echo screen contents>"
}

Rules:
- Allowed "type" verbs: launch, click, double_click, right_click, type, press, scroll, focus_window, wait.
- PREFER acting on named tree elements: put the element's Name in "target_selector" and leave "coords" null.
- Use "coords" ONLY when a screenshot is provided and no named element fits (canvas/custom-drawn UI).
- "value" holds: the app name for launch; the text for type; the key chord for press (e.g. "ctrl+s", "enter");
  the direction for scroll ("up"/"down"); or the number of seconds for wait.
- Emit the smallest set of actions you are confident about for THIS screen; you will be called again with the next tree.
- Keep "reasoning_summary" to one sentence and NEVER copy screen contents into it.

How to accomplish tasks:
- Drive the GUI the way a person would. NEVER accomplish a task by typing commands into a terminal, console,
  PowerShell, or Command Prompt window, and never treat a focused terminal as a scratchpad. If a terminal is the
  active window, focus or launch the correct GUI app (e.g. File Explorer) and act there instead.
- If a modal dialog, popup, or wizard is blocking the window you need, handle it BEFORE the task: dismiss it with
  its Close/Cancel/OK button or press "escape". If it asks whether to discard or resume/recover earlier work, pick
  the clean-start option (Discard/Cancel), not the one that reopens old files. Never type task data into a dialog
  that is only in your way.
- After a "launch", the new app is ALREADY the foreground window. Do NOT click its title bar or window "to focus
  it" — a window title is not a clickable element and such a click is skipped, wasting the turn. If the app may
  still be loading (the tree looks sparse or shows only the window frame), emit a single {"type":"wait","value":"1"}
  and you will be re-called with a fuller tree; otherwise act directly on the app's content.
- To enter data into a spreadsheet, do NOT click individual cells by name — cell grids are usually absent from the
  tree, so a click on "A1" is skipped. A freshly opened sheet already has the top-left cell (A1) selected: type a
  value, then press "enter" to drop to the next row down. Put a whole column's values and confirmations in ONE
  actions array, e.g. [type "1", press "enter", type "2", press "enter", ... type "5", press "enter"]; after the
  last "enter" the cursor sits in the next empty cell of that column (A6), where you can type a formula such as
  "=SUM(A1:A5)" and confirm it with press "enter".
- For file/folder operations, use File Explorer and KEYBOARD SHORTCUTS, not small ribbon/toolbar buttons (which
  often have no stable coordinates): create a folder with press "ctrl+shift+n", then type its name and press "enter";
  rename the selected item with press "f2", then type the new name and press "enter".
- A transient inline field (the rename edit box opened by "f2" or "ctrl+shift+n", an open menu, a dropdown) will
  NOT survive until your next turn — the screen is re-read between responses, which dismisses it. Emit ALL the
  actions that fill and confirm such a field in a SINGLE "actions" array. For a rename that means
  [press "f2", type "<new name>", press "enter"] together in ONE response — never press "f2" alone and stop.
- Prefer press (keyboard shortcuts) and named tree elements over clicking tiny toolbar/ribbon icons.
"""

_client: OpenAI | None = None
_client_sig: Any = None


def _get_client() -> OpenAI:
    """Return a cached OpenAI client, rebuilding it if the key/URL changed."""
    global _client, _client_sig
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL") or None
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set in the server environment (server/.env).")
    sig = (api_key, base_url)
    if _client is None or _client_sig != sig:
        _client = OpenAI(api_key=api_key, base_url=base_url)
        _client_sig = sig
    return _client


def _as_data_uri(screenshot: str) -> str:
    return screenshot if screenshot.startswith("data:") else f"data:image/png;base64,{screenshot}"


def _build_messages(command: str, ui_tree: str, state: dict | None, screenshot: str | None) -> list[dict]:
    parts = [
        f"COMMAND:\n{command}\n",
        f"UI TREE:\n{ui_tree if ui_tree else '(empty — tree unavailable for this app)'}\n",
    ]
    if state:
        parts.append(f"STATE (prior progress):\n{json.dumps(state)[:2000]}\n")
    text_block = "\n".join(parts)

    if screenshot:
        content: Any = [
            {"type": "text", "text": text_block +
             "\nA screenshot is attached because the tree was insufficient; you may use its coords."},
            {"type": "image_url", "image_url": {"url": _as_data_uri(screenshot)}},
        ]
    else:
        content = text_block
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _create_completion(client: OpenAI, model: str, messages: list[dict]):
    """Call the provider, degrading gracefully if an optional param is rejected.

    Prefer JSON mode (forces a parseable object, and it is the faster path on this
    gateway); fall back to an unconstrained call if the endpoint rejects it. No
    thinking toggle: measured latency is throughput-bound, not reasoning-bound, and
    forcing thinking on this model returns empty content.
    """
    attempts = [
        {"response_format": {"type": "json_object"}},
        {},
    ]
    last_err: Exception | None = None
    for extra in attempts:
        try:
            return client.chat.completions.create(
                model=model, messages=messages, temperature=0.2, max_tokens=1024, **extra,
            )
        except BadRequestError as e:
            # Most likely an unsupported optional param (response_format) — drop it and
            # retry unconstrained. Auth / rate-limit / network errors are NOT caught here:
            # they propagate immediately instead of being retried pointlessly.
            last_err = e
    raise RuntimeError(f"brain: LLM call failed after parameter fallbacks: {last_err}")


def _extract_json(raw: str) -> dict:
    """Return the first JSON OBJECT in the model output, else a safe empty decision."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        brace = raw.find("{")
        if brace != -1:
            raw = raw[brace:]
    start, end = raw.find("{"), raw.rfind("}")
    candidates = [raw, raw[start:end + 1] if 0 <= start < end else None]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):  # ignore valid-but-wrong-shape JSON (arrays, null, numbers)
            return parsed
    return {"actions": [], "done": False, "reasoning_summary": ""}


def _coerce_str(v: Any) -> str | None:
    return None if v is None else str(v)


def _coerce_coords(c: Any) -> list[float] | None:
    if isinstance(c, (list, tuple)) and len(c) == 2:
        try:
            return [float(c[0]), float(c[1])]
        except (TypeError, ValueError):
            return None
    return None


def _parse_decision(raw: str, allow_coords: bool) -> dict:
    data = _extract_json(raw)
    actions = []
    for a in (data.get("actions") or []):
        if not isinstance(a, dict):
            continue
        atype = str(a.get("type", "")).strip()
        if atype not in ALLOWED_ACTIONS:
            continue  # enforce the allowlist — never forward unknown verbs to the client
        actions.append({
            "type": atype,
            "target_selector": _coerce_str(a.get("target_selector")),
            # Rule 5: coords are only meaningful on the vision fallback; drop them otherwise.
            "coords": _coerce_coords(a.get("coords")) if allow_coords else None,
            "value": _coerce_str(a.get("value")),
        })
    return {
        "actions": actions,
        "done": bool(data.get("done", False)),
        "reasoning_summary": str(data.get("reasoning_summary", ""))[:500],
    }


def decide(command: str, ui_tree: str, state: dict | None = None,
           screenshot: str | None = None) -> tuple[dict, dict]:
    """Provider-neutral decision entry point.

    Returns (decision, usage):
      decision = {"actions": [...], "done": bool, "reasoning_summary": str}
      usage    = {"prompt_tokens", "completion_tokens", "total_tokens", "latency_ms"}
    """
    client = _get_client()
    model = os.environ.get("LLM_MODEL", "deepseek-ai/deepseek-v4-pro")
    messages = _build_messages(command, ui_tree, state, screenshot)

    t0 = time.monotonic()
    completion = _create_completion(client, model, messages)
    latency_ms = int((time.monotonic() - t0) * 1000)

    decision = _parse_decision(completion.choices[0].message.content or "",
                               allow_coords=screenshot is not None)
    u = completion.usage
    usage = {
        "prompt_tokens": getattr(u, "prompt_tokens", None),
        "completion_tokens": getattr(u, "completion_tokens", None),
        "total_tokens": getattr(u, "total_tokens", None),
        "latency_ms": latency_ms,
    }
    return decision, usage
