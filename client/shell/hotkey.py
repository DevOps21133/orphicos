"""Global kill-switch hotkey (Ctrl+Alt+Space) for the OrphicOS shell (CLAUDE.md §9.3).

Registers a SINGLE system-wide hotkey via Win32 RegisterHotKey and runs a private
message loop on its own thread. We deliberately do NOT install a global keyboard hook
(no key-logging): a product that can drive the whole OS must not read every keystroke.
If the chord is already taken by another app we log and carry on — the on-screen STOP
button still halts the run.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_VK_SPACE = 0x20
_HOTKEY_ID = 1


class GlobalKillHotkey:
    """Fire `on_press` whenever the user presses Ctrl+Alt+Space, anywhere in Windows."""

    def __init__(self, on_press: Callable[[], None]) -> None:
        self._on_press = on_press
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self.registered = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="orphic-hotkey", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, _HOTKEY_ID,
                                     _MOD_ALT | _MOD_CONTROL | _MOD_NOREPEAT, _VK_SPACE):
            print("OrphicOS: could not arm the Ctrl+Alt+Space kill switch "
                  "(the chord may be in use). The on-screen STOP button still works.")
            return
        self.registered = True
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
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
