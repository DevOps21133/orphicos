# OrphicOS Capability Roadmap — Broad Windows 11 Coverage

*Synthesis of a 3-track deep-research pass (2026-07-03): (A) Windows app-class survey —
where tree-first perception breaks; (B) code audit of our verb set vs. real workflows;
(C) action-space mining of Anthropic Computer Use, OpenAI Operator, Microsoft UFO2,
OmniParser, Skyvern, browser-use, pywinauto, and the windows-use engine itself.*

Current verb set: `launch, click, double_click, right_click, type, press, scroll,
focus_window, wait, screenshot`. Proven live: browser search chains, screenshot capture,
folder creation, Gmail compose with gated send.

---

## Headline findings

1. **The vision fallback almost never fires.** `Perception.is_empty` triggers only on a
   *zero-node* tree (`client/perceive/perceiver.py:108`), but canvas/DirectX/Java apps
   still expose 2–3 titlebar buttons — so the brain loops blind on a chrome-only tree
   instead of getting a screenshot. Every "tree fails" app class funnels into this hole.
2. **The brain is blind to text.** We serialize only `interactive_nodes`; windows-use
   already computes `dom_informative_nodes` (readable text) and `scrollable_nodes`
   (scroll % per pane) and we throw both away (`perceiver.py:105`). The decision contract
   also has no `answer` field — so "what does this error say?" is doubly impossible.
   This is half of "human-parity PC control."
3. **Latent batching bug:** `scroll` is missing from `_SCREEN_CHANGING`
   (`client/loop.py:25-26`), so a batched `[scroll, click "Accept"]` resolves the click
   against the *pre-scroll* snapshot and fails.
4. **The engine ships capabilities we don't expose:** `drag`, `move` (hover),
   `multi_select`, `multi_edit`, `resize_app`, `type(clear=)`, middle-click,
   `get_annotated_screenshot` (set-of-mark labeled screenshot), and full UIA patterns
   (Invoke/Value/Toggle/ExpandCollapse/ScrollIntoView) — all thin-wrapper distance away.
5. **UAC is a guaranteed dead end.** Elevation prompts run on the secure desktop — no UIA,
   no SendInput, ever (Windows security design). Any installer task dies there today with
   an opaque stall. We can't automate it (and shouldn't), but we must *detect* it and hand
   off to the user.
6. **Proven-value techniques from the field:** UFO2's per-action pre-flight validation cut
   LLM calls 51.5%; Skyvern's plan-validator lifted WebVoyager success 45%→85.8%; Skyvern's
   plan cache replays learned flows with zero LLM calls (directly attacks our #1 pain,
   speed). OmniParser is off the table — its V2 detector weights are AGPL (Rule 9).

## App-class coverage verdict (tree-first)

| Works | Partial | Fails today |
|---|---|---|
| Win32, WPF, UWP/WinUI (Settings, Store), Office ribbon, Chrome/Edge ≥138, Firefox, File Explorer | WinForms (owner-drawn), Electron (Slack/Discord/Spotify — lazy a11y), Excel grid/Word canvas (A1-hack only), tray/notification flyouts | Canvas/DirectX (games, CAD, Photoshop docs), Java Swing, UAC/secure desktop, elevated windows (UIPI), terminals (by design) |

DPI scaling is already handled (PerMonitorAwareV2). Multi-monitor vision coords have an
offset bug (screenshot spans all screens, coords applied raw — `actor.py:60-61`).

---

## Build waves

### Wave 1 — Quick wins (all S effort; fixes + prompt packs)

| # | Item | Type | Why |
|---|---|---|---|
| 1.1 | Add `scroll` to `_SCREEN_CHANGING` | bug fix (1 line) | batched scroll→click is silently broken |
| 1.2 | Serialize `scrollable_nodes` (+ scroll %) and add scroll-to-reveal prompt rule ("target absent + pane scrollable → scroll, done=false") | perception | highest-frequency failure: elements below the fold don't exist to the brain |
| 1.3 | Fix vision-fallback trigger: fire on *insufficient* tree (chrome-only heuristic) AND let the brain request it via a `need_screenshot` flag in the decision contract | perception | converts every "fails" app class into "degrades gracefully" |
| 1.4 | Use `get_annotated_screenshot` (numbered set-of-mark boxes) for the fallback; brain answers with a label id, not raw coords | perception | UFO2-grade grounding, method already ships in the engine |
| 1.5 | `wait_for` verb: poll for element/window appear/disappear client-side (≤120 s, kill-switch aware, no brain calls while polling); pure waits don't burn `max_steps` | code | installers/page loads currently burn a ~10 s brain call per 10 s wait |
| 1.6 | `set_clipboard` verb + auto paste-instead-of-type for >200-char text | code | long email/doc bodies currently type char-by-char (minutes, corruption-prone); clipboard becomes a data bus |
| 1.7 | `open_path` verb (`os.startfile` / Start-Process, optional app + args) | code | "open C:\Reports\Q2.pdf" costs 3–5 round trips today |
| 1.8 | Prompt pack: file dialogs (type full path into "File name:", alt+n), window management (win+left/right/up, alt+f4 — and gate alt+f4/win+l), Excel Go-To (ctrl+g), shell surfaces (win+a/win+n/win+b), text-editing recipes (ctrl+a, shift+end, ctrl+f) | prompt | free coverage for everyday flows |

### Wave 2 — "Read it back" (M) — unlocks the question-answering half of the product

✅ **2.1 + 2.2 SHIPPED (2026-07-04).** The perceiver now serializes
`dom_informative_nodes` as a capped `ON-SCREEN TEXT` section, and the decision
contract carries an `answer` field — surfaced in the shell, scoped the no-echo
rule to `reasoning_summary` only, never logged (Rule 4). 2.3 and 2.4 remain open.

| # | Item | Type | Status |
|---|---|---|---|
| 2.1 | Serialize `dom_informative_nodes` as a capped `TEXT:` section of the payload | perception | ✅ done |
| 2.2 | Add `answer` field to the decision contract, rendered + spoken in the shell (scope the no-echo rule to `reasoning_summary` only). Zero-retention unchanged: answer passes through, never stored | contract | ✅ done |
| 2.3 | `extract` verb: return a target subtree's text via UIA TextPattern/ValuePattern into STATE | code | ✅ done |
| 2.4 | Multi-monitor vision fix: capture active monitor only, translate returned coords by its offset | code | open |

**2.3 detail:** `extract` reads a control's current value via UIA patterns
(ValuePattern → TextPattern → cached Name). Two targeting modes: by tree name
(`target_selector`) for named fields whose value isn't shown, and by AutomationId
(`value='automation_id:<id>'`) for tree-invisible canvas displays like Calculator's
result readout (`CalculatorResults`). Returns the text as the action RESULT into
STATE — the same gather-then-answer flow as `read_document`. Closes the gap where
the clock test proved tree-reading works but Calculator's canvas display could
only be reached via the slower, ambiguous vision fallback. Committed `fc456da`.

### Wave 3 — Interaction completeness (S–M)

| # | Item |
|---|---|
| 3.1 | `drag` verb `{from, to}` (files, sliders, reordering) — engine `drag`/`move` exist |
| 3.2 | `hover` verb (move + 0.7 s dwell) for tooltips/hover menus |
| 3.3 | `modifier` field on clicks (ctrl/shift) + expose `multi_select` — Explorer multi-select |
| 3.4 | Selector grammar `Type:Name` / `Name#2` + resolution prefers active window; fixes duplicate-"OK" targeting |
| 3.5 | `menu_select`: right_click + snapshot popup locally + fuzzy-pick item in one client-side step (transient-UI fix) |
| 3.6 | Scroll amount control (`down:10`) + `ScrollItemPattern.ScrollIntoView` for named targets |

### Wave 4 — Robustness & speed (M–L)

| # | Item | Field evidence |
|---|---|---|
| 4.1 | UIA pattern invocation first (Invoke/Toggle/SetValue/Select), mouse as fallback — immune to occlusion/animation; atomic field writes | pywinauto, UFO2 |
| 4.2 | Pre-flight validation: before each queued action, verify target resolves + IsEnabled/IsVisible; early-exit *before* acting wrong → longer safe batches | UFO2: −51.5% LLM calls |
| 4.3 | UAC/secure-desktop detection → pause loop + shell event "confirm the Windows security prompt" → resume. (UIAccess-signed binary is the long-term fix; deferred with code signing) | Windows security design |
| 4.4 | Post-done validator: re-perceive and confirm the command is satisfied (only when a plan had failures — protects latency) | Skyvern: 45%→85.8% |
| 4.5 | Server-side plan cache: store successful plans as metadata (command signature + app + actions — Rule-4 clean), inject as STATE hint on repeat commands | Skyvern/UFO2; attacks the #1 pain |
| 4.6 | Electron a11y wake: on sparse tree in a Chromium-class window, send a UIA priming query, wait ~1 s, re-read once before vision fallback | Slack/Discord/Spotify are daily drivers |
| 4.7 | Window-title list of ALL open apps in every payload (+ later `peek_window` for a named background tree) | multi-app tasks are blind today |
| 4.8 | Brain-declared safety: optional `requires_confirmation: reason` per action, gated in the shell *in addition to* the regex (catches "empty the recycle bin") | OpenAI Operator protocol |

### Deliberately deferred

- **Office COM hybrid verbs** (UFO2 puppeteer: −58.5% steps) — high value, L effort, revisit after Wave 2.
- **Picture-in-Picture isolated desktop** (agent works while user keeps mouse) — killer differentiator, XL effort.
- **Java Access Bridge** — consumer demand unproven; Wave 1.3 vision fallback covers it.
- **OmniParser grounding** — AGPL detector weights, Rule 9 blocker. Use the LLM's native vision on annotated screenshots instead.
- **Terminal driving** — stays refused by design; a sandboxed allowlisted command verb behind the approval gate is a possible future.

---

## Recommended order

**Wave 1 first, in one sprint** — it's all S-effort, kills two real bugs (1.1, fallback
trigger), and ships four new verbs that remove the most common dead ends. Then Wave 2,
because "read it back" is the missing half of the product promise and everything in it
builds on Wave 1's perception work. Waves 3–4 re-prioritize after live telemetry shows
which failures users actually hit.
