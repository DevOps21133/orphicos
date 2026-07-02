# CLAUDE.md — OrphicOS Build Instructions (SERVER-BRAIN EDITION)

You are Claude Code, acting as the lead build engineer for **OrphicOS**.
Read this entire file before doing anything. These are your standing orders for every session in this repo.

---

## 1. MISSION

**OrphicOS** is a proprietary AI operator for **Windows**. A user installs a lightweight app on their Windows machine, gives a command by **text or voice**, and OrphicOS fully operates the machine — native apps, windows, files, mouse, keyboard. Windows-first. Not browser-only. Not Linux-focused.

**Architecture in one line:** a thin Windows client on the user's machine captures screen + executes actions; the reasoning ("what to click next") is done by a **server-side brain** we host. The user experiences "an AI that runs my computer." They never need to know, see, or configure the brain.

Tagline (informs all UI copy): **"OrphicOS — the machine works. You don't."**

```
USER'S WINDOWS MACHINE                        OUR SERVER
┌─────────────────────────────┐              ┌──────────────────────────────┐
│ OrphicOS Client             │              │ OrphicOS Brain Service        │
│  • command bar (text/voice) │  screenshot  │  • receives screen + goal     │
│  • screen capture           │─────────────▶│  • calls the reasoning model  │
│  • action executor (UFO²)   │◀─────────────│  • returns next action(s)     │
│  • live log + kill switch   │   action     │  • zero-retention of screens  │
└─────────────────────────────┘   (HTTPS)    └──────────────────────────────┘
```

Test/dev host: Windows 11, Intel Core Ultra 9 285K, RTX 5090, 128GB RAM. Shell commands are **PowerShell** on the client side; the brain service may run on Linux/WSL2/Docker or a VPS.

---

## 2. NON-NEGOTIABLE RULES

1. **BRAND ABSTRACTION (supreme).** The reasoning provider is an internal implementation detail. It is NEVER named or exposed in any user-facing string, UI, log shown to the user, network hostname the user would inspect, error message, or marketing copy. All product surfaces say "OrphicOS" / "the OrphicOS engine." The provider name lives ONLY in server-side code, server env vars, and `THIRD-PARTY-NOTICES.txt`. The client app contains NO provider SDK, NO provider key, and NO provider hostname — it only ever talks to `BRAIN_BASE` (our own domain, e.g. `https://brain.orphicos.ai`).
2. **HONEST DATA CLAIM.** Screenshots of the user's desktop travel to our server for reasoning. Therefore: never write, imply, or ship copy that says "runs locally," "never leaves your machine," "fully offline," or "0 bytes to the cloud." The approved framing everywhere (site, app, README, videos) is: **"Processed securely on OrphicOS servers. Encrypted in transit. Screens are never stored."** Build the product so that last clause is TRUE (see Rule 3).
3. **ZERO-RETENTION BY DESIGN.** The brain service must NOT persist user screenshots to disk or logs. Hold in memory for the single inference call, then drop. Server logs may keep metadata (timestamps, action types, latency) but never the screen images or extracted screen text. This is a build requirement, not a nice-to-have — our one honest promise depends on it.
4. **SECRETS DISCIPLINE.** The provider API key lives ONLY in the server's environment (`.env` on the server, gitignored) — NEVER in the client, NEVER in the repo, NEVER in any file shipped to a user. If you find a provider key anywhere client-side or committed, STOP and flag it.
5. **NEVER fork or modify the UFO² engine source.** Clone into `./engine/UFO`, treat as read-only vendored dependency. All OrphicOS logic lives in our code. Configuration-only integration. Ride upstream; don't maintain a fork.
6. **STOP POINTS.** You prepare; the human pilots. NEVER autonomously run a UFO GUI task that controls the live desktop. When a phase reaches "run the agent on the desktop," print a checklist + the exact command for the human to run, then stop.
7. **No destructive actions** outside the repo and the staging folder `C:\OrphicDemo\`. No registry edits, no system settings changes, no deleting files outside those paths.
8. **License hygiene.** Only MIT / Apache-2.0 / BSD / CC-BY dependencies. NEVER AGPL/SSPL/BSL (e.g., no Open Interpreter). Maintain `THIRD-PARTY-NOTICES.txt`; every dependency added is recorded in the same commit.
9. **Git discipline.** Small commits, imperative messages, one logical change each. Commit after every green milestone.
10. **Windows realities (client).** Target Python 3.10–3.12. Assume 100% display scaling. `pathlib` in code, `C:\` in docs, PowerShell for client commands.
11. **When blocked, don't improvise around a wall.** Print what you tried, the exact error, your hypothesis, 2–3 options. Then stop and ask.
12. **Definition of done is per phase.** Don't start phase N+1 until phase N's DONE checklist passes and is committed.

---

## 3. REPO LAYOUT (create in Phase 0)

```
orphicos/
├── CLAUDE.md
├── .gitignore                 <- .env, **/.env, engine/UFO/logs, __pycache__, *.log
├── THIRD-PARTY-NOTICES.txt
├── engine/
│   └── UFO/                   <- vendored clone of microsoft/UFO (read-only)
├── server/                    <- THE BRAIN (hosted by us; never shipped to users)
│   ├── app.py                 <- FastAPI: POST /think {screenshot, goal, state} -> {actions}
│   ├── provider.py            <- the reasoning-model call (the ONLY place the provider is named)
│   ├── .env.example           <- BRAIN_PROVIDER_KEY=  (server-only; real .env gitignored)
│   └── scripts/               <- run/deploy the brain service
├── client/                    <- THE APP (installed on the user's Windows machine)
│   ├── shell/                 <- command bar UI + live log + kill switch (FastAPI+webview or tray)
│   ├── voice/                 <- push-to-talk capture + STT
│   ├── bridge/                <- runs UFO²; sends screen+goal to BRAIN_BASE; applies returned actions
│   ├── guard/                 <- kill switch, approval gate
│   └── config.example.toml    <- BRAIN_BASE=https://brain.orphicos.ai   (NO keys here, ever)
├── demo/
│   └── make_invoices.py
├── scripts/                   <- setup helpers
└── docs/
    └── runbook.md
```

**The golden separation:** `server/` is ours and holds the key + provider name. `client/` is what the user gets and knows only its own brand + the `BRAIN_BASE` URL. Keep that wall clean in every commit.

---

## 4. PHASE 0 — ENVIRONMENT & SKELETON (do first)

1. Verify: `python --version` (3.10–3.12), `git --version`.
2. Create the repo layout, `.gitignore` (must ignore every `.env`), initial commit.
3. Create `THIRD-PARTY-NOTICES.txt` seeded with Microsoft UFO (MIT, full text) + placeholder for the reasoning provider.
4. Create `client/config.example.toml` (`BRAIN_BASE=` only) and `server/.env.example` (`BRAIN_PROVIDER_KEY=` only). Confirm no real secrets anywhere.
5. `scripts/check_env.ps1` prints PASS/FAIL per check.

**DONE:** checks PASS; wall between `client/` and `server/` exists; committed.

---

## 5. PHASE 1 — THE BRAIN SERVICE (fastest path to "it thinks")

Goal: a hosted endpoint that, given a screenshot + a goal + prior state, returns the next GUI action(s). Build it FIRST — it's the whole product's cortex and the fastest thing to stand up.

1. `server/app.py` — FastAPI with `POST /think`: accepts `{screenshot(base64), goal, state}`, returns structured `{actions: [...], reasoning_summary}`. Enforce Rule 3: never write the screenshot to disk/log.
2. `server/provider.py` — the single module that calls the reasoning model (vision-capable). Reads `BRAIN_PROVIDER_KEY` from server env. This is the ONE file that knows what the brain really is. Keep the interface generic: `think(screenshot, goal, state) -> actions` so the provider is swappable later.
3. Run locally first (`http://localhost:8000`), then document deploy to a real host (VPS/your 5090 box exposed via HTTPS) in `server/scripts/deploy.md`. Put it behind TLS + a simple client auth token (per-user, so you can meter/revoke) — the token is issued by us, not a provider key.
4. Smoke test: curl a sample screenshot + "open Notepad" → returns a coherent action. Save request/response (screenshot omitted from any saved artifact) in `docs/brain-smoketest.md`.

**DONE:** `/think` returns valid actions for 3 sample screens; zero-retention verified (grep server for any screenshot write → none); committed.

---

## 6. PHASE 2 — CLIENT ↔ BRAIN LOOP (text in → Windows operated)

1. Clone engine: `git clone https://github.com/microsoft/UFO.git engine/UFO` (gitignore it; pin commit in `docs/engine-version.txt`).
2. `pip install -r engine/UFO/requirements.txt` into `./.venv`; resolve failures one by one.
3. Configure UFO so its "reasoning" step calls **our** brain instead of any provider directly: point its model/endpoint config at `BRAIN_BASE` from `client/config.toml`, using its OpenAI-compatible option. **Read UFO's Model Configuration docs FIRST** (microsoft.github.io/UFO); do not guess field names. Config-only — if engine-source edits seem required, invoke Rule 11. The client must contain NO provider key or SDK — it authenticates to OUR server with the client token only.
4. `scripts/run_task.ps1` — health-check `BRAIN_BASE`, activate venv, launch `python -m ufo --task <name>`.
5. **STOP POINT.** Human runs 3 warm-ups (with target app open):
   - "Open Notepad and write a haiku about machines doing the work."
   - "Create a folder named test_orphic on the desktop and rename it to orphic_lives."
   - "Open Excel, put 1 to 5 in column A, and sum them in A6."
   Tell the human where UFO logs land and what success looks like.

**DONE:** human confirms 3/3 warm-ups succeed via the hosted brain; committed.

---

## 7. PHASE 3 — THE MONEY DEMO (cross-app)

1. `demo/make_invoices.py` → 5 dummy PDF invoices into `C:\OrphicDemo\invoices\` (reportlab, BSD; record in NOTICES).
2. Canonical prompt → `docs/demo-task.md`:
   > "Go through the PDFs in C:\OrphicDemo\invoices, pull each vendor name and total into a new Excel sheet, sum the column, then write a short summary in Notepad."
3. `scripts/reset_demo.ps1` regenerates the staging folder identically each take.
4. **STOP POINT.** Human runs it (OBS rolling). Debug from UFO logs after each attempt; iterate to **3 flawless runs in a row.**

**DONE:** 3/3 clean recorded runs; final prompt saved; committed.

---

## 8. PHASE 4 — THE ORPHICOS CLIENT SHELL (the product skin)

Minimal dark-themed UI in `client/shell/`:
1. **Command bar:** "What should the machine do?" → POSTs to `client/bridge/` → runs a UFO session driven by our brain.
2. **Live log view:** stream UFO's session log + screenshots into a scrolling feed via WebSocket/SSE. OrphicOS wordmark top-left, always in frame for clips.
3. **Kill switch:** big red STOP + global hotkey `Ctrl+Alt+Space` (`keyboard`, MIT) killing the session process tree instantly, even if UI is buried.
4. **Approval gate:** `guard/` pre-flight scans the instruction for risk verbs (delete, remove, send, submit, purchase, uninstall, format) → require explicit confirm BEFORE launching; also gate mid-run where feasible; document which variant works.
5. **First-run rule:** `scripts/run_shell.ps1` starts the client on localhost AND opens the browser automatically — every build session is instantly demo-able/recordable.

**DONE:** the Phase 3 demo runs from the OrphicOS window — typed, watched, killable (test it), replayable. Committed.

---

## 9. PHASE 5 — GIVE IT EARS (voice input)

Voice is a front door only; STT output lands in the same command bar as typed text.
1. STT in `client/voice/`: STT may be local (privacy nicety) OR server-side — your call for speed; if server-side, Rule 2's honest-data framing covers audio too. Default recommendation: local **faster-whisper** to keep the mic off the network. Keep `transcribe(audio) -> str` swappable.
2. Push-to-talk: hold `Ctrl+Alt+V` → record (`sounddevice`, MIT) → transcribe → text fills the command bar.
3. **Confirm gate (non-negotiable):** transcribed text is NEVER auto-submitted — it fills the box, the human reads it, presses Enter. Misheard commands on a machine-controlling agent are horror movies; we don't film those by accident.
4. Latency target: < 2s key-release → text for a 5–10s utterance.

**DONE:** human speaks the demo command, sees correct transcription, confirms, run executes. Committed.

---

## 10. PHASE 6 — PACKAGE & SHIP

1. Package `client/` as a Windows installer (e.g. PyInstaller + Inno Setup — permissive; record in NOTICES). The installer contains the client ONLY — never `server/`, never any provider key.
2. Finalize `THIRD-PARTY-NOTICES.txt` (complete, bundled with the installer).
3. `README.md` (public-safe): OrphicOS branding only; install → sign in with OrphicOS account/token → speak. Approved data framing from Rule 2. No engine/provider names.
4. `docs/launch-checklist.md`: demo recording steps, cold-open placeholder, landing-page copy placeholder (founder writes final copy, not you).
5. Onboarding = issue the user a client token that points them at `BRAIN_BASE`. No API keys, no provider accounts, no model setup on their end. "Install → speak" is the whole first-run.

**DONE:** a stranger installs the client, signs in, and runs the demo with zero setup beyond login. Committed.

---

## 11. SESSION PROTOCOL (every start)

1. Read this file + `docs/runbook.md` if present.
2. Run `scripts/check_env.ps1`; report status incl. `BRAIN_BASE` reachability.
3. State: current phase, last DONE checkpoint, today's target.
4. Small commits toward the phase DONE list. Keep the `client/` ↔ `server/` wall clean.
5. End session: 5-line status (phase, done, blocked, next, human actions needed).

Invisible plumbing, honest promises. The brand is OrphicOS; the brain is ours to know. Build accordingly.
