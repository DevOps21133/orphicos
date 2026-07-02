# OrphicOS — Runbook

**"OrphicOS — the machine works. You don't."**

OrphicOS runs a Windows 11 machine by voice or text. The user's PC is a thin
client (the hands); our server is the brain. `CLAUDE.md` holds the full build
spec and the non-negotiable rules — this runbook is the operational quick-start.

## The split (memorize)
- **client/** — thin app on the user's Windows 11 PC. Captures voice/text, reads
  the UI Automation tree, executes actions. **No AI model, no LLM key, ever.**
  Talks only to `SERVER_BASE` with a per-user OrphicOS token.
- **server/** — the brain. Receives `{command, ui_tree}`, calls the big-brain LLM
  (key lives only here), returns `{actions}`. Zero-retention of screen data.

## Golden wall
`server/` holds the LLM key + provider name. `client/` knows only its own brand,
`SERVER_BASE`, and the user's token. Guard that wall on every commit.

## Session start (every time)
1. Read `CLAUDE.md` and this runbook.
2. Run `scripts/check_env.ps1`; report status incl. `SERVER_BASE` reachability.
3. State current phase, last DONE checkpoint, today's target.
4. Small commits toward the phase DONE list. Keep the client/server wall clean.
5. End session: 5-line status (phase, done, blocked, next, human actions needed).

## Environment check
```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
```
The `SERVER_BASE reachable` check is expected to fail until Phase 1 hosts the
brain — that does not fail the overall check.

## Phase status
- **Phase 0 — Environment & Skeleton:** repo layout, `.gitignore`, config
  examples, `THIRD-PARTY-NOTICES.txt`, `check_env.ps1`; client/server wall
  established.  ← current
- Phase 1 — The Server Brain (`server/app.py`, `brain.py`, `auth.py`)
- Phase 2 — Thin Client Loop (Windows-Use, tree-first)
- Phase 3 — Voice Input (local STT, push-to-talk, confirm gate)
- Phase 4 — The Money Demo (cross-app, voice + text)
- Phase 5 — The OrphicOS Shell (product skin, kill switch, approval gate)
- Phase 6 — Package & Ship (Windows installer, sign-in, zero setup for users)

## Data & honesty
Screen data travels to the server for a single decision, then is dropped
(zero-retention). Approved framing everywhere: **"Processed securely on OrphicOS
servers. Encrypted in transit. Your screen data is never stored."** Never claim
"runs locally," "never leaves your machine," or "fully offline."
