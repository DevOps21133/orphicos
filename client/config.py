"""OrphicOS client configuration.

The client is THIN (Rules 1 & 6): no LLM key, no brain. It reads only what it
needs to reach the OrphicOS brain:
  - SERVER_BASE      : the brain URL              (client/config.toml)
  - ORPHIC_TOKEN     : the per-user OrphicOS token (environment variable)

There is intentionally no provider name, model id, or API key anywhere here.
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


def _config_path() -> Path:
    """Where the client config lives.

    Frozen (installed) build: a per-user file the installer/first-run creates —
    %APPDATA%\\OrphicOS\\config.toml — because the install dir is not writable.
    Dev checkout: client/config.toml next to this file, as before.
    """
    if getattr(sys, "frozen", False):
        return Path(os.environ["APPDATA"]) / "OrphicOS" / "config.toml"
    return Path(__file__).with_name("config.toml")


_CONFIG_PATH = _config_path()
_EXAMPLE_PATH = Path(__file__).with_name("config.example.toml")


@dataclass(frozen=True)
class Config:
    server_base: str
    token: str
    request_timeout: float = 120.0  # a batched multi-action decision can take ~50s on the gateway
    max_steps: int = 12
    shell_host: str = "127.0.0.1"   # the OrphicOS shell binds locally only
    shell_port: int = 8700          # kept off 8000 (the brain's local dev port)


def load_config() -> Config:
    """Load and validate the client config, raising a clear error if unusable."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Missing {_CONFIG_PATH.name}. Copy {_EXAMPLE_PATH.name} to "
            f"{_CONFIG_PATH.name} and set SERVER_BASE."
        )
    data = tomllib.loads(_CONFIG_PATH.read_text(encoding="utf-8"))

    server_base = str(data.get("SERVER_BASE", "")).rstrip("/")
    if not server_base:
        raise ValueError(f"SERVER_BASE is not set in {_CONFIG_PATH.name}.")

    # Installed builds keep the token in the per-user config file (written at sign-in);
    # the ORPHIC_TOKEN env var still wins so dev sessions keep working unchanged.
    token = os.environ.get("ORPHIC_TOKEN", "").strip() or str(data.get("TOKEN", "")).strip()
    if not token:
        raise ValueError(
            "No OrphicOS token. Set TOKEN in the config file (installed builds) or export "
            "ORPHIC_TOKEN (dev; issued via `python -m server.auth issue <user>`)."
        )

    return Config(
        server_base=server_base,
        token=token,
        request_timeout=float(data.get("REQUEST_TIMEOUT", 120.0)),
        max_steps=int(data.get("MAX_STEPS", 12)),
        shell_host=str(data.get("SHELL_HOST", "127.0.0.1")),
        shell_port=int(data.get("SHELL_PORT", 8700)),
    )
