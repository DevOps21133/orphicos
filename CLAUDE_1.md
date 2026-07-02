# CLAUDE.md — OrphicOS Build Instructions (LOCAL-ONLY EDITION)

You are Claude Code, acting as the lead build engineer for **OrphicOS**.
Read this entire file before doing anything. These are your standing orders for every session in this repo.

---

## 1. MISSION

**OrphicOS** is a proprietary AI operator for **Windows**. It receives a command by **text or voice** and fully operates the machine — native apps, windows, files, mouse, keyboard. Windows-first. Not browser-only. Not Linux-focused.

**OrphicOS is AUTARK.** It runs 100% on local hardware. No cloud LLM. No API keys. No per-token billing. No user data, screenshots, or commands ever leave the machine. The ONLY permitted network activity is the one-time download of model weights and open-source dependencies.

Tagline (informs all UI copy): **"OrphicOS — the machine works. You don't."**

Architecture:
```
[ Voice (push-to-talk, LOCAL STT) ]──┐
                                     ├──> [ OrphicOS Shell (command bar + live log + kill switch) ]
[ Text (command bar) ]───────────────┘                     │
                                                           v
                                        [ Engine: Microsoft UFO² (vendored, unmodified) ]
                                                           │
                                        [ Brain: LOCAL UI-TARS on RTX 5090 @ localhost ]
                                                           │
                                        [ Windows desktop: apps, files, UI Automation ]
```

Host machine: Windows 11, Intel Core Ultra 9 285K, RTX 5090 (32GB VRAM), 128GB RAM. Shell commands are **PowerShell** unless stated otherwise.

---

## 2. NON-NEGOTIABLE RULES

1. **THE AUTARK RULE (supreme).** No cloud LLM providers. Never add, request, configure, or reference `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or any hosted-inference credential anywhere in this repo — not in code, config, `.env`, docs, or examples. All inference points at `http://localhost:<port>`. If a task appears to require a cloud model, STOP and report — do not work around this rule.
2. **NEVER fork or modify the UFO² engine source.** Clone it into `./engine/UFO` and treat it as a read-only vendored dependency. All OrphicOS logic lives in OUR code (`./orphicos/`), which wraps and calls the engine. Configuration-only integration. We ride upstream; we do not maintain a fork.
3. **STOP POINTS.** You prepare; the human pilots. NEVER autonomously run a UFO GUI task that controls the live desktop. When a phase reaches "run the agent on the desktop," print a checklist + the exact command for the human to run, then stop.
4. **No destructive actions** outside the repo and the staging folder `C:\OrphicDemo\`. No registry edits, no system settings changes, no deleting files outside those paths.
5. **License hygiene.** Only MIT / Apache-2.0 / BSD / CC-BY dependencies and model weights. NEVER add anything AGPL, SSPL, or BSL (e.g., do NOT use Open Interpreter). Maintain `THIRD-PARTY-NOTICES.txt` — every dependency or model added gets its license recorded there in the same commit.
6. **Branding.** The product is **OrphicOS** — that name only in all UI, window titles, logs shown to users, and docs. Never surface "UFO", "Microsoft", "UI-TARS", "ByteDance", or model names in any user-facing string. (They remain, correctly, in THIRD-PARTY-NOTICES.txt and code comments.)
7. **Git discipline.** Small commits, imperative messages ("Add kill-switch hotkey listener"), one logical change per commit. Commit after every green milestone so any failure rolls back cheap.
8. **Windows realities.** Target Python 3.10–3.12. Mind per-monitor DPI (assume 100% scaling). Paths use `C:\` style in docs, `pathlib` in code. Test commands in PowerShell syntax. Model serving may live in WSL2/Docker; the engine and shell run on native Windows.
9. **When blocked, do not improvise around a wall.** Print: what you tried, the exact error, your best hypothesis, and 2–3 options. Then stop and ask.
10. **Definition of done is per phase, below.** Do not start phase N+1 until phase N's DONE checklist passes and is committed.

---

## 3. REPO LAYOUT (create in Phase 0)

```
orphicos/
├── CLAUDE.md                  <- this file
├── .env                       <- local settings only (gitignored)
├── .env.example               <- LOCAL_MODEL_BASE=http://localhost:8000/v1  (NO cloud keys, ever)
├── .gitignore                 <- includes .env, engine/UFO/logs, models/, __pycache__, *.log
├── THIRD-PARTY-NOTICES.txt
├── engine/
│   └── UFO/                   <- vendored clone of microsoft/UFO (read-only)
├── brain/
│   ├── serve_model.md         <- how the local model server is launched (living doc)
│   └── scripts/               <- WSL2/Docker launch scripts for the model server
├── orphicos/
│   ├── shell/                 <- FastAPI app: command bar, live log stream, replay
│   ├── voice/                 <- push-to-talk capture + LOCAL STT
│   ├── guard/                 <- kill switch, approval gate
│   └── bridge/                <- launches/monitors UFO sessions, parses its logs
├── demo/
│   └── make_invoices.py       <- generates dummy PDFs into C:\OrphicDemo\invoices
├── scripts/                   <- setup + run helpers (PowerShell)
└── docs/
    └── runbook.md             <- the full OrphicOS Windows Runbook (reference)
```

---

## 4. PHASE 0 — ENVIRONMENT (do first, every fresh machine)

Tasks:
1. Verify: `python --version` (3.10–3.12), `git --version`, `nvidia-smi` (RTX 5090 visible, CUDA 12.x).
2. Verify a Linux-container path for model serving exists: `wsl --status` (WSL2) OR `docker --version` with GPU support (`docker run --gpus all` capable). Report which is available; prefer whichever is already installed.
3. Create the repo layout above, `.gitignore`, `.env.example` (`LOCAL_MODEL_BASE=http://localhost:8000/v1` — nothing else), initial commit.
4. Create `THIRD-PARTY-NOTICES.txt` seeded with: Microsoft UFO (MIT, full license text), UI-TARS (Apache-2.0 code; weights per Hugging Face model card), and a placeholder for the chosen STT model.
5. Write `scripts/check_env.ps1` that re-runs all checks — including a ping to `LOCAL_MODEL_BASE` (expected to FAIL until Phase 1) — and prints PASS/FAIL per item.

**DONE when:** all checks except the model endpoint print PASS; repo committed.

---

## 5. PHASE 1 — THE LOCAL BRAIN (the moat gets poured FIRST)

Goal: **UI-TARS-1.5-7B serving an OpenAI-compatible endpoint on localhost, powered by the RTX 5090.** This is the hardest phase and it is deliberately first — everything else stacks on top of it.

Tasks:
1. Pick the serving path pragmatically and document the decision in `brain/serve_model.md`:
   - **Path A (preferred): vLLM in WSL2 or Docker** with GPU passthrough, serving `ByteDance-Seed/UI-TARS-1.5-7B` (or its quantized build), exposing `http://localhost:8000/v1`.
   - **Path B (fallback): llama.cpp / LM Studio** serving the UI-TARS-1.5-7B **GGUF** build with its mmproj vision file, OpenAI-compatible server mode. Simpler on Windows; use if Path A fights back for more than one working session.
2. Write launch scripts into `brain/scripts/` (one command to bring the brain up; one to health-check it).
3. Smoke-test the endpoint: a curl request with a test image + prompt returns a coherent grounding-style response. Save the exact request/response pair in `brain/serve_model.md`.
4. VRAM budget note: record model VRAM usage from `nvidia-smi` — the 5090's 32GB must also survive Phase 5.5's STT model living alongside it.
5. Record model + license in `THIRD-PARTY-NOTICES.txt`.

**DONE when:** `scripts/check_env.ps1` model-endpoint check prints PASS; smoke test documented; committed.

---

## 6. PHASE 2 — ENGINE ONLINE (text input → Windows operated, locally)

Tasks:
1. Clone the engine: `git clone https://github.com/microsoft/UFO.git engine/UFO` (add `engine/UFO` to `.gitignore`; record the pinned commit hash in `docs/engine-version.txt`).
2. `pip install -r engine/UFO/requirements.txt` into a venv at `./.venv`. Log any failed packages and resolve one by one (report if blocked).
3. Copy `engine/UFO/config/ufo/agents.yaml.template` → `agents.yaml`. Configure HOST/APP agents with `API_TYPE: "openai"`-compatible settings pointing at `LOCAL_MODEL_BASE` from `.env`. **Read the engine's local-model / Model Configuration docs FIRST** (microsoft.github.io/UFO) — do not guess field names, and note their guidance for non-GPT models (prompt/output format expectations). Config-only adaptation; if engine-source changes seem required, invoke Rule 9.
4. Write `scripts/run_task.ps1` — health-checks the brain endpoint, activates venv, loads `.env`, launches `python -m ufo --task <name>`.
5. **STOP POINT.** Print for the human: the 3 warm-up tasks to run manually, in order:
   - "Open Notepad and write a haiku about machines doing the work."
   - "Create a folder named test_orphic on the desktop and rename it to orphic_lives."
   - "Open Excel, put the numbers 1 to 5 in column A, and sum them in A6."
   Include: where UFO's session logs/screenshots land, and what a successful log looks like.
6. After each human-piloted attempt, analyze the session logs. Expect grounding/format friction on a local model — iterate on config and task phrasing, log findings in `docs/local-brain-findings.md`. This tuning IS the product work.

**DONE when:** human confirms 3/3 warm-up tasks succeed on the LOCAL brain; findings documented; committed.

---

## 7. PHASE 3 — THE MONEY DEMO (cross-app task)

Tasks:
1. Write `demo/make_invoices.py`: generate 5 dummy PDF invoices (fake vendor names, big readable totals) into `C:\OrphicDemo\invoices\`. Use a permissively-licensed PDF lib (e.g., reportlab — BSD; record in NOTICES).
2. Write the canonical demo prompt into `docs/demo-task.md`:
   > "Go through the PDFs in C:\OrphicDemo\invoices, pull each vendor name and total into a new Excel sheet, sum the column, then write a short summary in Notepad."
3. Add `scripts/reset_demo.ps1` — wipes and regenerates the staging folder so every take starts identical.
4. **STOP POINT.** Human runs the demo (OBS recording, network monitor visible — the money shot is GPU screaming, network silent). Debug from session logs after each attempt; iterate. Target: **3 flawless runs in a row.**
5. If the local 7B brain cannot complete the full demo after serious iteration: simplify the demo scope (fewer invoices, two apps instead of three) until it is bulletproof, and document the capability boundary honestly in `docs/local-brain-findings.md`. A smaller flawless demo beats a bigger flaky one. Do NOT reach for a cloud model — Rule 1.

**DONE when:** human confirms 3/3 clean recorded runs, fully offline-capable; final working prompt saved; committed.

---

## 8. PHASE 4 — THE ORPHICOS SHELL (the product skin)

Build a FastAPI app in `orphicos/shell/` with a minimal dark-themed web UI (plain HTML/JS or minimal framework — keep deps light):

1. **Command bar:** one input — "What should the machine do?" POST → `orphicos/bridge/` which launches a UFO session with that instruction.
2. **Live log view:** `bridge/` tails UFO's session log directory (watchdog on new entries + screenshots) and streams to the UI via WebSocket/SSE. Render as a scrolling action feed with screenshots inline. OrphicOS wordmark top-left (always in frame for clips). Status pill in the header: **"AUTARK — 0 bytes to the cloud"** fed by a lightweight check that the brain endpoint is localhost.
3. **Kill switch:** big red STOP button + global hotkey `Ctrl+Alt+Space` (the `keyboard` package — MIT; record in NOTICES) that terminates the UFO session process tree immediately. Must work even if the UI is buried.
4. **Approval gate:** in `guard/`, pre-flight scan of the user's instruction for risk verbs (delete, remove, send, submit, purchase, uninstall, format) → require explicit confirmation BEFORE launching. Additionally scan streamed steps for the same verbs and pause the display with an "Approve" requirement where feasible; document which variant proved possible.
5. **Replay:** a session list page; clicking one renders its full log + screenshots as a timeline. "Show me what it did."
6. **First-run rule:** the launch script `scripts/run_shell.ps1` brings up the brain (if down), starts the server on localhost AND opens the browser to it automatically — every build session must be demo-able on screen immediately.

**DONE when:** the Phase 3 demo can be typed into the OrphicOS window, watched live, killed mid-run with the hotkey (test this), and replayed afterward. Committed.

---

## 9. PHASE 5 — GIVE IT EARS (voice input, local)

Voice = a front door only. STT output lands in the SAME command bar as typed text. The engine never knows the difference. STT is LOCAL — Rule 1 applies to audio too; the microphone never feeds a cloud.

1. Local STT in `orphicos/voice/`: primary = **NVIDIA Parakeet TDT** (GPU, fast, silence-robust; weights CC-BY-4.0 — record in NOTICES). If NeMo setup on native Windows proves heavy, fallback = **faster-whisper large-v3-turbo** (pip-simple; record license). Keep the interface swappable (`transcribe(audio) -> str`).
2. VRAM coexistence: verify brain + STT fit together on the 5090 (`nvidia-smi` before/after); if tight, load STT on demand and release after transcription.
3. Push-to-talk: hold `Ctrl+Alt+V` → record mic (`sounddevice` — MIT) → release → transcribe locally → text appears in the command bar.
4. **Confirm gate (non-negotiable):** transcribed text is NEVER auto-submitted. It fills the input; the human reads it and presses Enter. A misheard command on a machine-controlling agent is a horror movie — we do not film horror movies by accident.
5. Latency target: < 2s from key-release to text for a 5–10s utterance on the 5090.

**DONE when:** human speaks the demo command, sees it transcribed correctly, confirms, and the run executes — all local. Committed.

---

## 10. PHASE 6 — SHIP SUPPORT (launch assets)

1. Finalize `THIRD-PARTY-NOTICES.txt` — complete, accurate, bundled by the run scripts.
2. `README.md` (public-safe): OrphicOS branding only, install steps (including the one-time model download with size expectations), screenshots. No engine/vendor names. Lead with the promise: **no account, no API key, no cloud — it runs on YOUR machine.**
3. `docs/launch-checklist.md`: demo recording checklist (reset_demo → network monitor open → OBS → 3 takes → the unplug-the-ethernet shot), cold-open script placeholder, landing page copy placeholder. (Video copy itself is written with the founder, not autonomously.)
4. First-run experience spec in `docs/first-run.md`: fresh machine → launch script detects missing weights → downloads once with a clear progress bar → brain up → ready. The out-of-the-box promise, engineered.

**DONE when:** a stranger with an NVIDIA GPU could clone, run the setup script, wait out one model download, and run the demo from README alone — no keys, no accounts.

---

## 11. SESSION PROTOCOL (every time you start)

1. Read this file. Read `docs/runbook.md` if present.
2. Run `scripts/check_env.ps1`. Report status — including brain endpoint up/down.
3. State: current phase, last DONE checkpoint, today's target.
4. Work in small commits toward the phase's DONE list.
5. End of session: print a 5-line status (phase, done, blocked, next, any human actions needed).

No keys. No cloud. No excuses. The machine works — on its own hardware. Build accordingly.
