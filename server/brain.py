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

    Prefer JSON mode + thinking-off (lowest latency); fall back progressively.
    """
    attempts = [
        {"response_format": {"type": "json_object"},
         "extra_body": {"chat_template_kwargs": {"thinking": False}}},
        {"extra_body": {"chat_template_kwargs": {"thinking": False}}},
        {},
    ]
    last_err: Exception | None = None
    for extra in attempts:
        try:
            return client.chat.completions.create(
                model=model, messages=messages, temperature=0.2, max_tokens=1024, **extra,
            )
        except BadRequestError as e:
            # Most likely an unsupported optional param (response_format / thinking
            # toggle) — drop it and retry. Auth / rate-limit / network errors are NOT
            # caught here: they propagate immediately instead of being retried pointlessly.
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
