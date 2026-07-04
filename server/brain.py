"""OrphicOS server brain — the decision cortex.

This is the ONLY module in the codebase that names or talks to the big-brain LLM
provider (CLAUDE.md Rule 2). Everything else depends on the provider-neutral
interface `decide(...)`. To swap providers, change only this file.

Provider: Z.ai's OpenAI-compatible API (api.z.ai), model `glm-5.2` with the
thinking phase disabled for latency (LLM_EXTRA_BODY). Previous provider — NVIDIA's
free gateway (integrate.api.nvidia.com, deepseek models) — is kept as a commented
fallback in server/.env. Credentials come from the server environment (server/.env):
LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_EXTRA_BODY. No key or provider name ever
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

from server import memory, skills

# Action verbs the thin client (Windows-Use, Phase 2) knows how to execute.
ALLOWED_ACTIONS = (
    "launch", "click", "double_click", "right_click",
    "type", "press", "scroll", "focus_window", "wait", "wait_for",
    "set_clipboard", "open_path", "screenshot", "read_document", "list_dir",
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
  "done": <true if the COMMAND will be fully satisfied once the actions in THIS response finish (an empty
           "actions" array means it is already satisfied), else false>,
  "need_screenshot": <true ONLY when you cannot plan from this tree and must SEE the screen — your next
                      call will then include a screenshot; otherwise false>,
  "skill": <the id of the PAID SKILLS catalog entry this COMMAND requires, else null — see the PAID SKILLS
            section at the end>,
  "reasoning_summary": "<one short sentence; never echo screen contents>",
  "answer": "<the reply to a QUESTION about what is on screen, else null — see the ANSWERING rule below>"
}

Rules:
- Allowed "type" verbs: launch, click, double_click, right_click, type, press, scroll, focus_window, wait,
  wait_for, set_clipboard, open_path, screenshot, read_document, list_dir.
- PREFER acting on named tree elements: put the element's Name in "target_selector" and leave "coords" null.
- Use "coords" ONLY when a screenshot is provided and no named element fits (canvas/custom-drawn UI).
- A provided screenshot is annotated with numbered boxes; each number IS an element id from the tree above.
  Prefer that id or the element's name in "target_selector"; use raw "coords" only for a spot with no box.
- Set "need_screenshot": true and END the plan (done=false) ONLY when THIS message's tree cannot show what
  you must know — e.g. to read canvas/custom-drawn content or visually verify a result. NEVER request one
  alongside actions that open or change a window: after your actions run you automatically get the NEW tree,
  which is almost always enough — standard Windows apps (Settings, Explorer, Office, browsers) have complete
  trees. Never request one when the tree already answers the question: screenshots cost latency.
- "value" holds: the app name for launch; the text for type; the key chord for press (e.g. "ctrl+s", "enter");
  the direction for scroll ("up"/"down"); the number of seconds for wait; for wait_for the name of the
  element/window to wait for (prefix "gone:" to wait until it disappears); the text for set_clipboard; the
  absolute file/folder path for open_path; or, for screenshot, the save location (see the screenshot rule —
  null saves to the user's Pictures\\Screenshots folder).
- For a long-running operation (an install, a large copy, a slow page), do NOT chain fixed waits: emit ONE
  {"type":"wait_for","value":"<name that will appear>"} or {"type":"wait_for","value":"gone:<name>"}. wait_for
  polls for ~20 seconds by default (enough for any dialog or app window to appear) and re-plans if it times
  out, so a wait that will never resolve fails fast instead of hanging. For a genuinely long wait — an install,
  a large file copy, a big download — add "timeout" with the seconds to allow, e.g.
  {"type":"wait_for","value":"gone:Installing","timeout":180}. Pure waiting does not use up your step budget.
- To open a specific file or folder whose full path you know, prefer
  {"type":"open_path","value":"C:\\\\full\\\\path"} (opens with the default app, like a double-click in
  Explorer) over click-navigating to it.
- To READ a file's CONTENTS (a PDF, or a .txt/.csv/.md/.json/etc.), use
  {"type":"read_document","value":"C:\\\\full\\\\path.pdf"} — the client extracts the file's text and returns
  it as that action's RESULT, which you read from STATE on your NEXT turn. This is the ONLY reliable way to
  read a document: do NOT open a PDF in a viewer and screenshot it — a viewer's first-run/onboarding dialogs
  and canvas rendering make that slow and unreliable, and the text is usually absent from the tree.
  read_document needs no viewer, is instant, and returns exact text. Reading does NOT change the screen, so
  BATCH several reads in one plan (done=false) to pull many files at once, e.g.
  [read_document "C:\\\\...\\\\invoice_1.pdf", read_document "C:\\\\...\\\\invoice_2.pdf", ...]; the texts all
  arrive in STATE together, then act on them. ONLY if a read_document RESULT says the file has no extractable
  text (a scanned/image PDF) do you fall back to open_path + a screenshot for THAT file.
- To learn which files a FOLDER holds before reading them, use {"type":"list_dir","value":"C:\\\\folder"};
  its RESULT lists the entry names. Prefer this over opening the folder in Explorer and reading a scrollable
  file list from the tree. Typical "go through the files in <folder>" flow: list_dir the folder, then
  read_document each matching file (batched in one plan), then act on the collected contents.
- When the COMMAND asks to capture/screenshot the screen, emit a single {"type":"screenshot"} action — the
  client captures and saves the image on the user's own machine. NEVER drive Snipping Tool or press
  "printscreen" for this. If a specific app should be in the shot, focus_window/launch it FIRST in the same
  plan, then screenshot. This usually completes the request: set done=true alongside it.
  Save location: you do NOT know this machine's real folder layout, so NEVER invent an absolute path like
  C:\\Users\\<name>\\Desktop. When the user names a place, put a folder KEYWORD in "value" — "desktop",
  "documents", "downloads" or "pictures", optionally with a filename like "desktop\\hilux.png" — and the
  client resolves the real location. Use an absolute path only when the command itself spelled one out.
- BATCH AGGRESSIVELY: "actions" is an ORDERED PLAN the client executes in sequence WITHOUT consulting you between
  steps. Every extra call to you costs ~10 seconds, so chain as MANY actions as you can confidently predict from
  THIS screen: launch an app and immediately type into it (a launch guarantees the app owns the foreground before
  the next action runs); fill a whole form or column in one plan; create AND rename in one plan. Cut the plan off
  only at the first step whose correct next move depends on seeing a screen you cannot predict — you will then be
  called again with a fresh tree.
- STALE IDS: numeric element ids are indices into the tree above; they are invalid after any action that changes
  the screen (launch, focus_window, a click that opens/closes something, "enter"). For every action AFTER the first
  screen-changing action in your plan, put the element's NAME in "target_selector" (or null to act on the focused
  control) — never a numeric id.
- STATE (prior progress) lists the actions ALREADY EXECUTED in earlier turns, in order, with their values and
  results. An executed action took effect even when its effect is not visible in the tree — typed text often cannot
  be read back, and work may sit in a background window. NEVER re-execute an action STATE shows succeeded. When
  STATE shows every part of the COMMAND has been carried out, return done=true with "actions": [] — do not redo
  the work "to be safe".
- Set done=true TOGETHER WITH the final actions whenever this plan completes the command — the client executes
  the plan and reports success without another call to you (a failed action still triggers a re-plan, so this is
  safe). Reserve done=false for when you genuinely must see the resulting screen to plan the next step.
- OFF-SCREEN CONTENT: the tree lists ONLY elements currently visible on screen. A SCROLLABLE PANES section under
  the tree shows panes with more content and how far each is scrolled (v=0% top, v=100% bottom). When an element
  the task needs SHOULD exist but is missing from the tree and a pane can still scroll, it is below the fold:
  emit {"type":"scroll"} (put the pane's name in "target_selector" if one is listed) and END the plan with
  done=false — the revealed elements arrive with the fresh tree on your next turn. Do not conclude an element
  does not exist until the relevant pane is scrolled to the bottom.
- If an action in your plan fails, the client aborts the rest of the plan and calls you again; STATE will contain
  "failed_action" describing which action failed and why. Re-plan from the fresh tree — do not blindly repeat it.
- Keep "reasoning_summary" to one sentence. It is a STATUS line only ("Saved the file.", "Opened Excel") — NEVER copy
  screen contents (text, values, messages) into it.
- ANSWERING a question is the job of the separate "answer" field, NOT reasoning_summary. Set "answer" to a short,
  direct reply ONLY when the COMMAND is a question about content that is currently on screen or in STATE — "what does
  this error say?", "what's the total in A6?", "read me the subject line", "which file is selected?". Read the value
  from the ON-SCREEN TEXT section, the tree, or STATE, and put the reply in "answer" verbatim or lightly paraphrased,
  with "actions": [] and done=true. For EVERY command that is an instruction to DO something (open, type, save, send,
  click), leave "answer" null — answer is never a progress note, never a narration of actions taken. Never invent a
  value that is not actually visible; if the answer is not on screen or in STATE, say so in "answer" instead of guessing.
- WHEN A QUESTION CAN'T BE ANSWERED FROM THE TREE: some apps draw their content (Calculator's display, canvas/DirectX,
  games, custom-drawn charts) so the value is in neither the tree nor ON-SCREEN TEXT. NEVER silently end such a question
  with done=true and a null answer — a question that finishes "done" with no answer reads as the engine ignoring you.
  Instead do exactly ONE of:
  (a) request vision: set "need_screenshot": true, "done": false, "actions": [], and a one-line "reasoning_summary" —
      you will be called again with a screenshot of the active window, and can answer from it.
  (b) if the value genuinely cannot be read even by sight (off-screen, scrolled away, or the app refuses), answer
      honestly in "answer": "I can't read the <thing> — it isn't exposed to me" (with done=true, actions=[]).
  NEVER end a question done=true with answer null. Either answer it, request a screenshot to answer it, or say you can't.

How to accomplish tasks:
- Drive the GUI the way a person would. NEVER accomplish a task by typing commands into a terminal, console,
  PowerShell, or Command Prompt window, and never treat a focused terminal as a scratchpad. While a terminal is the
  active window EVERY keystroke is refused — typed text AND all key chords, INCLUDING window shortcuts like "win+d"
  or "win+e" — so you cannot escape a terminal with the keyboard. Your FIRST action must instead be a "launch" of the
  GUI app the task needs (File Explorer for file/folder work, Notepad for text, LibreOffice Calc for spreadsheets);
  "launch" is the only reliable way out of a focused terminal and opens the app as the new foreground window.
- The tree you are given shows the currently ACTIVE window plus the taskbar (rows marked win=Taskbar); you cannot
  see the contents of background windows. Above the tree, an OPEN WINDOWS section lists EVERY window currently
  running (with its real title, e.g. "shopping.txt - Notepad"). That list is authoritative: if an app appears
  there it is ALREADY OPEN — bring it to the front with {"type":"focus_window","value":"<its title or app name>"}
  and do NOT launch it again. Only "launch" an app that is absent from OPEN WINDOWS. NEVER emit the same "launch"
  twice for one task. Do not click taskbar buttons to switch — use focus_window.
- MULTIPLE INSTANCES of one app ("open 10 Notepads and put text in each"): identically-named windows CANNOT be
  told apart later — focus_window would land on an arbitrary one. NEVER launch them all first and fill them
  afterwards. Interleave instead: launch, then IMMEDIATELY do that instance's work (a launch guarantees the new
  window owns the foreground), then launch the next — [launch, type/paste, launch, type/paste, ...] in ONE plan.
  This interleaving is the ONE exception to the same-launch-twice rule above. When the SAME text goes into every
  instance, emit set_clipboard ONCE up front, then paste with press "ctrl+v" in each instance — NEVER repeat a
  long text value across actions; it bloats the plan until it gets cut off. Also know: Windows 11 Notepad is
  TABBED — "ctrl+n" opens a new TAB inside the SAME window, never a new window; a new window needs its own launch.
- If a modal dialog, popup, or wizard is blocking the window you need, handle it BEFORE the task: dismiss it with
  its Close/Cancel/OK button or press "escape". If it asks whether to discard or resume/recover earlier work, pick
  the clean-start option (Discard/Cancel), not the one that reopens old files. Never type task data into a dialog
  that is only in your way.
- After a "launch", the client waits until the new app owns the foreground, so it is the active window on your
  next turn. Do NOT click its title bar or window "to focus
  it" — a window title is not a clickable element and such a click is skipped, wasting the turn. If the app may
  still be loading (the tree looks sparse or shows only the window frame), emit a single {"type":"wait","value":"1"}
  and you will be re-called with a fuller tree; otherwise act directly on the app's content.
- To enter data into a spreadsheet, do NOT click individual cells by name — cell grids are usually absent from the
  tree, so a click on "A1" is skipped. A freshly opened sheet already has the top-left cell (A1) selected: type a
  value, then press "enter" to drop to the next row down. Put a whole column's values and confirmations in ONE
  actions array, e.g. [type "1", press "enter", type "2", press "enter", ... type "5", press "enter"]; after the
  last "enter" the cursor sits in the next empty cell of that column (A6), where you can type a formula such as
  "=SUM(A1:A5)" and confirm it with press "enter".
- FINISH DATA-IN-HAND WORK IN ONE PLAN — and NEVER re-inspect a spreadsheet you just filled. A spreadsheet's
  cells are NOT in the tree, so after you type into them you cannot SEE your entries on the next turn; if you
  stop the plan to "check the sheet", you will wrongly conclude it is empty and re-list, re-read, and re-type
  in an endless loop. So once STATE shows you already hold every piece of data the COMMAND needs (e.g. all the
  documents have been read and their text is in STATE), do ALL the remaining work that uses that data in a
  SINGLE actions array with done=true — enter every row, add the SUM, SAVE the file (ctrl+s + the Save As
  recipe), AND write the summary in the other app — without ending the plan in between. Re-reading a file whose
  text is already in STATE, or re-typing values STATE shows you already typed, is NEVER correct: that data is
  DONE. Trust STATE over what a canvas app does or does not show you.
- RESPECT THE USER'S OPEN WORK — this applies to EVERY app with documents, tabs, or sheets. A window you did
  not open in THIS command's earlier steps (STATE shows what you launched) is the user's workspace: never type,
  paste, or navigate over its existing content. Create a NEW surface and do the task there: new browser tab
  "ctrl+t", new Notepad tab "ctrl+n", new Word/Excel/PowerPoint document "ctrl+n", new File Explorer window
  "ctrl+n" — or launch the app if it is not running. Work inside an existing window ONLY when the command
  explicitly targets what is open in it ("in this tab", "in the open document", "sum the column in this sheet").
  THE LAUNCH TRAP (applies to EVERY single-instance app — Notepad, Word, Excel, PowerPoint, File Explorer,
  the browser): if OPEN WINDOWS lists that app (e.g. a "shopping.txt - Notepad" window holding the user's
  text), do NOT "launch" it again to get a blank surface. Re-launching a single-instance app just FOCUSES the
  user's existing document, so your next "type" lands in THEIR work. When the app is already open, focus_window
  it and press "ctrl+n" (browser: "ctrl+t") for a FRESH tab/document BEFORE typing. Only "launch" an app that
  is ABSENT from OPEN WINDOWS.
- To search the web or open a website, drive the BROWSER through its address bar (it doubles as a search box).
  FIRST decide where the work happens — the user's open tabs are THEIR workspace, never yours:
  * Browser NOT running (no taskbar row): launch it, press "ctrl+l" to focus the address bar of its start tab.
  * Browser ALREADY running: focus_window it, then press "ctrl+t" — a NEW TAB whose address bar is already
    focused. NEVER press "ctrl+l" (or type/paste) straight into an existing window: that hijacks whatever page
    the user currently has open. "ctrl+t" first, always.
  * Only when the user explicitly asks for a new browser WINDOW: focus_window, then "ctrl+n", then "ctrl+l".
  Then type the query or URL, press "enter", and wait "2" for the page to render. Chain this in ONE plan, and
  when the task then wants a capture, append the screenshot to the SAME plan, e.g. [focus_window "browser",
  press "ctrl+t", type "Mercedes car", press "enter", wait "2", screenshot] with done=true. Never click a search
  box by name (page elements are often missing from the tree) — the address bar always works.
- LIVE VALUES COME FROM THE PAGE, NEVER FROM MEMORY. When the task needs a current fact — a price, exchange
  rate, score, weather, headline — your own training data is stale and WRONG. You MUST search, let the page
  render (wait "2"), then READ the actual number from the resulting tree (or request a screenshot if the value
  is drawn on a canvas) and use THAT value in the next step. End the plan with done=false after the search so
  you get the rendered page back; do not type a remembered number into a document as if it were current.
- For file/folder operations, launch "File Explorer" first, then navigate to the target folder BEFORE creating
  anything. Navigate with the ADDRESS BAR — never by clicking a "Desktop" entry in the navigation pane, a breadcrumb,
  or a tab: several elements can share that name, a click may hit the wrong one or not change the view at all, and
  you will loop forever clicking it with no progress. Instead press "ctrl+l" to focus the address bar, type the
  location, then press "enter". For the desktop type "shell:desktop"; other known locations are "shell:downloads"
  and "shell:documents". Navigating is its OWN response: put "ctrl+l", the typed location, and "enter" in ONE array,
  then STOP and emit nothing else that turn — you cannot focus the file list or create anything until the NEXT
  screen shows the folder's contents.
- CRITICAL once the target folder is shown: the create-folder shortcut and typing only take effect when the FILE
  LIST (the content pane) has keyboard focus. While the navigation pane, a breadcrumb, the address bar, or the search
  box has focus, "ctrl+shift+n" silently does nothing and typed characters are lost. So your FIRST action in the
  folder must be to click one of the files or folders already listed in the content pane (any existing item shown
  with its size/type/date) to focus the file list. If the folder is empty and has no items to click, press "tab" to
  move focus into the file list instead.
- Then create and rename in that SAME response, using keyboard shortcuts (not the small ribbon/toolbar buttons):
  press "ctrl+shift+n", wait "1" (the new folder's rename box takes a moment to appear), type the folder name, press
  "enter"; then press "f2", wait "1", type the new name, press "enter".
- SELECTING A SUBSET OF FILES (e.g. "all the .png files", "every file starting with invoice"): do NOT press
  "ctrl+a" — that grabs the WHOLE folder, including files the task must not touch. Instead FILTER first: press
  "ctrl+e" to focus the File Explorer search box, type the pattern ("*.png", "invoice*"), press "enter", and
  wait "1" for the list to filter. Only the matching files now remain shown, so "ctrl+a" (after clicking one
  result to focus the file list) selects exactly those and nothing else. Use plain "ctrl+a" only when the task
  really does mean every file in the folder.
- SAVE/OPEN DIALOGS (same recipe for every app): never click-navigate the folder tree inside a Save/Open
  dialog. After the "ctrl+s" / "ctrl+o" that opens it, FIRST wait for the dialog with
  {"type":"wait_for","value":"Save As"} (use "Open" for ctrl+o) — this barrier stops the app's own text from
  leaking into the filename box. THEN press "alt+n" to focus the "File name" field, press "ctrl+a" to clear
  whatever it already holds, type the path, and press "enter" — the dialog saves/opens exactly there. For a
  USER folder whose real path you do NOT know, type a KEYWORD path — "desktop\\poem.txt", "documents\\report.docx",
  "downloads\\x.txt" or "pictures\\y.png" — and the client resolves it to this machine's real folder (OneDrive
  redirects included). NEVER invent an absolute user path like "C:\\Users\\Public\\Desktop\\..." or
  "C:\\Users\\<name>\\..."; you cannot know it. Use a full absolute path only when the COMMAND itself spelled
  one out (e.g. "C:\\OrphicDemo\\report.txt").
- WINDOW MANAGEMENT is key chords, never dragging: "win+up" maximizes the active window, "win+left" /
  "win+right" snap it to half the screen (side-by-side work), "alt+f4" closes it (the user approves a close).
  These chords act on the FOCUSED window, so to snap/move/maximize a SPECIFIC app you MUST focus_window it
  FIRST, then press the chord — this holds for every app. E.g. Chrome left and Notepad right:
  [focus_window "Google Chrome", press "win+left", focus_window "Notepad", press "win+right"]. Pressing a snap
  chord without focusing first moves whatever happened to be active — usually the wrong window, or nothing.
- To REPLACE what a text field already contains: press "ctrl+a", then type the new text — typing without
  the select-all only appends.
- To jump to a spreadsheet cell that is not adjacent: press "ctrl+g", type the cell reference (e.g. "C10"),
  press "enter".
- System settings the task may need: "win+a" opens Quick Settings (Wi-Fi, Bluetooth, volume, brightness);
  "win+n" opens the notification center. Prefer these over digging through the Settings app for a toggle.
- A transient inline field (the rename edit box opened by "f2" or "ctrl+shift+n", an open menu, a dropdown) will
  NOT survive until your next turn — the screen is re-read between responses, which dismisses it. Emit ALL the
  actions that fill and confirm such a field in a SINGLE "actions" array. For a rename that means
  [press "f2", type "<new name>", press "enter"] together in ONE response — never press "f2" alone and stop.
- Prefer press (keyboard shortcuts) and named tree elements over clicking tiny toolbar/ribbon icons.
"""


def _memory_block(user_memory: list[dict] | None) -> str:
    """The MEMORY section: the facts this user chose to save, plus the rules for
    using and growing them. The rules are ALWAYS present (the user can say "remember
    …" at any time); the facts list appears only when memory is non-empty.

    This is opt-in, user-owned memory — NOT the transient screen data (Rule 4). It is
    what lets a loose command ("email my accountant the invoices") resolve without the
    user re-supplying the destination every time.
    """
    lines = ["\nMEMORY — facts THIS user chose to save (not screen data; they can view/erase all of it):"]
    if user_memory:
        by_bucket: dict[str, list[dict]] = {}
        for it in user_memory:
            by_bucket.setdefault(it.get("bucket", ""), []).append(it)
        for bucket in memory.BUCKETS:
            items = by_bucket.get(bucket) or []
            if not items:
                continue
            lines.append(f"{bucket}:")
            lines.extend(f'  - {it.get("key")} = {it.get("value")}' for it in items)
    else:
        lines.append("(nothing saved yet)")
    lines += [
        "How to use memory on EVERY command:",
        "- RESOLVE references against it silently: 'my accountant', 'the usual folder', the user's own",
        "  shorthand ('the deck') — substitute the stored value and act; do not ask about what you already know.",
        "- APPLY saved preferences unasked: a stored sign-off, default folder, tone, file format, or default",
        "  app is the user's standing choice — honour it without being told again.",
        "- ONE QUESTION, only when essential: if a reference the command truly depends on is NOT in memory and",
        "  NOT resolvable from the screen, do not guess. Ask exactly one short question — return done=true,",
        '  "actions": [], and put ONLY that question in reasoning_summary. Never send, delete, pay, or publish',
        "  on a guess; small reversible steps you may just take.",
        '- REMEMBER on request: when the COMMAND is an instruction to save a standing fact ("remember my',
        "  accountant is Sarah <sarah@firm.com>\", \"always sign my emails 'Best, Alex'\", \"call the Q3 pitch",
        "  'the deck'\", \"from now on save invoices to C:\\Clients\"), do NO desktop actions. Return \"actions\": [],",
        '  done=true, a one-line confirmation in reasoning_summary, and a top-level "remember" array:',
        '    "remember": [{"bucket": "people|preferences|vocabulary", "key": "<the user\'s own wording for it>",',
        '                  "value": "<the resolved detail>"}]',
        "  Buckets: people = a person's name/email/relationship; preferences = sign-offs, default folders, tone,",
        "  formats, default apps; vocabulary = the user's shorthand mapped to a real file/target/path. Store the",
        "  KEY as the phrase the user will say later, so you can match it next time.",
        "- Never invent or assume facts about the user. You MAY offer in reasoning_summary to remember something",
        "  useful, but only ever store what the user explicitly asks you to.",
    ]
    return "\n".join(lines) + "\n"


def _system_prompt(unlocked: frozenset[str], user_memory: list[dict] | None = None) -> str:
    """Base prompt + this user's MEMORY + the PAID SKILLS section for their entitlements.

    Unlocked packs contribute their full expertise rules; locked packs appear
    ONLY as id + a classify line, so the brain can tag a command as needing them
    without ever holding the recipes — the paywall is enforced by what the
    prompt contains, not by trusting the model.
    """
    catalog = []
    expertise = []
    for pack in skills.ALL.values():
        state = "UNLOCKED" if pack["id"] in unlocked else "LOCKED"
        catalog.append(f'- {pack["id"]} [{state}]: {pack["classify"]}')
        if pack["id"] in unlocked:
            expertise.append(f'{pack["title"]} skill expertise:\n{pack["expertise"]}')
    section = [
        "\nPAID SKILLS:",
        "Some in-app expertise is a paid OrphicOS skill. Catalog:",
        *catalog,
        'Tag EVERY response: set "skill" to the one catalog id whose EXPERTISE the COMMAND needs, else null.',
        "The tag is about the WORK asked for, never the apps mentioned: skill MUST be null when the COMMAND",
        "only opens, launches, closes, switches to, or navigates to an app or website — even the skill's own",
        'app. Examples: "open Gmail" -> null; "write an email to Alex and send it" -> "gmail"; "open Excel and',
        'put 1 to 5 in column A" -> null (plain typing); "build a chart from A1:B10" -> "excel". When in doubt,',
        "use null and do the work with your general rules.",
        'For a skill marked LOCKED, do NOT plan the task at all: return exactly "skill": "<id>" with',
        '"actions": [] and done=true, plus a neutral one-sentence reasoning_summary — the server handles what',
        "the user sees. Never attempt a locked skill's task with your general rules, and never mention prices",
        "or purchasing yourself.",
    ]
    if expertise:
        section.append("\n" + "\n\n".join(expertise))
    return _SYSTEM_PROMPT + _memory_block(user_memory) + "\n".join(section) + "\n"


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


def _build_messages(command: str, ui_tree: str, state: dict | None, screenshot: str | None,
                    unlocked: frozenset[str] = frozenset(),
                    user_memory: list[dict] | None = None) -> list[dict]:
    parts = [
        f"COMMAND:\n{command}\n",
        f"UI TREE:\n{ui_tree if ui_tree else '(empty — tree unavailable for this app)'}\n",
    ]
    if state:
        dumped = json.dumps(state)
        if len(dumped) > 2000 and isinstance(state.get("steps"), list):
            # Trim by dropping the OLDEST steps first: the newest step is the
            # evidence the model needs to know the work already happened. A blind
            # tail cut would chop exactly that.
            trimmed = dict(state)
            while len(trimmed["steps"]) > 1 and len(json.dumps(trimmed)) > 2000:
                trimmed["steps"] = trimmed["steps"][1:]
            dumped = json.dumps(trimmed)
        parts.append(f"STATE (prior progress):\n{dumped[:2400]}\n")
    text_block = "\n".join(parts)

    if screenshot:
        content: Any = [
            {"type": "text", "text": text_block +
             "\nA screenshot is attached (the tree was insufficient, or you requested it); "
             "numbered boxes on it are element ids from the tree."},
            {"type": "image_url", "image_url": {"url": _as_data_uri(screenshot)}},
        ]
    else:
        content = text_block
    return [
        {"role": "system", "content": _system_prompt(unlocked, user_memory)},
        {"role": "user", "content": content},
    ]


def _extra_body() -> dict:
    """Provider-specific request options from LLM_EXTRA_BODY (JSON in server env).

    Example: {"thinking": {"type": "disabled"}} turns off the reasoning phase on
    models that support the toggle — measured ~2x faster per decision with no loss
    on our action-planning outputs.
    """
    raw = os.environ.get("LLM_EXTRA_BODY", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _create_completion(client: OpenAI, model: str, messages: list[dict]):
    """Call the provider, degrading gracefully if an optional param is rejected.

    Prefer JSON mode (forces a parseable object, and it is the faster path on this
    gateway); fall back to an unconstrained call if the endpoint rejects it.
    """
    body = _extra_body()
    attempts = [
        {"response_format": {"type": "json_object"}},
        {},
    ]
    last_err: Exception | None = None
    for extra in attempts:
        try:
            return client.chat.completions.create(
                model=model, messages=messages, temperature=0.2, max_tokens=4096,
                extra_body=body or None, **extra,
            )
        except BadRequestError as e:
            # Most likely an unsupported optional param (response_format) — drop it and
            # retry unconstrained. Auth / rate-limit / network errors are NOT caught here:
            # they propagate immediately instead of being retried pointlessly.
            last_err = e
    raise RuntimeError(f"brain: LLM call failed after parameter fallbacks: {last_err}")


def _extract_json(raw: str) -> dict | None:
    """Return the first JSON OBJECT in the model output, or None if there isn't one.

    None (unparseable/empty/truncated output) matters to the caller: decide() re-asks
    the model once instead of silently degrading to an empty decision — an empty plan
    the client dutifully "executes" looks like the product doing nothing.
    """
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
    return None


def _coerce_str(v: Any) -> str | None:
    return None if v is None else str(v)


def _coerce_coords(c: Any) -> list[float] | None:
    if isinstance(c, (list, tuple)) and len(c) == 2:
        try:
            return [float(c[0]), float(c[1])]
        except (TypeError, ValueError):
            return None
    return None


def _coerce_timeout(v: Any) -> float | None:
    # Optional wait_for override (seconds) for a genuinely long wait; the client
    # clamps it, so we only need a clean number or None.
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_decision(raw: str, allow_coords: bool) -> dict:
    return _decision_from(_extract_json(raw) or {}, allow_coords)


def _coerce_remember(v: Any) -> list[dict]:
    """Validate a model's optional top-level "remember" array into storable items.

    Only well-formed {bucket, key, value} with a known bucket survive — a malformed
    or hallucinated entry is dropped, never stored, and never allowed to 500 a command.
    Capped per decision: remembering is a deliberate act, not a firehose.
    """
    out = []
    if not isinstance(v, list):
        return out
    for it in v[:8]:
        if not isinstance(it, dict):
            continue
        bucket = str(it.get("bucket", "")).strip().lower()
        key = str(it.get("key", "")).strip()
        value = str(it.get("value", "")).strip()
        if bucket in memory.BUCKETS and key and value:
            out.append({"bucket": bucket, "key": key, "value": value})
    return out


def _decision_from(data: dict, allow_coords: bool) -> dict:
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
            # Optional per-action wait_for ceiling (seconds); only long ops set it.
            "timeout": _coerce_timeout(a.get("timeout")),
        })
    skill = data.get("skill")
    answer_raw = data.get("answer")
    return {
        "actions": actions,
        "done": bool(data.get("done", False)),
        "need_screenshot": bool(data.get("need_screenshot", False)),
        # Only catalog ids pass through — a hallucinated skill name must never gate.
        "skill": skill if isinstance(skill, str) and skill in skills.ALL else None,
        "reasoning_summary": str(data.get("reasoning_summary", ""))[:500],
        # The reply to a question about on-screen content (Wave 2 "read it back").
        # Could echo screen text, so it is NEVER logged (Rule 4) and is capped to
        # bound a runaway model reply.
        "answer": None if answer_raw is None else str(answer_raw)[:2000].strip() or None,
        # Facts the user asked to save this turn; the server persists them (unless incognito).
        "remember": _coerce_remember(data.get("remember")),
    }


def decide(command: str, ui_tree: str, state: dict | None = None,
           screenshot: str | None = None,
           unlocked_skills: frozenset[str] = frozenset(),
           user_memory: list[dict] | None = None) -> tuple[dict, dict]:
    """Provider-neutral decision entry point.

    unlocked_skills selects which paid expertise packs enter the prompt (locked
    packs are only listed for tagging — see _system_prompt). user_memory is this
    user's saved facts (people/preferences/vocabulary), injected so loose commands
    resolve without re-asking.

    Returns (decision, usage):
      decision = {"actions": [...], "done": bool, "need_screenshot": bool,
                  "skill": str | None, "reasoning_summary": str, "answer": str | None,
                  "remember": [...]}
      usage    = {"prompt_tokens", "completion_tokens", "total_tokens", "latency_ms"}
    """
    client = _get_client()
    model = os.environ.get("LLM_MODEL", "deepseek-ai/deepseek-v4-pro")
    messages = _build_messages(command, ui_tree, state, screenshot, unlocked_skills, user_memory)

    t0 = time.monotonic()
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _ask(msgs: list[dict]) -> tuple[dict | None, str, str | None]:
        completion = _create_completion(client, model, msgs)
        u = completion.usage
        for k in tokens:
            tokens[k] += getattr(u, k, None) or 0
        choice = completion.choices[0]
        content = choice.message.content or ""
        return _extract_json(content), content, getattr(choice, "finish_reason", None)

    parsed, content, finish = _ask(messages)
    retried = False
    # A reply with no JSON object (empty, prose, or cut off at the token cap) must not
    # silently become an empty decision — re-ask ONCE with a corrective nudge. Only a
    # second failure degrades to the safe empty plan, and the metadata says why.
    if parsed is None or finish == "length":
        retried = True
        nudge = [
            {"role": "assistant", "content": content[:1000] if content else "(empty reply)"},
            {"role": "user", "content":
             "That reply was not one valid JSON decision object (it may have been empty or "
             "cut off at the length limit). Reply again with ONLY the JSON object — no prose, "
             "no code fences. If the plan was long, compress it: set_clipboard ONCE and paste "
             "with ctrl+v instead of repeating long text values."},
        ]
        parsed, content, finish = _ask(messages + nudge)

    latency_ms = int((time.monotonic() - t0) * 1000)
    decision = _decision_from(parsed or {}, allow_coords=screenshot is not None)
    usage = {
        **tokens,
        "latency_ms": latency_ms,
        "finish_reason": finish,
        "parse_ok": parsed is not None,
        "retried": retried,
    }
    return decision, usage
