"""OrphicOS client configuration.

The client is THIN (Rules 1 & 6): no LLM key, no brain. It reads only what it
needs to reach the OrphicOS brain:
  - SERVER_BASE      : the brain URL              (client/config.toml)
  - ORPHIC_TOKEN     : the per-user OrphicOS token (environment variable)

There is intentionally no provider name, model id, or API key anywhere here.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

_CONFIG_PATH = Path(__file__).with_name("config.toml")
_EXAMPLE_PATH = Path(__file__).with_name("config.example.toml")


@dataclass(frozen=True)
class Config:
    server_base: str
    token: str
    request_timeout: float = 120.0  # a batched multi-action decision can take ~50s on the gateway
    max_steps: int = 12


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

    token = os.environ.get("ORPHIC_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "ORPHIC_TOKEN is not set. Export the per-user OrphicOS token issued by "
            "the brain (`python -m server.auth issue <user>`) before starting the client."
        )

    return Config(
        server_base=server_base,
        token=token,
        request_timeout=float(data.get("REQUEST_TIMEOUT", 120.0)),
        max_steps=int(data.get("MAX_STEPS", 12)),
    )
