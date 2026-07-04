"""Execute the brain's actions on the live Windows desktop.

Maps the server's action contract — {type, target_selector|coords, value} — onto
windows-use's headless `Desktop` methods (click / type / scroll / shortcut / app).
No LLM here: the *decide* step already happened on the server; this only acts.

Element targeting: the brain returns `target_selector` (the element's Name, as shown
in the tree it received) or, on the vision fallback, raw `coords`. We resolve a name
to the matching interactive node's id in the CURRENT snapshot, then ask the Desktop
for that element's live centre coordinates.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from client._engine import Desktop, escape_text_for_sendkeys, uia
from client.act._focus_guard import foreground_console_label

# A dialog/window that WILL appear shows in ~1s; only genuinely long operations
# (installs, big copies, downloads) need to wait longer. So the default is short —
# a wait_for that won't resolve (e.g. "Save As" after a ctrl+s that saved silently
# because the file already had a name) fails fast and lets the brain re-plan, instead
# of hanging for two minutes. A plan that knows its wait is long passes an explicit
# "timeout" (seconds) to raise the ceiling for that one action, clamped to the max.
_WAIT_FOR_TIMEOUT = 20.0
_WAIT_FOR_TIMEOUT_MAX = 300.0
_WAIT_FOR_POLL = 0.5
_CLIPBOARD_TYPE_THRESHOLD = 200  # chars; longer text is pasted, not typed key-by-key

# Windows known-folder GUIDs (KNOWNFOLDERID). Only THIS machine knows where these
# really live (OneDrive redirects Desktop/Documents/Pictures away from the profile
# root), so the server's brain names folders by keyword and we resolve them here.
_KNOWN_FOLDER_GUIDS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
}


def _known_folder(alias: str) -> Path:
    """Resolve a known-folder alias ('desktop', ...) to its real location."""
    try:
        import ctypes
        from ctypes import wintypes
        guid_buf = ctypes.create_unicode_buffer(_KNOWN_FOLDER_GUIDS[alias])
        guid = (ctypes.c_byte * 16)()
        ctypes.oledll.ole32.CLSIDFromString(guid_buf, ctypes.byref(guid))
        out = ctypes.c_wchar_p()
        ctypes.oledll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), wintypes.DWORD(0), None, ctypes.byref(out))
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return Path.home() / alias.capitalize()


def _rebase_known_folder(raw: str) -> Path:
    """Anchor a save path onto the real user folder it names, if it names one.

    The brain cannot know this machine's real profile layout, so it may say just
    "desktop", "desktop\\shot.png", or guess a wrong absolute path like
    C:\\Users\\Public\\Desktop\\shot.png. If ANY component is a known-folder
    alias, everything from that component on is rebased onto the real folder;
    otherwise the path is used as given.
    """
    parts = Path(raw).expanduser().parts
    for i, part in enumerate(parts):
        alias = part.lower()
        if alias in _KNOWN_FOLDER_GUIDS:
            return _known_folder(alias).joinpath(*parts[i + 1:])
    return Path(raw).expanduser()


# A typed value that BEGINS with a known-folder keyword + path separator is a save
# path headed for a Save/Open dialog (e.g. "desktop\\poem.txt"), not prose. The brain
# emits this form for EVERY app's save dialog because it cannot know the real path;
# the client resolves it here so ordinary typed text is never touched.
_KEYWORD_PATH_RE = re.compile(
    r"^(?:" + "|".join(_KNOWN_FOLDER_GUIDS) + r")[\\/]", re.IGNORECASE)


def _resolve_typed_path(text: str) -> str:
    """Rewrite a keyword save path to this machine's real absolute path; else pass through."""
    stripped = text.strip()
    if _KEYWORD_PATH_RE.match(stripped):
        return str(_rebase_known_folder(stripped))
    return text


# Single-instance document/browser apps: launching one again while it is ALREADY
# open just focuses the user's existing document, so the next "type" lands in their
# work (the "launch trap"). When the target is one of these AND a window of it is
# already open, the client focuses it and opens a guaranteed-fresh surface instead —
# a new browser TAB (ctrl+t) or a new document/tab (ctrl+n). This protection is
# deterministic: it holds no matter what the brain planned. Keyword is matched as a
# whole word against both the app name and the open window titles.
_FRESH_SURFACE = {
    "notepad": "ctrl+n",
    "wordpad": "ctrl+n",
    "word": "ctrl+n",
    "excel": "ctrl+n",
    "powerpoint": "ctrl+n",
    "libreoffice calc": "ctrl+n",
    "libreoffice writer": "ctrl+n",
    "libreoffice impress": "ctrl+n",
    "libreoffice": "ctrl+n",
    "chrome": "ctrl+t",
    "edge": "ctrl+t",
    "firefox": "ctrl+t",
    "brave": "ctrl+t",
    "opera": "ctrl+t",
}

# The brain names the app the USER said ("Excel"); only the CLIENT knows what is
# actually installed on THIS machine (the same reason known folders resolve here).
# When a requested app is not found, fall back to the installed equivalent before
# aborting. This machine — and the project's office recipe — use LibreOffice; a
# machine with real Excel launches Excel and never reaches this map. Matched as a
# whole word, so "word" does not catch "wordpad".
_APP_ALIASES = {
    "excel": "LibreOffice Calc",
    "word": "LibreOffice Writer",
    "powerpoint": "LibreOffice Impress",
}

# The engine's launch/switch return a human string, not a status code. These
# fragments mean it could NOT start/find the app — we must abort the whole plan
# then, so the following type/press actions never fire into the wrong window
# (e.g. a failed "launch Excel" must not type a formula into the Calculator).
_ACTION_FAILED_MARKERS = ("not found", "no windows found", "could not", "failed")


def _looks_failed(result: str) -> bool:
    """True when a launch/switch result string reports the app could not be started
    or found — the signal to abort the batch rather than act on the wrong window."""
    low = result.lower()
    return any(marker in low for marker in _ACTION_FAILED_MARKERS)


class ActionError(RuntimeError):
    """An action could not be executed (unknown type, or no matching element)."""


def _refuse_if_console(what: str) -> None:
    """Guard blind keystrokes: OrphicOS never drives a terminal, so if a console has
    focus these keys would run as shell commands (outside the kill switch). Skip them."""
    console = foreground_console_label()
    if console is not None:
        raise ActionError(
            f"refused to send {what} into a focused console ({console}); "
            "no GUI target is focused")


class Actor:
    def __init__(self, desktop: Desktop,
                 should_stop: Callable[[], bool] | None = None) -> None:
        self._desktop = desktop
        # The kill switch must be able to break a long wait_for poll, not just
        # the gaps between actions — the loop passes its should_stop through.
        self._should_stop = should_stop

    def execute(self, action: dict) -> str:
        """Run one action; return a short human-readable result for the live log."""
        atype = str(action.get("type") or "").strip()
        handler = getattr(self, f"_do_{atype}", None)
        if handler is None:
            raise ActionError(f"unsupported action type: {atype!r}")
        try:
            return handler(action, action.get("value"))
        except ActionError:
            raise
        except Exception as e:  # noqa: BLE001 — deliberate: any engine failure becomes skippable
            # windows-use reads a control's live BoundingRectangle at act time; a control
            # that went stale during the brain round-trip raises comtypes.COMError (not an
            # ActionError). Convert it so the loop SKIPS this action and re-perceives,
            # rather than crashing the whole run on a half-finished desktop.
            raise ActionError(f"{atype} failed: {type(e).__name__}: {e}") from e

    # --- element resolution ------------------------------------------------
    def _resolve_loc(self, action: dict) -> tuple[int, int] | None:
        coords = action.get("coords")
        if isinstance(coords, (list, tuple)) and len(coords) == 2:
            return int(coords[0]), int(coords[1])
        sel = action.get("target_selector")
        if not sel:
            return None
        label = self._label_for(str(sel))
        if label is None:
            raise ActionError(f"no on-screen element matches {sel!r}")
        return self._desktop.get_coordinates_from_label(label)

    def _label_for(self, sel: str) -> int | None:
        """Resolve a target_selector (element id or Name) to an interactive-node id."""
        state = self._desktop.desktop_state
        nodes = (state.tree_state.interactive_nodes or []) if state and state.tree_state else []
        if not nodes:
            return None
        s = sel.strip()
        if s.isdigit() and 0 <= int(s) < len(nodes):
            return int(s)
        low = s.lower()
        named = [(i, (n.name or "").strip()) for i, n in enumerate(nodes)]
        for i, name in named:                                   # exact, case-insensitive
            if name.lower() == low:
                return i
        for i, name in named:                                   # prefix
            if name and name.lower().startswith(low):
                return i
        for i, name in named:                                   # substring
            if name and low in name.lower():
                return i
        return None

    def _scrollable_center(self, sel: str) -> tuple[int, int] | None:
        """Resolve a scroll target against the snapshot's SCROLLABLE panes by name."""
        state = self._desktop.desktop_state
        tree = state.tree_state if state else None
        low = sel.strip().lower()
        if not low or tree is None:
            return None
        for node in (getattr(tree, "scrollable_nodes", None) or []):
            name = (getattr(node, "name", "") or "").strip().lower()
            if name and (low in name or name in low):
                center = getattr(node, "center", None)
                if center is not None:
                    return int(center.x), int(center.y)
        return None

    def _require_loc(self, action: dict) -> tuple[int, int]:
        loc = self._resolve_loc(action)
        if loc is None:
            raise ActionError("action needs a target element or coordinates")
        return loc

    # --- action handlers ---------------------------------------------------
    def _do_launch(self, action: dict, value) -> str:
        name = value or action.get("target_selector")
        if not name:
            raise ActionError("launch needs an app name in 'value'")
        name = str(name)
        # LAUNCH TRAP: if this is a single-instance doc/browser app that is ALREADY
        # open, launching it again just focuses the user's document and the next
        # "type" clobbers their work. Focus it and open a fresh surface instead —
        # a deterministic guarantee, independent of what the brain planned.
        chord = self._fresh_surface_for(name)
        if chord is not None:
            self._desktop.app(mode="switch", name=name)
            self._ensure_foreground(name)
            self._desktop.shortcut(chord)
            sleep(0.4)  # let the new tab/document become the active surface
            surface = "tab" if chord == "ctrl+t" else "document"
            return f"{name} already open — opened a fresh {surface}"
        result = str(self._desktop.app(mode="launch", name=name))
        if _looks_failed(result):
            # The app the brain named may not exist on THIS machine (it said "Excel";
            # the box has LibreOffice). Try the installed equivalent before giving up.
            alias = self._alias_for(name)
            if alias is not None:
                alt = str(self._desktop.app(mode="launch", name=alias))
                if not _looks_failed(alt):
                    self._ensure_foreground(alias)
                    return f"{name} not installed — launched {alias} instead"
            # Abort the plan: a launch that never started the app must not let the
            # following actions run against whatever window currently has focus
            # (that is how "type 1..5" ended up feeding the shell's own command bar).
            raise ActionError(f"could not launch {name}: {result}")
        self._ensure_foreground(name)
        return result

    def _alias_for(self, name: str) -> str | None:
        """The installed-equivalent app to try when `name` was not found — e.g. the
        machine has LibreOffice, not the Microsoft Office app the brain named."""
        low = name.lower()
        for keyword, target in _APP_ALIASES.items():
            if re.search(rf"\b{re.escape(keyword)}\b", low):
                return target
        return None

    def _fresh_surface_for(self, name: str) -> str | None:
        """The 'new surface' chord (ctrl+t / ctrl+n) if `name` is a single-instance
        doc/browser app that already has a window open; else None (launch normally)."""
        low = name.lower()
        keyword = next(
            (k for k in _FRESH_SURFACE if re.search(rf"\b{re.escape(k)}\b", low)), None)
        if keyword is None or not self._app_window_open(keyword):
            return None
        return _FRESH_SURFACE[keyword]

    def _app_window_open(self, keyword: str) -> bool:
        """True if any open window's title contains `keyword` as a whole word.
        Uses the snapshot the brain just planned against (active window + all open
        windows), so 'launch Excel' with a '... - Excel' window open is caught."""
        state = getattr(self._desktop, "desktop_state", None)
        if state is None:
            return False
        titles = [state.active_window.name if state.active_window else ""]
        titles += [getattr(w, "name", "") or "" for w in (getattr(state, "windows", None) or [])]
        pat = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
        return any(pat.search(t) for t in titles if t)

    def _ensure_foreground(self, app_name: str, timeout: float = 6.0) -> None:
        """The brain's contract says a launched app IS the foreground window, but the
        engine's launch returns before the window exists, and focus can bounce back to
        the previous window (e.g. the browser hosting the shell). Without this, the
        next perceive shows the OLD window and the brain relaunches in a loop. Poll
        until the app owns the foreground; halfway through, try an explicit switch."""
        want = app_name.strip().lower()
        deadline = monotonic() + timeout
        tried_switch = False
        while monotonic() < deadline:
            sleep(0.4)
            state = self._desktop.get_state()
            active = (state.active_window.name if state.active_window else "") or ""
            if want in active.lower():
                return
            if not tried_switch and (deadline - monotonic()) < timeout / 2:
                tried_switch = True
                try:
                    self._desktop.app(mode="switch", name=app_name)
                except Exception:  # noqa: BLE001 — window may not exist yet; keep polling
                    pass
        # Never fail the launch over focus: the loop re-perceives and the brain
        # can still recover with focus_window.

    def _do_focus_window(self, action: dict, value) -> str:
        name = value or action.get("target_selector")
        if not name:
            raise ActionError("focus_window needs a window name")
        result = str(self._desktop.app(mode="switch", name=str(name)))
        if _looks_failed(result):
            # Abort the plan: if the target window was not found, the next chord or
            # keystroke (a snap, a type) would hit the wrong window. Let the brain
            # re-plan against the real screen instead.
            raise ActionError(f"could not focus {name}: {result}")
        # Settle the foreground before the plan's next action. focus_window is what
        # precedes a snap chord (win+left/right) or a type, and those act on whatever
        # window is CURRENTLY foreground — if focus has not finished switching, the
        # chord snaps the wrong window. Polling until the target truly owns the
        # foreground makes the following action reliable.
        self._ensure_foreground(str(name))
        return result

    def _do_click(self, action: dict, value) -> str:
        loc = self._require_loc(action)
        self._desktop.click(loc, button="left", clicks=1)
        return f"clicked {loc}"

    def _do_double_click(self, action: dict, value) -> str:
        loc = self._require_loc(action)
        self._desktop.click(loc, button="left", clicks=2)
        return f"double-clicked {loc}"

    def _do_right_click(self, action: dict, value) -> str:
        loc = self._require_loc(action)
        self._desktop.click(loc, button="right", clicks=1)
        return f"right-clicked {loc}"

    def _do_type(self, action: dict, value) -> str:
        text = _resolve_typed_path("" if value is None else str(value))
        loc = self._resolve_loc(action)
        if len(text) > _CLIPBOARD_TYPE_THRESHOLD and self._paste(loc, text):
            return (f"pasted {len(text)} chars into {loc}" if loc is not None
                    else f"pasted {len(text)} chars into focused control")
        if loc is not None:
            self._desktop.type(loc, text=text)
            return f"typed into {loc}"
        # No target -> type into whatever control currently has focus.
        _refuse_if_console("typed text")
        uia.SendKeys(escape_text_for_sendkeys(text), interval=0.01, waitTime=0.05)
        return "typed into focused control"

    def _paste(self, loc: tuple[int, int] | None, text: str) -> bool:
        """Deliver long text via clipboard+ctrl+v — key-by-key typing is slow and
        drops characters in laggy apps. Returns False when the clipboard write
        fails, so _do_type falls back to keystrokes."""
        if loc is None:
            _refuse_if_console("pasted text")  # same rule as typing into focus
        try:
            if not uia.SetClipboardText(text):
                return False
        except Exception:  # noqa: BLE001 — clipboard may be held by another app
            return False
        if loc is not None:
            self._desktop.click(loc, button="left", clicks=1)  # focus the target
        self._desktop.shortcut("ctrl+v")
        return True

    def _do_press(self, action: dict, value) -> str:
        if not value:
            raise ActionError("press needs a key chord in 'value' (e.g. 'ctrl+s')")
        _refuse_if_console(f"key chord {value!r}")
        self._desktop.shortcut(str(value))
        return f"pressed {value}"

    def _do_scroll(self, action: dict, value) -> str:
        # A scroll target may name a SCROLLABLE pane (not an interactive element),
        # and a stale/wrong name should never fail a scroll — the focused window
        # is always a sane place to scroll. So resolution degrades, never raises.
        try:
            loc = self._resolve_loc(action)  # optional; None scrolls the focused window
        except ActionError:
            loc = self._scrollable_center(str(action.get("target_selector") or ""))
        direction = str(value).lower() if value else "down"
        if direction not in ("up", "down", "left", "right"):
            direction = "down"
        stype = "horizontal" if direction in ("left", "right") else "vertical"
        self._desktop.scroll(loc=loc, type=stype, direction=direction, wheel_times=3)
        return f"scrolled {direction}"

    def _do_screenshot(self, action: dict, value) -> str:
        """Capture the screen and save it ON THIS MACHINE (the user's own PC).

        The image never travels to the server — this is a local deliverable the
        user asked for, unlike the Rule 5 vision fallback in client/perceive.
        `value` may name an absolute .png path; default is Pictures\\Screenshots.
        """
        png = self._desktop.get_screenshot(as_bytes=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        def _default_path() -> Path:
            # Real Pictures folder (OneDrive redirects it away from the profile root),
            # same known-folder resolution the brain's keyword paths use. Resolved
            # lazily so an explicit save path never triggers an unused folder lookup.
            return _known_folder("pictures") / "Screenshots" / f"orphic_screenshot_{stamp}.png"

        if value:
            path = _rebase_known_folder(str(value))
            if path.suffix.lower() != ".png":  # a folder was given -> name the file inside it
                path = path / f"orphic_screenshot_{stamp}.png"
        else:
            path = _default_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png)
        except OSError:
            # Never fail the run over an unwritable save path (the brain can only
            # guess paths) — fall back to our folder and say where it really went.
            default = _default_path()
            default.parent.mkdir(parents=True, exist_ok=True)
            default.write_bytes(png)
            return (f"screenshot saved to {default} "
                    f"(requested location {path} was not writable)")
        return f"screenshot saved to {path}"

    def _do_wait(self, action: dict, value) -> str:
        try:
            seconds = float(value) if value is not None else 1.0
        except (TypeError, ValueError):
            seconds = 1.0
        seconds = max(0.0, min(seconds, 10.0))  # cap so the loop stays responsive
        sleep(seconds)
        return f"waited {seconds:g}s"

    def _do_wait_for(self, action: dict, value) -> str:
        """Poll until an element/window whose name contains `value` appears —
        or disappears, with a "gone:" prefix. Long operations (installs, big
        copies, slow pages) need this instead of chained fixed waits, and can
        raise the short default ceiling via an action "timeout" (seconds). A
        timeout raises ActionError so the brain re-plans instead of the run hanging."""
        spec = str(value or action.get("target_selector") or "").strip()
        want_gone = spec.lower().startswith("gone:")
        needle = (spec[5:] if want_gone else spec).strip().lower()
        if not needle:
            raise ActionError("wait_for needs an element/window name in 'value'"
                              " (prefix 'gone:' to wait for it to disappear)")
        timeout = self._wait_timeout(action.get("timeout"))
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if self._should_stop is not None and self._should_stop():
                return f"wait for {spec!r} interrupted by stop"
            if self._name_present(needle) != want_gone:
                return f"{needle!r} {'disappeared' if want_gone else 'appeared'}"
            sleep(_WAIT_FOR_POLL)
        raise ActionError(f"wait_for {spec!r} timed out after {timeout:g}s")

    @staticmethod
    def _wait_timeout(raw) -> float:
        """The wait_for ceiling for one action: the short default unless the plan
        asked for longer, clamped to the max so a bad value can't hang the run."""
        if raw is None:
            return _WAIT_FOR_TIMEOUT
        try:
            return max(1.0, min(float(raw), _WAIT_FOR_TIMEOUT_MAX))
        except (TypeError, ValueError):
            return _WAIT_FOR_TIMEOUT

    def _name_present(self, needle: str) -> bool:
        """Case-insensitive substring match over the fresh snapshot: the active
        window's title, any listed windows, and the interactive element names."""
        state = self._desktop.get_state()
        names = []
        if state.active_window:
            names.append(state.active_window.name or "")
        for w in getattr(state, "windows", None) or []:
            names.append(getattr(w, "name", "") or "")
        tree = state.tree_state
        for node in (tree.interactive_nodes or []) if tree else []:
            names.append(getattr(node, "name", "") or "")
        return any(needle in name.lower() for name in names if name)

    def _do_set_clipboard(self, action: dict, value) -> str:
        if value is None:
            raise ActionError("set_clipboard needs text in 'value'")
        text = str(value)
        if not uia.SetClipboardText(text):
            raise ActionError("could not write to the clipboard")
        return f"clipboard set ({len(text)} chars)"

    def _do_open_path(self, action: dict, value) -> str:
        """Open a file/folder with its default handler — the reliable equivalent
        of double-clicking it in Explorer, without any click-navigation. Also
        accepts an http(s) URL, which opens in the default browser (the server's
        skill-checkout upsell uses this); other URL schemes are refused."""
        raw = str(value or action.get("target_selector") or "").strip()
        if not raw:
            raise ActionError("open_path needs an absolute file/folder path in 'value'")
        lowered = raw.lower()
        if "://" in lowered:
            if not lowered.startswith(("http://", "https://")):
                raise ActionError(f"refused to open non-http URL scheme: {raw.split('://', 1)[0]}")
            os.startfile(raw)
            return f"opened {raw} in the browser"
        path = Path(raw).expanduser()
        if not path.exists():
            raise ActionError(f"path does not exist: {path}")
        os.startfile(str(path))
        return f"opened {path}"

    def _do_read_document(self, action: dict, value) -> str:
        """Read a document's text straight from disk (Rule 5, third perception mode):
        exact content, no viewer, no file-association picker, no browser onboarding —
        and far faster than screenshotting a rendered page. The extracted text becomes
        this action's RESULT, which the brain reads from STATE on its next turn. A
        scanned/image PDF yields NO_TEXT_MARKER so the brain falls back to open_path +
        a screenshot for that file."""
        from client.perceive.documents import read_document_text  # lazy: pulls pypdf only when used
        raw = str(value or action.get("target_selector") or "").strip()
        if not raw:
            raise ActionError("read_document needs an absolute file path in 'value'")
        path = Path(raw).expanduser()
        if not path.exists():
            raise ActionError(f"path does not exist: {path}")
        if path.is_dir():
            raise ActionError(f"read_document needs a file, not a folder — use list_dir for {path}")
        try:
            text = read_document_text(path)
        except ValueError as e:
            raise ActionError(str(e)) from e
        return f"{path.name} contents:\n{text}"

    def _do_list_dir(self, action: dict, value) -> str:
        """List a folder's entries by name so the brain can drive a folder-of-files
        task deterministically (which invoices exist, in what order) without opening
        Explorer and reading a virtualized, scrollable file list from the tree."""
        raw = str(value or action.get("target_selector") or "").strip()
        if not raw:
            raise ActionError("list_dir needs an absolute folder path in 'value'")
        path = Path(raw).expanduser()
        if not path.is_dir():
            raise ActionError(f"not a folder: {path}")
        names = sorted(p.name + ("\\" if p.is_dir() else "") for p in path.iterdir())
        if not names:
            return f"{path} is empty"
        return f"{path} contains {len(names)} entries: " + ", ".join(names)
