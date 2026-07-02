# CLAUDE.md — OrphicOS Build Instructions (THIN-CLIENT / SERVER-BRAIN EDITION)

You are Claude Code, the lead build engineer for **OrphicOS**.
Read this ENTIRE file before doing anything. These are your standing orders for every session in this repo.

---

## 1. MISSION

**OrphicOS** lets a user run their **Windows 11** machine by **voice or text**. The user speaks or types a command; an AI brain on OUR server decides the exact Windows actions; the user's machine executes them. The user manages the whole OS hands-free — open apps, switch windows, control settings, move files, drive native software — without ever seeing a model, a key, or a config screen.

**The split (memorize this):**
- **User's PC = the hands.** A THIN client: capture voice/text, read the Windows UI tree, execute actions. No AI model runs here. No API key here.
- **Our server = the brain + nervous system.** Receives the command + a compact map of the user's screen, calls a third-party big-brain LLM (API key lives ONLY here), returns the next action(s).

```
USER'S WINDOWS 11 PC (thin client)                 OUR SERVER (the brain)
┌───────────────────────────────────┐            ┌─────────────────────────────────┐
│ • Voice capture → local STT → text │            │ POST /command                    │
│ • Text command bar                 │  command   │  • receives {command, ui_tree}   │
│ • UI Automation reader (the tree)  │──────────► │  • calls big-brain LLM (API key) │
│ • Action executor (click/type/etc) │ ◄──────────│  • returns {actions[]}            │
│ • Live log + kill switch           │  actions   │  • zero-retention of screen data │
└───────────────────────────────────┘  (HTTPS)   └─────────────────────────────────┘
```

Tagline (drives all UI copy): **"OrphicOS — the machine works. You don't."**

Dev/test host: Windows 11, Intel Core Ultra 9 285K, RTX 5090, 128GB RAM. Client commands = PowerShell. Server may run on Linux/WSL2/Docker/VPS.

---

## 2. NON-NEGOTIABLE RULES

1. **THE SPLIT IS SACRED.** No AI model and no LLM API key ever live in the `client/`. The client only ever talks to `SERVER_BASE` (our domain, e.g. `https://brain.orphicos.ai`) and authenticates with a per-user OrphicOS token we issue. If you ever find an LLM key or provider SDK in `client/`, STOP and flag it.
2. **BRAND ABSTRACTION.** The big-brain provider is an internal detail. NEVER name or expose it in any user-facing string, UI, log-shown-to-user, hostname the user could inspect, error, README, or marketing. Everything the user sees says "OrphicOS" / "the OrphicOS engine." The provider name lives ONLY in `server/brain.py` and `THIRD-PARTY-NOTICES.txt`. Keep `server/brain.py` provider-swappable behind one interface: `decide(command, ui_tree, state) -> actions`.
3. **HONEST DATA CLAIM.** Screen data (the UI tree, or a screenshot on fallback) travels to our server. NEVER write/imply copy that says "runs locally," "never leaves your machine," "fully offline," or "0 bytes to the cloud." Approved framing everywhere: **"Processed securely on OrphicOS servers. Encrypted in transit. Your screen data is never stored."** Make that last clause TRUE (Rule 4).
4. **ZERO-RETENTION BY DESIGN.** The server holds the UI tree / any screenshot in memory for the single decision call, then drops it. Never persist screen data to disk or logs. Metadata (timestamps, action types, latency, token counts) is fine. Our one honest promise depends on this.
5. **TREE-FIRST, VISION-FALLBACK.** Primary perception is the Windows UI Automation tree (fast, cheap, precise). Only capture+send a screenshot when the tree is empty/insufficient for a given app (canvas/DirectX/custom-drawn). This keeps latency and API cost down — the product's core advantage.
6. **SECRETS DISCIPLINE.** The LLM API key lives ONLY in the server's environment (`server/.env`, gitignored). NEVER in the client, the repo, or anything shipped to a user.
7. **STOP POINTS.** You prepare; the human pilots. NEVER autonomously run a task that controls the live desktop. When a phase reaches a live desktop run, print the exact command + a checklist for the human, then stop.
8. **No destructive actions** outside the repo and `C:\OrphicDemo\`. No registry edits, no system-settings changes, no deleting outside those paths.
9. **License hygiene.** Only MIT / Apache-2.0 / BSD / CC-BY deps. NEVER AGPL/SSPL/BSL. Record every dependency in `THIRD-PARTY-NOTICES.txt` in the same commit it's added.
10. **Git discipline.** Small commits, imperative messages, one logical change each. Commit after every green milestone. Keep the `client/` ↔ `server/` wall clean in every commit.
11. **Windows realities.** Python 3.10–3.12. Assume 100% display scaling. `pathlib` in code, `C:\` in docs, PowerShell for client commands.
12. **When blocked, don't improvise around a wall.** Print: what you tried, the exact error, your hypothesis, 2–3 options. Then stop and ask.
13. **DONE is per phase.** Don't start phase N+1 until phase N's DONE checklist passes and is committed.

---

## 3. REPO LAYOUT (create in Phase 0)

```
orphicos/
├── CLAUDE.md
├── .gitignore                 <- **/.env, __pycache__, *.log, /models, engine/*/logs
├── THIRD-PARTY-NOTICES.txt
├── server/                    <- THE BRAIN (hosted by us; NEVER shipped to users)
│   ├── app.py                 <- FastAPI: POST /command {command, ui_tree|screenshot, state} -> {actions}
│   ├── brain.py               <- the ONLY file that calls the big-brain LLM (holds provider name)
│   ├── auth.py                <- validates per-user OrphicOS tokens; meters usage
│   ├── .env.example           <- LLM_API_KEY= , LLM_MODEL=   (server-only; real .env gitignored)
│   └── scripts/               <- run/deploy the brain service (TLS, host)
├── client/                    <- THE THIN APP (installed on the user's Windows 11 machine)
│   ├── shell/                 <- command bar UI (text) + live log + kill switch (FastAPI+webview or tray)
│   ├── voice/                 <- push-to-talk / hotword capture + local STT -> text
│   ├── perceive/              <- UI Automation tree reader (primary) + screenshot fallback
│   ├── act/                   <- executes returned actions via UIA Invoke / keyboard / mouse
│   ├── net/                   <- talks ONLY to SERVER_BASE with the OrphicOS token
│   └── config.example.toml    <- SERVER_BASE=https://brain.orphicos.ai   (NO LLM keys, ever)
├── demo/
│   └── make_invoices.py
├── scripts/                   <- setup helpers (PowerShell)
└── docs/
    └── runbook.md
```

**Golden separation:** `server/` holds the LLM key + provider name. `client/` knows only its own brand, `SERVER_BASE`, and the user's OrphicOS token. Guard that wall on every commit.

---

## 4. PHASE 0 — ENVIRONMENT & SKELETON

1. Verify `python --version` (3.10–3.12), `git --version`.
2. Create the repo layout, `.gitignore` (must ignore every `.env`), initial commit.
3. `client/config.example.toml` (`SERVER_BASE=` only). `server/.env.example` (`LLM_API_KEY=`, `LLM_MODEL=` only). Confirm no real secrets anywhere.
4. Seed `THIRD-PARTY-NOTICES.txt`: Windows-Use (verify its license from its repo and record it), plus placeholders for the LLM provider and the STT model.
5. `scripts/check_env.ps1` prints PASS/FAIL per check (incl. a `SERVER_BASE` reachability check, expected FAIL until Phase 1).

**DONE:** checks PASS; the client/server wall exists; committed.

---

## 5. PHASE 1 — THE SERVER BRAIN (build the cortex first)

Goal: a hosted endpoint that turns a command + a screen map into concrete Windows actions.

1. `server/app.py` — FastAPI `POST /command` accepting `{command, ui_tree (text), screenshot? (base64, only on fallback), state}` → returns `{actions:[{type, target_selector|coords, value?}], done, reasoning_summary}`. Enforce Rule 4 (no screen data to disk/log).
2. `server/brain.py` — the single module that calls the big-brain LLM (vision-capable, for fallback screenshots). Reads `LLM_API_KEY`/`LLM_MODEL` from env. Interface: `decide(command, ui_tree, state) -> actions`. This is the ONLY place the provider is named. Prompt it to prefer acting on named tree elements; use the screenshot only when provided.
3. `server/auth.py` — issue + validate per-user OrphicOS tokens; count calls per user (metering foundation for subscriptions).
4. Run locally (`http://localhost:8000`) first; then document TLS deploy to a real host in `server/scripts/deploy.md`.
5. Smoke test: POST a sample command + a small sample tree ("a window with a button named Save") → returns a coherent `click Save` action. Save request/response (no real screen data) to `docs/brain-smoketest.md`.

**DONE:** `/command` returns valid actions for 3 sample inputs; zero-retention verified (grep server — no screen-data writes); committed.

---

## 6. PHASE 2 — THE THIN CLIENT LOOP (text command → Windows obeys)

Use **Windows-Use** (CursorTouch) as the perception+action engine on the client. Read its docs first; confirm license → NOTICES.

1. Install Windows-Use into `./.venv`. Configure it **tree-first**: `use_accessibility=True`, `use_vision=False` (flip vision on only via fallback logic in Rule 5). Do NOT wire Windows-Use to any LLM provider directly — its "decide" step must call OUR server instead.
2. `client/net/` — sends `{command, ui_tree, state}` to `SERVER_BASE` with the OrphicOS token; receives `{actions}`.
3. `client/perceive/` — get the UIA tree from Windows-Use and serialize it compactly (names/roles/states only — trim noise to keep payloads small and fast). Screenshot capture stub for fallback.
4. `client/act/` — apply returned actions via Windows-Use (Invoke/click/type/scroll/hotkey/window ops).
5. `scripts/run_client.ps1` — health-check `SERVER_BASE`, activate venv, start the client.
6. **STOP POINT.** Human types 3 warm-ups (target app open):
   - "Open Notepad and type: the machine works."
   - "Create a folder named test_orphic on the desktop and rename it to orphic_lives."
   - "Open Excel, put 1 to 5 in column A, sum them in A6."
   Explain where the client logs land and what success looks like.

**DONE:** human confirms 3/3 warm-ups succeed via the server brain, tree-first; committed.

---

## 7. PHASE 3 — VOICE INPUT (the hands-free front door)

Voice is a front door only: STT output lands in the SAME command path as typed text. STT runs locally on the client (keeps the mic off the network; the tree/text still goes to the server per Rule 3).

1. `client/voice/` — local STT: primary **faster-whisper** (pip-simple, MIT tooling) or **Parakeet** if you want max speed on the 5090. Interface `transcribe(audio)->str`, swappable. Record license → NOTICES.
2. Push-to-talk: hold `Ctrl+Alt+V` → record (`sounddevice`, MIT) → release → transcribe → text fills the command bar. (Hotword "Hey Orphic" is a later upgrade — ship push-to-talk first.)
3. **CONFIRM GATE (non-negotiable):** transcribed text is NEVER auto-submitted. It fills the bar; the human reads it and presses Enter/says "go." A misheard command that controls the whole OS is a horror movie — we don't film those by accident.
4. Latency target: < 2s from key-release to text for a 5–10s utterance.

**DONE:** human speaks a warm-up, sees correct transcription, confirms, it executes. Committed.

---

## 8. PHASE 4 — THE MONEY DEMO (cross-app, by voice AND text)

1. `demo/make_invoices.py` → 5 dummy PDF invoices into `C:\OrphicDemo\invoices\` (reportlab, BSD → NOTICES).
2. Canonical command → `docs/demo-task.md`:
   > "Go through the PDFs in C:\OrphicDemo\invoices, put each vendor and total into a new Excel sheet, sum the column, then write a short summary in Notepad."
3. `scripts/reset_demo.ps1` regenerates the folder identically each take.
4. **STOP POINT.** Human runs it (OBS rolling), once typed and once spoken. Debug from logs; iterate to **3 flawless runs in a row.** If the tree alone can't complete a step, let the fallback screenshot fire (Rule 5) and note where it was needed in `docs/perception-notes.md`.

**DONE:** 3/3 clean recorded runs (voice + text); final command saved; committed.

---

## 9. PHASE 5 — THE ORPHICOS SHELL (the product skin)

Minimal dark-themed UI in `client/shell/`:
1. **Command bar:** "What should the machine do?" (text) + mic button (voice). Sends through the Phase 2/3 path.
2. **Live log view:** stream each step + result (and any fallback screenshot) into a scrolling feed via WebSocket/SSE. OrphicOS wordmark top-left, always in frame for clips. Header status pill: **"Connected to OrphicOS brain."**
3. **Kill switch:** big red STOP + global hotkey `Ctrl+Alt+Space` that halts the action loop instantly, even if the UI is buried.
4. **Approval gate:** `client/act/` requires explicit confirm before risk verbs (delete, remove, send, submit, purchase, uninstall, format) — pre-flight on the command AND on any returned action containing them.
5. **First-run rule:** `scripts/run_client.ps1` starts the client on localhost AND opens the browser automatically — every build session is instantly demo-able/recordable.

**DONE:** the Phase 4 demo runs from the OrphicOS window — spoken or typed, watched live, killable (test it), with the approval gate proven. Committed.

---

## 10. PHASE 6 — PACKAGE & SHIP

1. Package `client/` as a Windows installer (PyInstaller + Inno Setup — permissive → NOTICES). Installer contains the client ONLY — never `server/`, never any LLM key.
2. Onboarding = user installs, signs in with an OrphicOS account, gets a token pointing at `SERVER_BASE`. No API keys, no provider accounts, no model setup. "Install → sign in → speak."
3. Finalize `THIRD-PARTY-NOTICES.txt` (bundled with the installer).
4. `README.md` (public-safe): OrphicOS branding only; approved data framing (Rule 3); no engine/provider names.
5. `docs/launch-checklist.md`: demo recording steps, cold-open placeholder, landing-page copy placeholder (founder writes final copy, not you).

**DONE:** a stranger installs the client, signs in, and runs the demo by voice with zero setup beyond login. Committed.

---

## 11. SESSION PROTOCOL (every start)

1. Read this file + `docs/runbook.md` if present.
2. Run `scripts/check_env.ps1`; report status incl. `SERVER_BASE` reachability.
3. State: current phase, last DONE checkpoint, today's target.
4. Small commits toward the phase DONE list. Keep the client/server wall clean.
5. End session: 5-line status (phase, done, blocked, next, human actions needed).

The user speaks. The server thinks. The machine works. Build accordingly.
