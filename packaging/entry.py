"""OrphicOS frozen entry point — what the installed OrphicOS.exe runs.

First run: creates %APPDATA%\OrphicOS\config.toml from a template, opens it in
Notepad so the user can paste their OrphicOS token, and exits with instructions.
Every run after that: starts the OrphicOS shell (browser UI) exactly like
`python -m client.shell` does in a dev checkout.

This file contains no brain logic and no provider anything (CLAUDE.md Rules 1 & 2).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_TEMPLATE = """# OrphicOS — connection settings
# 1) SERVER_BASE is preset to the OrphicOS brain.
# 2) Paste the token from your OrphicOS account between the quotes, save, close.
SERVER_BASE = "{server_base}"
TOKEN = ""
"""

_DEFAULT_SERVER_BASE = "https://brain.orphicos.ai"


def _first_run_setup(cfg_path: Path) -> None:
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(_TEMPLATE.format(server_base=_DEFAULT_SERVER_BASE), encoding="utf-8")
    print("Welcome to OrphicOS — one-time setup.")
    print(f"A settings file was created at:\n  {cfg_path}")
    print("Paste your OrphicOS token into TOKEN, save the file, then start OrphicOS again.")
    subprocess.Popen(["notepad.exe", str(cfg_path)])


def main() -> int:
    cfg_path = Path(os.environ["APPDATA"]) / "OrphicOS" / "config.toml"
    if not cfg_path.exists():
        _first_run_setup(cfg_path)
        input("Press Enter to close this window...")
        return 0

    from client.shell.__main__ import main as shell_main
    rc = shell_main()
    if rc != 0:
        # Config errors print to stderr inside shell_main; keep the window readable.
        input("Press Enter to close this window...")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
