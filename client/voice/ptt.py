"""Push-to-talk chord watcher: hold Ctrl+Alt+V to record, release to transcribe.

Like the kill-switch hotkey, this deliberately installs NO global keyboard hook — a
product that can drive the whole OS must not read every keystroke. RegisterHotKey
can't be used either: it only reports presses, and push-to-talk needs the RELEASE.
Instead a small thread polls GetAsyncKeyState for exactly the three chord keys
(Ctrl, Alt, V) — the OS tells us only whether those specific keys are down, so no
other typing is ever observable from here.
"""
from __future__ import annotations

import ctypes
import threading
from typing import Callable

HOTKEY_LABEL = "Ctrl+Alt+V"

_VK_CONTROL = 0x11
_VK_MENU = 0x12    # Alt
_VK_V = 0x56
_KEY_DOWN = 0x8000
_POLL_SECONDS = 0.02  # 50 Hz: imperceptible press/release lag, negligible CPU


def _chord_down() -> bool:
    ks = ctypes.windll.user32.GetAsyncKeyState
    return all(ks(vk) & _KEY_DOWN for vk in (_VK_CONTROL, _VK_MENU, _VK_V))


class PushToTalk:
    """Fire on_press when the chord goes down and on_release when it comes back up."""

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="orphic-ptt", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        held = False
        while not self._stop.wait(_POLL_SECONDS):
            down = _chord_down()
            if down and not held:
                held = True
                self._fire(self._on_press)
            elif held and not down:
                held = False
                self._fire(self._on_release)

    @staticmethod
    def _fire(cb: Callable[[], None]) -> None:
        try:
            cb()
        except Exception:  # noqa: BLE001 — the watcher must outlive a bad callback
            pass

    def stop(self) -> None:
        self._stop.set()
