"""OrphicOS server brain — the decision cortex.

This is the ONLY module in the codebase that names or talks to the big-brain LLM
provider (CLAUDE.md Rule 2). Everything else depends on the provider-neutral
interface `decide(...)`. To swap providers, change only this file.

Provider: Z.ai's OpenAI-compatible API (api.z.ai), model `glm-5.2` with the
thinking phase disabled for latency (LLM_EXTRA_BODY). Previous provider — NVIDIA's
free gateway (integrate.api.nvidia.com, deepseek models) — is kept as a commented
fallback in server/.env. Credentials come from the server environment (server/.env):
LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_EXTRA_BODY. No key or provider name ever
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
    "type", "press", "scroll", "focus_window", "wait", "wait_for",
    "set_clipboard", "open_path", "screenshot",
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
  "done": <true if the COMMAND will be fully satisfied once the actions in THIS response finish (an empty
           "actions" array means it is already satisfied), else false>,
  "need_screenshot": <true ONLY when you cannot plan from this tree and must SEE the screen — your next
                      call will then include a screenshot; otherwise false>,
  "reasoning_summary": "<one short sentence; never echo screen contents>"
}

Rules:
- Allowed "type" verbs: launch, click, double_click, right_click, type, press, scroll, focus_window, wait,
  wait_for, set_clipboard, open_path, screenshot.
- PREFER acting on named tree elements: put the element's Name in "target_selector" and leave "coords" null.
- Use "coords" ONLY when a screenshot is provided and no named element fits (canvas/custom-drawn UI).
- A provided screenshot is annotated with numbered boxes; each number IS an element id from the tree above.
  Prefer that id or the element's name in "target_selector"; use raw "coords" only for a spot with no box.
- Set "need_screenshot": true and END the plan (done=false) ONLY when THIS message's tree cannot show what
  you must know — e.g. to read canvas/custom-drawn content or visually verify a result. NEVER request one
  alongside actions that open or change a window: after your actions run you automatically get the NEW tree,
  which is almost always enough — standard Windows apps (Settings, Explorer, Office, browsers) have complete
  trees. Never request one when the tree already answers the question: screenshots cost latency.
- "value" holds: the app name for launch; the text for type; the key chord for press (e.g. "ctrl+s", "enter");
  the direction for scroll ("up"/"down"); the number of seconds for wait; for wait_for the name of the
  element/window to wait for (prefix "gone:" to wait until it disappears); the text for set_clipboard; the
  absolute file/folder path for open_path; or, for screenshot, the absolute save path (null saves to the
  user's Pictures\\Screenshots folder).
- For a long-running operation (an install, a large copy, a slow page), do NOT chain fixed waits: emit ONE
  {"type":"wait_for","value":"<name that will appear>"} or {"type":"wait_for","value":"gone:<name>"} — the
  client polls for up to 2 minutes and re-plans if it times out. Pure waiting does not use up your step budget.
- To open a specific file or folder whose full path you know, prefer
  {"type":"open_path","value":"C:\\\\full\\\\path"} (opens with the default app, like a double-click in
  Explorer) over click-navigating to it.
- When the COMMAND asks to capture/screenshot the screen, emit a single {"type":"screenshot"} action — the
  client captures and saves the image on the user's own machine. NEVER drive Snipping Tool or press
  "printscreen" for this. If a specific app should be in the shot, focus_window/launch it FIRST in the same
  plan, then screenshot. This usually completes the request: set done=true alongside it.
- BATCH AGGRESSIVELY: "actions" is an ORDERED PLAN the client executes in sequence WITHOUT consulting you between
  steps. Every extra call to you costs ~10 seconds, so chain as MANY actions as you can confidently predict from
  THIS screen: launch an app and immediately type into it (a launch guarantees the app owns the foreground before
  the next action runs); fill a whole form or column in one plan; create AND rename in one plan. Cut the plan off
  only at the first step whose correct next move depends on seeing a screen you cannot predict — you will then be
  called again with a fresh tree.
- STALE IDS: numeric element ids are indices into the tree above; they are invalid after any action that changes
  the screen (launch, focus_window, a click that opens/closes something, "enter"). For every action AFTER the first
  screen-changing action in your plan, put the element's NAME in "target_selector" (or null to act on the focused
  control) — never a numeric id.
- STATE (prior progress) lists the actions ALREADY EXECUTED in earlier turns, in order, with their values and
  results. An executed action took effect even when its effect is not visible in the tree — typed text often cannot
  be read back, and work may sit in a background window. NEVER re-execute an action STATE shows succeeded. When
  STATE shows every part of the COMMAND has been carried out, return done=true with "actions": [] — do not redo
  the work "to be safe".
- Set done=true TOGETHER WITH the final actions whenever this plan completes the command — the client executes
  the plan and reports success without another call to you (a failed action still triggers a re-plan, so this is
  safe). Reserve done=false for when you genuinely must see the resulting screen to plan the next step.
- OFF-SCREEN CONTENT: the tree lists ONLY elements currently visible on screen. A SCROLLABLE PANES section under
  the tree shows panes with more content and how far each is scrolled (v=0% top, v=100% bottom). When an element
  the task needs SHOULD exist but is missing from the tree and a pane can still scroll, it is below the fold:
  emit {"type":"scroll"} (put the pane's name in "target_selector" if one is listed) and END the plan with
  done=false — the revealed elements arrive with the fresh tree on your next turn. Do not conclude an element
  does not exist until the relevant pane is scrolled to the bottom.
- If an action in your plan fails, the client aborts the rest of the plan and calls you again; STATE will contain
  "failed_action" describing which action failed and why. Re-plan from the fresh tree — do not blindly repeat it.
- Keep "reasoning_summary" to one sentence and NEVER copy screen contents into it.

How to accomplish tasks:
- Drive the GUI the way a person would. NEVER accomplish a task by typing commands into a terminal, console,
  PowerShell, or Command Prompt window, and never treat a focused terminal as a scratchpad. While a terminal is the
  active window EVERY keystroke is refused — typed text AND all key chords, INCLUDING window shortcuts like "win+d"
  or "win+e" — so you cannot escape a terminal with the keyboard. Your FIRST action must instead be a "launch" of the
  GUI app the task needs (File Explorer for file/folder work, Notepad for text, LibreOffice Calc for spreadsheets);
  "launch" is the only reliable way out of a focused terminal and opens the app as the new foreground window.
- The tree you are given shows the currently ACTIVE window plus the taskbar (rows marked win=Taskbar); you cannot
  see the contents of background windows. A taskbar row like "Notepad - 1 running window" is PROOF the app is
  already open: bring it to the front with {"type":"focus_window","value":"Notepad"} — do NOT launch it again.
  NEVER emit the same "launch" twice for one task: if the app you launched is not the active window on the next
  turn, it is running in the background — use focus_window with the app's name. Do not click taskbar buttons; do
  not use focus_window for an app with no taskbar row and no evidence it is running — "launch" that one.
- MULTIPLE INSTANCES of one app ("open 10 Notepads and put text in each"): identically-named windows CANNOT be
  told apart later — focus_window would land on an arbitrary one. NEVER launch them all first and fill them
  afterwards. Interleave instead: launch, then IMMEDIATELY do that instance's work (a launch guarantees the new
  window owns the foreground), then launch the next — [launch, type/paste, launch, type/paste, ...] in ONE plan.
  This interleaving is the ONE exception to the same-launch-twice rule above. Also know: Windows 11 Notepad is
  TABBED — "ctrl+n" opens a new TAB inside the SAME window, never a new window; a new window needs its own launch.
- If a modal dialog, popup, or wizard is blocking the window you need, handle it BEFORE the task: dismiss it with
  its Close/Cancel/OK button or press "escape". If it asks whether to discard or resume/recover earlier work, pick
  the clean-start option (Discard/Cancel), not the one that reopens old files. Never type task data into a dialog
  that is only in your way.
- After a "launch", the client waits until the new app owns the foreground, so it is the active window on your
  next turn. Do NOT click its title bar or window "to focus
  it" — a window title is not a clickable element and such a click is skipped, wasting the turn. If the app may
  still be loading (the tree looks sparse or shows only the window frame), emit a single {"type":"wait","value":"1"}
  and you will be re-called with a fuller tree; otherwise act directly on the app's content.
- To enter data into a spreadsheet, do NOT click individual cells by name — cell grids are usually absent from the
  tree, so a click on "A1" is skipped. A freshly opened sheet already has the top-left cell (A1) selected: type a
  value, then press "enter" to drop to the next row down. Put a whole column's values and confirmations in ONE
  actions array, e.g. [type "1", press "enter", type "2", press "enter", ... type "5", press "enter"]; after the
  last "enter" the cursor sits in the next empty cell of that column (A6), where you can type a formula such as
  "=SUM(A1:A5)" and confirm it with press "enter".
- To search the web or open a website, drive the BROWSER through its address bar (it doubles as a search box):
  launch the browser (or focus_window if a taskbar row shows one running), press "ctrl+l" to focus the address
  bar, type the query or URL, press "enter", then wait "2" for the page to render. Chain this in ONE plan, and
  when the task then wants a capture, append the screenshot to the SAME plan, e.g. [launch "browser", press
  "ctrl+l", type "Mercedes car", press "enter", wait "2", screenshot] with done=true. Never click a search box
  by name (page elements are often missing from the tree) — the address bar via "ctrl+l" always works.
- To write an email in Gmail: navigate the browser to "gmail.com" (address-bar chain above) and wait "2"; on
  the Gmail screen click "Compose", wait "1", then STOP that plan (done=false) — the compose pane is a new
  screen you must see before filling it. On the next turn the pane's To field already has keyboard focus: type
  the recipient (the address, or a person's name to use Gmail's contact suggestions), press "enter" to accept
  the top suggestion, press "tab" to reach Subject, type the subject, press "tab" to reach the message body,
  type the message — ALL in ONE plan. Write a clear subject and body yourself from the COMMAND's intent unless
  exact text is dictated. Finish that same plan by clicking the "Send" button with done=true; the client asks
  the user to approve the send, so the plan is safe to complete in one go.
- For file/folder operations, launch "File Explorer" first, then navigate to the target folder BEFORE creating
  anything. Navigate with the ADDRESS BAR — never by clicking a "Desktop" entry in the navigation pane, a breadcrumb,
  or a tab: several elements can share that name, a click may hit the wrong one or not change the view at all, and
  you will loop forever clicking it with no progress. Instead press "ctrl+l" to focus the address bar, type the
  location, then press "enter". For the desktop type "shell:desktop"; other known locations are "shell:downloads"
  and "shell:documents". Navigating is its OWN response: put "ctrl+l", the typed location, and "enter" in ONE array,
  then STOP and emit nothing else that turn — you cannot focus the file list or create anything until the NEXT
  screen shows the folder's contents.
- CRITICAL once the target folder is shown: the create-folder shortcut and typing only take effect when the FILE
  LIST (the content pane) has keyboard focus. While the navigation pane, a breadcrumb, the address bar, or the search
  box has focus, "ctrl+shift+n" silently does nothing and typed characters are lost. So your FIRST action in the
  folder must be to click one of the files or folders already listed in the content pane (any existing item shown
  with its size/type/date) to focus the file list. If the folder is empty and has no items to click, press "tab" to
  move focus into the file list instead.
- Then create and rename in that SAME response, using keyboard shortcuts (not the small ribbon/toolbar buttons):
  press "ctrl+shift+n", wait "1" (the new folder's rename box takes a moment to appear), type the folder name, press
  "enter"; then press "f2", wait "1", type the new name, press "enter".
- SAVE/OPEN DIALOGS: never click-navigate the folder tree inside a Save/Open dialog. Press "alt+n" to focus
  the "File name" field, type the FULL absolute path (folders included, e.g. "C:\\OrphicDemo\\report.txt"),
  then press "enter" — the dialog saves/opens exactly there.
- WINDOW MANAGEMENT is key chords, never dragging: "win+up" maximizes the active window, "win+left" /
  "win+right" snap it to half the screen (side-by-side work), "alt+f4" closes it (the user approves a close).
- To REPLACE what a text field already contains: press "ctrl+a", then type the new text — typing without
  the select-all only appends.
- To jump to a spreadsheet cell that is not adjacent: press "ctrl+g", type the cell reference (e.g. "C10"),
  press "enter".
- System settings the task may need: "win+a" opens Quick Settings (Wi-Fi, Bluetooth, volume, brightness);
  "win+n" opens the notification center. Prefer these over digging through the Settings app for a toggle.
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
        dumped = json.dumps(state)
        if len(dumped) > 2000 and isinstance(state.get("steps"), list):
            # Trim by dropping the OLDEST steps first: the newest step is the
            # evidence the model needs to know the work already happened. A blind
            # tail cut would chop exactly that.
            trimmed = dict(state)
            while len(trimmed["steps"]) > 1 and len(json.dumps(trimmed)) > 2000:
                trimmed["steps"] = trimmed["steps"][1:]
            dumped = json.dumps(trimmed)
        parts.append(f"STATE (prior progress):\n{dumped[:2400]}\n")
    text_block = "\n".join(parts)

    if screenshot:
        content: Any = [
            {"type": "text", "text": text_block +
             "\nA screenshot is attached (the tree was insufficient, or you requested it); "
             "numbered boxes on it are element ids from the tree."},
            {"type": "image_url", "image_url": {"url": _as_data_uri(screenshot)}},
        ]
    else:
        content = text_block
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _extra_body() -> dict:
    """Provider-specific request options from LLM_EXTRA_BODY (JSON in server env).

    Example: {"thinking": {"type": "disabled"}} turns off the reasoning phase on
    models that support the toggle — measured ~2x faster per decision with no loss
    on our action-planning outputs.
    """
    raw = os.environ.get("LLM_EXTRA_BODY", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _create_completion(client: OpenAI, model: str, messages: list[dict]):
    """Call the provider, degrading gracefully if an optional param is rejected.

    Prefer JSON mode (forces a parseable object, and it is the faster path on this
    gateway); fall back to an unconstrained call if the endpoint rejects it.
    """
    body = _extra_body()
    attempts = [
        {"response_format": {"type": "json_object"}},
        {},
    ]
    last_err: Exception | None = None
    for extra in attempts:
        try:
            return client.chat.completions.create(
                model=model, messages=messages, temperature=0.2, max_tokens=2048,
                extra_body=body or None, **extra,
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
        "need_screenshot": bool(data.get("need_screenshot", False)),
        "reasoning_summary": str(data.get("reasoning_summary", ""))[:500],
    }


def decide(command: str, ui_tree: str, state: dict | None = None,
           screenshot: str | None = None) -> tuple[dict, dict]:
    """Provider-neutral decision entry point.

    Returns (decision, usage):
      decision = {"actions": [...], "done": bool, "need_screenshot": bool, "reasoning_summary": str}
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
