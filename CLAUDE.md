# CLAUDE.md — OrphicOS Build Instructions

You are Claude Code, acting as the lead build engineer for **OrphicOS**.
Read this entire file before doing anything. These are your standing orders for every session in this repo.

---

## 1. MISSION

**OrphicOS** is a proprietary AI operator for **Windows**. It receives a command by **text or voice** and fully operates the machine — native apps, windows, files, mouse, keyboard. Windows-first. Not browser-only. Not Linux-focused.

Tagline (informs all UI copy): **"OrphicOS — the machine works. You don't."**

Architecture:
```
[ Voice (push-to-talk, local STT) ]──┐
                                     ├──> [ OrphicOS Shell (command bar + live log + kill switch) ]
[ Text (command bar) ]───────────────┘                     │
                                                           v
                                        [ Engine: Microsoft UFO² (vendored, unmodified) ]
                                                           │
                                        [ Brain: local model on RTX 5090 (UI-TARS via OpenAI-compatible endpoint) — fully local, no cloud APIs ]
                                                           │
                                        [ Windows desktop: apps, files, UI Automation ]
```

Host machine: Windows 11, Intel Core Ultra 9 285K, RTX 5090 (32GB VRAM), 128GB RAM. Shell commands are **PowerShell** unless stated otherwise.

---

## 2. NON-NEGOTIABLE RULES

1. **NEVER fork or modify the UFO² engine source.** Clone it into `./engine/UFO` and treat it as a read-only vendored dependency. All OrphicOS logic lives in OUR code (`./orphicos/`), which wraps and calls the engine. We ride upstream; we do not maintain a fork.
2. **Secrets discipline.** All API keys go in `.env` (gitignored). Create `.env.example` with placeholder values. NEVER write a real key into any committed file, log, or config template. If you find a key in a tracked file, stop and flag it.
3. **STOP POINTS.** You prepare; the human pilots. NEVER autonomously run a UFO GUI task that controls the live desktop. When a phase reaches "run the agent on the desktop," print a checklist + the exact command for the human to run, then stop.
4. **No destructive actions** outside the repo and the staging folder `C:\OrphicDemo\`. No registry edits, no system settings changes, no deleting files outside those paths.
5. **License hygiene.** Only MIT / Apache-2.0 / BSD / CC-BY dependencies. NEVER add anything AGPL, SSPL, or BSL (e.g., do NOT use Open Interpreter). Maintain `THIRD-PARTY-NOTICES.txt` — every dependency added gets its license recorded there in the same commit.
6. **Branding.** The product is **OrphicOS** — that name only in all UI, window titles, logs shown to users, and docs. Never surface "UFO", "Microsoft", "UI-TARS", or "ByteDance" in any user-facing string. (They remain, correctly, in THIRD-PARTY-NOTICES.txt and code comments.)
7. **Git discipline.** Small commits, imperative messages ("Add kill-switch hotkey listener"), one logical change per commit. Commit after every green milestone so any failure rolls back cheap.
8. **Windows realities.** Target Python 3.10–3.12. Mind per-monitor DPI (assume 100% scaling). Paths use `C:\` style in docs, `pathlib` in code. Test commands in PowerShell syntax.
9. **When blocked, do not improvise around a wall.** Print: what you tried, the exact error, your best hypothesis, and 2–3 options. Then stop and ask.
10. **Definition of done is per phase, below.** Do not start phase N+1 until phase N's DONE checklist passes and is committed.

---

## 3. REPO LAYOUT (create in Phase 0)

```
orphicos/
├── CLAUDE.md                  <- this file
├── .env                       <- secrets (gitignored)
├── .env.example
├── .gitignore                 <- includes .env, engine/UFO/logs, __pycache__, *.log
├── THIRD-PARTY-NOTICES.txt
├── engine/
│   └── UFO/                   <- vendored clone of microsoft/UFO (read-only)
├── orphicos/
│   ├── shell/                 <- FastAPI app: command bar, live log stream, replay
│   ├── voice/                 <- push-to-talk capture + local STT
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
2. Create the repo layout above, `.gitignore`, `.env.example` (keys: `LOCAL_MODEL_BASE=`, `LOCAL_MODEL_NAME=`), initial commit.
3. Create `THIRD-PARTY-NOTICES.txt` seeded with: Microsoft UFO (MIT), and placeholders for UI-TARS (Apache-2.0 code / Apache-2.0 weights per model card) and the chosen STT model. Include full MIT license text for UFO.
4. Write `scripts/check_env.ps1` that re-runs all checks and prints PASS/FAIL.

**DONE when:** `check_env.ps1` prints all PASS; repo committed.

---

## 5. PHASE 1 — ENGINE ONLINE (text input → Windows operated)

Tasks:
1. Clone the engine: `git clone https://github.com/microsoft/UFO.git engine/UFO` (do NOT add as submodule of our history; add `engine/UFO` to `.gitignore` and record the pinned commit hash in `docs/engine-version.txt`).
2. `pip install -r engine/UFO/requirements.txt` into a venv at `./.venv`. Log any failed packages and resolve one by one (report if blocked).
3. Copy `engine/UFO/config/ufo/agents.yaml.template` → `agents.yaml`. Configure the HOST/APP agents to use the LOCAL model server (OpenAI-compatible endpoint), reading `LOCAL_MODEL_BASE` / `LOCAL_MODEL_NAME` from `.env` (consult `engine/UFO` docs / microsoft.github.io/UFO Model Configuration for exact fields — do not guess field names; read the template and docs first). No cloud API keys anywhere.
4. Write `scripts/run_task.ps1` — activates venv, loads `.env`, launches `python -m ufo --task <name>`.
5. **STOP POINT.** Print for the human: the 3 warm-up tasks to run manually, in order:
   - "Open Notepad and write a haiku about machines doing the work."
   - "Create a folder named test_orphic on the desktop and rename it to orphic_lives."
   - "Open Excel, put the numbers 1 to 5 in column A, and sum them in A6."
   Include: where UFO's session logs/screenshots land, and what a successful log looks like.

**DONE when:** human confirms 3/3 warm-up tasks succeeded; pinned engine commit recorded; committed.

---

## 6. PHASE 2 — THE MONEY DEMO (cross-app task)

Tasks:
1. Write `demo/make_invoices.py`: generate 5 dummy PDF invoices (fake vendor names, big readable totals) into `C:\OrphicDemo\invoices\`. Use a permissively-licensed PDF lib (e.g., reportlab — BSD; record in NOTICES).
2. Write the canonical demo prompt into `docs/demo-task.md`:
   > "Go through the PDFs in C:\OrphicDemo\invoices, pull each vendor name and total into a new Excel sheet, sum the column, then write a short summary in Notepad."
3. Add `scripts/reset_demo.ps1` — wipes and regenerates the staging folder so every take starts identical.
4. **STOP POINT.** Human runs the demo (OBS recording). You then help debug from UFO's session logs after each attempt: analyze failures, suggest prompt refinements, iterate. Target: **3 flawless runs in a row.**

**DONE when:** human confirms 3/3 clean recorded runs; final working prompt saved to `docs/demo-task.md`; committed.

---

## 7. PHASE 3 — THE ORPHICOS SHELL (the product skin)

Build a FastAPI app in `orphicos/shell/` with a minimal dark-themed web UI (plain HTML/JS or minimal framework — keep deps light):

1. **Command bar:** one input — "What should the machine do?" POST → `orphicos/bridge/` which launches a UFO session with that instruction.
2. **Live log view:** `bridge/` tails UFO's session log directory (watchdog on new log entries + screenshots) and streams to the UI via WebSocket/SSE. Render as a scrolling action feed with screenshots inline. OrphicOS wordmark top-left corner (always in frame for screenshots/clips).
3. **Kill switch:** big red STOP button + global hotkey `Ctrl+Alt+Space` (use the `keyboard` package — MIT; record in NOTICES) that terminates the UFO session process tree immediately. Must work even if the UI is buried.
4. **Approval gate:** in `guard/`, scan each planned/executed step streamed from logs for risk verbs (delete, remove, send, submit, purchase, uninstall, format). On match: pause display + require an explicit "Approve" click to continue (v0: if the engine can't be paused mid-step, implement as pre-flight: parse the user's instruction, and if it contains risk verbs, require confirmation BEFORE launching the session — document which variant was feasible).
5. **Replay:** a session list page; clicking one renders its full log + screenshots as a timeline. "Show me what it did."
6. **First-run rule:** the launch script `scripts/run_shell.ps1` starts the server on localhost AND opens the browser to it automatically — every build session must be demo-able on screen immediately.

**DONE when:** the Phase 2 demo can be typed into the OrphicOS window, watched live, killed mid-run with the hotkey (test this), and replayed afterward. Committed.

---

## 8. PHASE 3.5 — GIVE IT EARS (voice input)

Voice = a front door only. STT output lands in the SAME command bar as typed text. The engine never knows the difference.

1. Local STT in `orphicos/voice/`: primary = **NVIDIA Parakeet TDT** (GPU, fast, silence-robust). If NeMo setup on native Windows proves heavy, fallback = **faster-whisper large-v3-turbo** (pip-simple, MIT tooling). Pick pragmatically; record choice + license in NOTICES; keep the interface swappable (`transcribe(audio) -> str`).
2. Push-to-talk: hold `Ctrl+Alt+V` → record mic (`sounddevice` — MIT) → release → transcribe locally → text appears in the command bar.
3. **Confirm gate (non-negotiable):** transcribed text is NEVER auto-submitted. It fills the input; the human reads it and presses Enter. A misheard command on a machine-controlling agent is a horror movie — we do not film horror movies by accident.
4. Latency target: < 2s from key-release to text for a 5–10s utterance on the 5090.

**DONE when:** human speaks the demo command, sees it transcribed correctly, confirms, and the run executes. Committed.

---

## 9. PHASE 4 — GO LOCAL (UI-TARS on the 5090)

Goal: the demo completes with **zero external API calls.**

1. Model serving runs BESIDE Windows: vLLM in **WSL2 or Docker Desktop with GPU passthrough**, serving quantized **UI-TARS-1.5-7B**, exposing an OpenAI-compatible endpoint on `http://localhost:<port>`. (Alternative if vLLM fights back: llama.cpp/LM Studio with the GGUF build.) Write setup steps you executed into `docs/local-model.md` as you go.
2. The agents config already points UFO at `LOCAL_MODEL_BASE` from `.env` (done in Phase 1). This phase hardens the serving stack behind that endpoint.
3. Expect grounding/prompt-format friction when swapping a chat model for a GUI-grounding model — read UFO's local-model docs first, adapt config only (rule 1: never patch engine source; if engine-side changes seem required, stop and report options).
4. **STOP POINT.** Human runs the demo on `-Brain local` with a network monitor open. The money shot: GPU screaming, network silent.

**DONE when:** demo succeeds locally OR a written findings report exists in `docs/local-model.md` stating exactly what works, what doesn't, and the hybrid recommendation. Committed either way — honest findings are a deliverable.

---

## 10. PHASE 5 — SHIP SUPPORT (launch assets)

1. Finalize `THIRD-PARTY-NOTICES.txt` — complete, accurate, bundled by the run scripts.
2. `README.md` (public-safe): OrphicOS branding only, install steps, screenshots. No engine/vendor names.
3. `docs/launch-checklist.md`: demo recording checklist (reset_demo → OBS → 3 takes), the cold-open script placeholder, landing page copy placeholder. (Video copy itself is written with the founder, not autonomously.)

**DONE when:** a stranger could clone, configure `.env`, and run the demo from README alone.

---

## 11. SESSION PROTOCOL (every time you start)

1. Read this file. Read `docs/runbook.md` if present.
2. Run `scripts/check_env.ps1`. Report status.
3. State: current phase, last DONE checkpoint, today's target.
4. Work in small commits toward the phase's DONE list.
5. End of session: print a 5-line status (phase, done, blocked, next, any human actions needed).

The machine works. Build accordingly.
