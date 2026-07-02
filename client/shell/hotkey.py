"""Global kill-switch hotkey for the OrphicOS shell (CLAUDE.md §9.3).

Registers ONE system-wide hotkey via Win32 RegisterHotKey and runs a private message
loop on its own thread. We deliberately do NOT install a global keyboard hook (no
key-logging): a product that can drive the whole OS must not read every keystroke.

Ctrl+Alt+Space is the documented primary chord, but another app may already own it
(AutoHotkey, IMEs, etc.). RegisterHotKey only succeeds on a FREE chord — it never steals
one — so we try a short fallback chain and report which chord actually armed. The shell
UI shows that real chord (or "none") on the STOP button, so the panic key is never a lie.
The on-screen STOP button always works regardless.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_VK_SPACE = 0x20
_VK_PAUSE = 0x13
_VK_BACK = 0x08
_HOTKEY_ID = 1

# Tried in order; the first FREE chord wins. All are panic-appropriate and unlikely to
# collide; Ctrl+Alt+Delete is reserved by Windows and cannot be registered, so it's absent.
_CANDIDATES = (
    ("Ctrl+Alt+Space", _MOD_CONTROL | _MOD_ALT, _VK_SPACE),
    ("Ctrl+Shift+Space", _MOD_CONTROL | _MOD_SHIFT, _VK_SPACE),
    ("Ctrl+Alt+Pause", _MOD_CONTROL | _MOD_ALT, _VK_PAUSE),
    ("Ctrl+Alt+Backspace", _MOD_CONTROL | _MOD_ALT, _VK_BACK),
)


class GlobalKillHotkey:
    """Fire `on_press` when the user presses the armed panic chord, anywhere in Windows."""

    def __init__(self, on_press: Callable[[], None]) -> None:
        self._on_press = on_press
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._arm_attempted = threading.Event()
        self.armed_chord: Optional[str] = None  # the chord that actually registered, or None

    def start(self, timeout: float = 2.0) -> Optional[str]:
        """Start the hotkey thread and block until arming is attempted; return the armed chord."""
        self._thread = threading.Thread(target=self._run, name="orphic-hotkey", daemon=True)
        self._thread.start()
        self._arm_attempted.wait(timeout)
        return self.armed_chord

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        for label, mods, vk in _CANDIDATES:
            if user32.RegisterHotKey(None, _HOTKEY_ID, mods | _MOD_NOREPEAT, vk):
                self.armed_chord = label
                break
        self._arm_attempted.set()  # unblock start(); armed_chord is now final

        if self.armed_chord is None:
            print("OrphicOS: no global kill-switch chord was free; use the on-screen STOP button.")
            return
        print(f"OrphicOS: kill switch armed on {self.armed_chord}.")

        msg = wintypes.MSG()
        # GetMessageW returns >0 for a message, 0 for WM_QUIT, -1 on error; stop on <=0.
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                try:
                    self._on_press()
                except Exception:  # noqa: BLE001 — a kill switch must never crash its own loop
                    pass
        user32.UnregisterHotKey(None, _HOTKEY_ID)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
