# 🕶️ OrphicOS — Windows Build Runbook (v0)

**North star:** OrphicOS plugs into Windows and operates the whole machine — apps, windows, mouse, keyboard. Windows-first. Not browser-only. Not Linux.

**Tagline:** *OrphicOS — the machine works. You don't.*

**The play in one line:** Stand on Microsoft's MIT-licensed UFO² (the Windows "Desktop AgentOS"), wrap it in the OrphicOS brand + guardrails, run the brain locally (UI-TARS on the RTX 5090) for the "never phones home" moat, and launch it loud on Raw AI.

---

## Phase 0 — Prep the rig (half a day)

Your machine: Windows 11, Core Ultra 9 285K, RTX 5090 32GB, 128GB RAM. More than enough. Do these first:

1. **Python 3.10–3.12** installed and on PATH (`python --version`).
2. **Git** installed (`git --version`).
3. **No cloud API keys.** The brain is a local model on the 5090 from day one — fully local, nothing phones home.
4. **Display scaling to 100%** on the monitor the agent will drive. Per-monitor DPI scaling is the #1 cause of "agent clicks the wrong pixel" on Windows. Kill that landmine on day one.
5. **A dedicated Windows user account** (e.g. `orphic-agent`) or a Windows Sandbox/VM for early testing. The agent screenshots the desktop and sends them to the LLM — keep wallets, passwords, and private tabs off that desktop. Golden rule survives: **the agent gets its own world.**
6. **OBS Studio** installed. Every test run is potential launch footage. Record everything — the blooper where it opens Paint instead of Excel is *also* content.

---

## Phase 1 — Install UFO² and wire the local brain (Day 1–2)

**Goal:** one natural-language command → UFO² drives a real Windows app. That's the "it's alive!" moment.

```powershell
# 1. Clone
git clone https://github.com/microsoft/UFO.git
cd UFO

# 2. Install
pip install -r requirements.txt

# 3. Configure the agent brains
copy config\ufo\agents.yaml.template config\ufo\agents.yaml
# Edit agents.yaml → point it at the local model server (OpenAI-compatible
# endpoint on localhost) — see their Model Configuration Guide in the docs
# at microsoft.github.io/UFO for the exact fields.

# 4. First flight
python -m ufo --task first_run
```

Then type something dead simple, with the target app **already open** (UFO works best when the app is active, even minimized):

> "Open Notepad and write a haiku about machines doing the work."

**What to know about how it thinks:** UFO² is a HostAgent (picks the app, decomposes the task, switches apps mid-task) + AppAgents (drive each app via Windows UI Automation *and* vision parsing, plus native APIs where available). It reads the real Windows control tree, not just pixels — that's why it beats naive screenshot-clickers.

**Where the receipts live:** UFO saves screenshots + full request/response logs per session. That folder is your debugger *and* — spoiler for Phase 3 — the raw material for the OrphicOS replay feature.

✅ **Exit criteria:** three different single-app tasks succeed (Notepad, File Explorer, Excel). Don't leave Phase 1 until they do. Reliability is the product.

---

## Phase 2 — The money demo: one cross-app task (Day 3–5)

**Goal:** the launch-video shot. One sentence in, multi-app work out, zero touching the keyboard.

**The demo task (pick this one):**

> "Go through the PDFs in `C:\Demo\invoices`, pull each vendor name and total into a new Excel sheet, sum the column, then write a short summary in Notepad."

Why this exact task:
- **Three native Windows apps** (File Explorer → Excel → Notepad) = unmistakably "operates the machine," not a browser trick.
- **Zero logins, zero risk** — it's a folder of dummy PDFs you make yourself. No sensitive pixels on screen.
- **Business-shaped** — invoices + Excel is a pain every viewer with a company *feels*. Cold traffic converts on pain it recognizes.

**How to run it like a pro:**
1. Stage the folder with 5 clean dummy invoices (make them yourself, big readable totals).
2. Open Excel and File Explorer first (targets active = higher success).
3. OBS recording. Full desktop.
4. Run the task. When it fails — and it will, this is the frontier — read the session log, simplify the phrasing, re-run. Every retry is tuning your future product prompt.
5. Grind it until you get **3 flawless runs in a row.** That's your bar. One lucky run is a demo; three clean runs is a product seed.

**Reality check (say it out loud):** cross-app desktop automation is the hardest game in AI right now — the big benchmarks show even top systems failing most arbitrary multi-app tasks. That's not bad news. That's *why* a bulletproof narrow demo is worth money while giants chase generality. General vision, narrow reliability. That's the OrphicOS doctrine.

✅ **Exit criteria:** 3-for-3 clean runs of the invoice demo, recorded.

---

## Phase 3 — Wrap the OrphicOS shell (Day 6–9)

**Goal:** turn "a research repo I run in a terminal" into "OrphicOS, the product." Four pieces, all thin:

1. **Command bar** — a minimal always-on-top window (start stupid-simple: Python + a tiny FastAPI + a webview, or even a tray app) with one text box: *"What should the machine do?"* Submits the task to UFO².
2. **Live "watch it work" view** — stream UFO's session log + screenshots into a scrolling feed. This is the Devin/Cursor-style magic window; it's 80% of the perceived value. UFO already writes everything to disk — you're just rendering it live. Bonus: UFO² has a Picture-in-Picture mode that runs the agent in an isolated virtual desktop so the user keeps their mouse. Surfacing that = "it works in the background while you live your life" — pure tagline fuel.
3. **The red button** — global hotkey (e.g. Ctrl+Alt+Space) that kills the agent process instantly. V0 kill switch = process termination. Crude, honest, effective. Enterprise buyers ask about this in the first five minutes.
4. **Replay + approval** — a "Show me what it did" screen (render the saved session log) and a config flag: pause and ask before destructive actions (delete, send, submit). Gate at your orchestrator layer: intercept those verbs in the plan, require a click.

**Branding pass:** dark theme, the arcane vibe, "OrphicOS" wordmark in the corner of the live view — so every clip anyone screenshots carries the brand. The log window *is* the marketing asset.

✅ **Exit criteria:** the invoice demo runs end-to-end from the OrphicOS window — typed there, watched there, killable there, replayable there.

---

## Phase 4 — Go local: UI-TARS on the 5090 (Day 10–12)

**Goal:** flip on the moat. *"Your data never leaves the building."*

UI-TARS is the purpose-built open computer-use vision model — trained on UI screenshots and action sequences, so it natively understands ribbons, taskbar, Settings, File Explorer. It's rated the strongest open-source option for Windows desktop control, and it sings on a local GPU (sub-second actions vs 3–5s on CPU).

**The architecture (and the honest wrinkle):**
- UFO² keeps running **natively on Windows** — it must, it's driving the Windows UI.
- The **model server** runs beside it: quantized UI-TARS-7B served via vLLM inside **WSL2 or Docker Desktop with GPU passthrough** on the same rig (vLLM is Linux-native; WSL2 is the standard way to run it on a Windows box). Expose an OpenAI-compatible endpoint on localhost.
- Point UFO's model config at `http://localhost:<port>` per its local-model guide.

**Phased honestly:**
- 4a. Serve UI-TARS-7B (quantized) → verify tokens flow.
- 4b. Wire UFO to the local endpoint → re-run the invoice demo. Expect tuning; grounding models swap less cleanly than chat models. Budget a full day of fiddling — that day *is* the moat being poured.
- 4c. Local only — no cloud fallback. If a workflow won't hold up on the local model, bulletproof a narrower workflow instead of phoning home.

**Why this is the business:** every cloud agent (ChatGPT agent, Mariner, Devin) ships your screen to their servers. OrphicOS on a 5090 doesn't. For companies with contracts, compliance, and paranoia — which is to say, companies with *money* — that's not a feature, that's the reason to buy. And nobody in your audience can copy it without your hardware obsession. The Mac Studio hunt? Same story, bigger models, later chapter.

✅ **Exit criteria:** invoice demo completes with **zero external API calls** (watch the network tab, brag about it on camera).

---

## Phase 5 — The launch (Day 13–14)

**Video description, first line, non-negotiable:**
```
👉 Join the inner circle: t.me/rawaiyt
```

**Cold open (first 8 seconds — footage already rolling, agent already working):**

> "I typed one sentence into my Windows PC — 'process these invoices' — then I left to make coffee. This is my screen while I was gone. No macros. No cloud. The AI is running on the graphics card two feet from my desk. This is OrphicOS. The machine works. You don't."

**Video structure (10–12 min):**
1. **0:00–0:08** — cold open above, over the flawless demo run.
2. **0:08–1:30** — the hook expanded: "everyone shows you browser agents; this drives the *whole computer*" + the PiP shot of you using the mouse while the agent works its own desktop. Crowd-stopper.
3. **1:30–7:00** — the build story: UFO² install, first fails (keep the bloopers — failure → triumph is the oldest story that sells), the 3-for-3 run.
4. **7:00–10:00** — the moat: task manager open, GPU spiking, network silent. "It never phoned home."
5. **10:00–end** — CTA: "First access goes to the Telegram. Link's the first line of the description."

**Clips for X (@HarakiriInu, feed the n8n pipeline):** the 8-sec cold open; the PiP dual-desktop shot; the "network: silent, GPU: screaming" shot. Ten posts a day need ammo — this video is a crate of it.

**Landing page (orphicos.ai) — three lines, one button:**
> **OrphicOS — the machine works. You don't.**
> An AI operator for Windows. It runs your apps, your files, your desktop — locally, on your GPU. Your data never leaves the building.
> [ Get early access → Telegram ]

**First money (start before the code is pretty):**
- **Done-for-you automation sprints** — you run OrphicOS on a client's workflow (their machine or a VM you control), flat fee, 1–2 weeks. Sells the *outcome*, validates willingness-to-pay in days, and every engagement teaches you which workflows to productize.
- **Early-access waitlist** in Telegram → your proven high-ticket DM close. Same funnel that printed for LowCapCharter, new product on the shelf.
- Self-serve subscription only after 3 humans have paid for sprints. Revenue defines the roadmap, not the other way around.

---

## The Doctrine (tape this part up)

1. **General vision, narrow reliability.** The brand promises the whole machine; each release bulletproofs a handful of workflows. That's how a solo operator beats teams stuck at 15% success on "anything."
2. **Never fork the engine.** Ride UFO² upstream (MIT), build OrphicOS *around* it. Merge their improvements for free while competitors maintain forks.
3. **The log is a feature.** Replay + audit = enterprise trust = pricing power.
4. **Local is the moat.** The 5090 isn't a gaming card anymore. It's the product.
5. **Ship the video with the software.** Distribution is the asset the funded competitors don't have. Every phase above produces footage — waste none of it.

*You give the word. It does the work in the dark.* 🕶️
