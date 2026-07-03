# OrphicOS — Positioning & Messaging

## Positioning statement (one line)

OrphicOS lets you operate your Windows 11 PC by voice or text: you state what should happen, and the machine performs the steps in your real applications — visibly, stoppably, and with anything risky gated behind your confirmation.

---

## Messaging pillars

Every proof point below is true of the product today unless marked "(future)".

### 1. Say it. It happens.

Voice or text, one command path, real Windows applications.

Proof points:
- You type a command in the command bar, or hold a hotkey and speak; local speech-to-text fills the same bar. One path, two front doors.
- Spoken commands are never auto-submitted: you read the transcription and confirm before anything runs (confirm gate).
- Works on real, native Windows apps — Notepad, File Explorer, Excel, Calculator have been driven end-to-end — not a fixed set of API integrations.
- Cross-app tasks: one command can span reading files, filling a spreadsheet, and writing a summary. (The multi-app demo task is the internal proof bar; cite it only once it has clean recorded runs.)

### 2. It reads the interface, not just the pixels.

Precision from the same structure Windows exposes to screen readers.

Proof points:
- The client reads the Windows UI Automation tree — the named buttons, fields, and windows of every app — and acts on named elements, the way assistive technology does.
- A screenshot is captured only as a fallback when an app exposes no usable tree; tree-first keeps actions precise and fast.
- Nothing to configure: no model selection, no API keys, no setup screens. Install, sign in, speak. The thin client executes; the OrphicOS brain (our hosted service) decides.

### 3. You stay at the helm.

Software that operates your computer must be watchable, stoppable, and cautious by construction.

Proof points:
- Live log: every step and result streams to the screen as it happens.
- Kill switch: a STOP button plus a global hotkey (Ctrl+Alt+Space) halts the action loop instantly, even if the window is buried.
- Approval gate: risk verbs — delete, remove, send, submit, purchase, uninstall, format — require explicit confirmation, checked both on your command and on any action the brain returns.
- Confirm gate on voice: transcribed speech never executes without your explicit go.

### 4. Honest data handling.

Proof points:
- Approved claim, verbatim, everywhere: **"Processed securely on OrphicOS servers. Encrypted in transit. Your screen data is never stored."**
- Voice audio is transcribed on your device; only the resulting text and a compact map of the interface are sent. The microphone stream never leaves the machine. (This is the only "on-device" claim we may make.)
- Zero-retention by design: the server holds the interface map in memory for the single decision, then drops it. Never written to disk or logs.

---

## Audiences (who buys first)

1. **Accessibility users** — people with motor impairments for whom mouse/keyboard is a barrier. Voice Access does dictation and grid clicking; OrphicOS executes whole tasks from one sentence. Highest need, strongest word-of-mouth, and it keeps our claims honest: this audience tests them daily.
2. **RSI sufferers** — programmers, writers, and office workers rationing their hands. They already pay for Dragon and Talon; a task-level voice layer is a direct upgrade for the non-typing parts of their day.
3. **Power users / early adopters** — people who automate with AutoHotkey and PowerToys and will tolerate early-access rough edges for leverage. They generate the demo clips and the build-in-public audience.
4. **Small-business operators** — one person doing invoicing, data entry, and file wrangling across Excel, PDFs, and email. The cross-app demo is aimed at them; they arrive after the first three audiences prove reliability.

---

## What we NEVER say

Banned outright:
- **Any LLM provider or model name**, anywhere a user, customer, or journalist could see it — UI, logs shown to users, README, marketing, error messages, interviews. It is always "OrphicOS" or "the OrphicOS brain/engine."
- **"Runs locally," "fully offline," "never leaves your machine," "0 bytes to the cloud"** — false; screen data travels to our server. The only approved data claim is the verbatim sentence in Pillar 4. The only permitted local claim is about voice audio transcription.
- **Fake traction** — invented user counts, waitlist numbers, revenue, logos, testimonials. Early access means early access.
- **Capability inflation** — "works with any app," "100% accurate," "replaces your assistant/employee," "fully autonomous." We say what has run cleanly and mark everything else "(future)".
- **"Your data is never sent anywhere"** or any privacy phrasing stronger than the approved claim.

Jargon guidance:
- Avoid "AI agent," "agentic," "autonomous agent," "copilot," "LLM," "prompt" in user-facing copy. This is hype-cycle vocabulary and it names the wrong thing: OrphicOS is not autonomous — the user commands, watches, and can stop it. Say "OrphicOS," "the machine," "the OrphicOS brain."
- The user gives a **command**, not a prompt. The user **speaks**; the machine **works**. (Full glossary: naming.md.)
- No hype adjectives: "revolutionary," "magical," "game-changing," "10x." Describe what it does; let the demo carry the excitement.
