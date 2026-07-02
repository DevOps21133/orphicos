# OrphicOS Brain — Smoke Test (Phase 1)

Verifies `POST /command` turns a command + a UI-Automation tree into coherent
Windows actions. **All trees below are synthetic** — no real screen data is
captured or stored (Rule 4). Run against the local server on 2026-07-02.

## Setup
```powershell
server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000
$TOKEN = server\.venv\Scripts\python.exe -m server.auth issue demo
```

## Health & auth guard
| Check | Request | Result |
|---|---|---|
| Health | `GET /health` | `{"status":"ok","service":"OrphicOS engine"}` |
| Auth required | `POST /command` with **no** token | `401 Unauthorized` |

## Sample 1 — click a named element (tree-first)
**Request**
```json
{"command": "Save the document",
 "ui_tree": "Window \"Untitled - Notepad\"\n  MenuBar\n  Edit \"Text editor\" value=\"hello world\"\n  Button \"Save\"\n  Button \"Cancel\""}
```
**Response** (HTTP 200)
```json
{"actions": [{"type": "click", "target_selector": "Save", "coords": null, "value": null}],
 "done": false,
 "reasoning_summary": "Click the Save button to proceed with saving the document."}
```

## Sample 2 — launch an app
**Request**
```json
{"command": "Open Notepad and type: Meeting notes",
 "ui_tree": "Desktop\n  TaskBar\n    Button \"Start\"\n    Button \"Search highlights\""}
```
**Response** (HTTP 200)
```json
{"actions": [{"type": "launch", "target_selector": null, "coords": null, "value": "Notepad"}],
 "done": false,
 "reasoning_summary": "Notepad is not yet open, so launching it is the first step."}
```

## Sample 3 — multi-step sequence
**Request**
```json
{"command": "In the Amount field enter 250 then click Submit",
 "ui_tree": "Window \"Expense Form\"\n  Edit \"Description\"\n  Edit \"Amount\"\n  ComboBox \"Category\"\n  Button \"Submit\"\n  Button \"Cancel\""}
```
**Response** (HTTP 200)
```json
{"actions": [
    {"type": "click", "target_selector": "Amount", "coords": null, "value": null},
    {"type": "type",  "target_selector": "Amount", "coords": null, "value": "250"},
    {"type": "click", "target_selector": "Submit", "coords": null, "value": null}],
 "done": false,
 "reasoning_summary": "Focus the Amount field, enter 250, then click Submit."}
```

## Result
- 3/3 samples returned **valid, coherent actions**; every action targets a named
  tree element (`target_selector` set, `coords` null) — tree-first per Rule 5.
- Auth enforced (401 without a token); metering counts each call.
- **Zero-retention confirmed:** server logs are metadata only
  (`cmd user=demo actions=1 types=click done=False latency_ms=… tokens=… calls=…`);
  the `ui_tree`, any screenshot, and the command text are never written to disk or logs.

## Notes
- Provider: NVIDIA-hosted `deepseek-ai/deepseek-v4-pro` (named only in `server/brain.py`).
- Observed latency 6–29 s on NVIDIA's shared endpoint — a tuning item for the
  interactive product (candidate levers: the `deepseek-v4-flash` variant, the
  `thinking:false` toggle, dedicated capacity). Not a Phase 1 correctness blocker.
