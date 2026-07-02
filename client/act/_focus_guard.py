"""Detect whether the foreground window is a console/terminal.

The thin client sends untargeted keystrokes (SendKeys, keyboard shortcuts) to
whatever window currently has focus. If that window is a PowerShell/cmd/Windows
Terminal console, those keystrokes become SHELL COMMANDS — they run outside the
OrphicOS kill switch and can do real damage. OrphicOS never drives a console, so
the actor consults this guard and refuses to fire blind keys when a terminal is
focused (the action is skipped instead).

Pure Win32 via ctypes — no third-party engine involved, so this stays on the
client side of the wall. Detection is fail-open: any error returns None (do not
block), because a detection bug must never brick legitimate typing.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

# Window classes owned by console hosts.
_CONSOLE_CLASSES = {
    "ConsoleWindowClass",             # conhost.exe: classic Windows PowerShell / cmd.exe
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    "PseudoConsoleWindow",
}
# Backstop by process image name, for hosts whose window class may vary.
_CONSOLE_PROCS = {
    "powershell.exe", "pwsh.exe", "cmd.exe",
    "windowsterminal.exe", "conhost.exe", "openconsole.exe",
}

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _process_image_name(pid: int) -> str | None:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return None
    finally:
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)


def foreground_console_label() -> str | None:
    """Return a short label (class or process name) if the foreground window is a
    console/terminal, else None. Never raises — returns None on any failure."""
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        if cls_buf.value in _CONSOLE_CLASSES:
            return cls_buf.value

        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = _process_image_name(pid.value) if pid.value else None
        if proc and proc.lower() in _CONSOLE_PROCS:
            return proc
        return None
    except Exception:  # noqa: BLE001 — detection must never break real typing (fail-open)
        return None
