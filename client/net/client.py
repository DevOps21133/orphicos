"""OrphicOS client → brain transport.

Sends {command, ui_tree, state, screenshot?} to the OrphicOS brain and returns the
decided actions. This module is the client's ONLY outbound network path, and it
goes to exactly one place: SERVER_BASE (Rules 1 & 6). There is no LLM provider,
key, or SDK here — the screenshot is included only on the tree-insufficient
fallback (Rule 5).
"""
from __future__ import annotations

from typing import Any, Optional

import httpx


class BrainError(RuntimeError):
    """The brain was unreachable or returned a non-success response."""


class BrainClient:
    def __init__(self, server_base: str, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=server_base.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def health(self) -> bool:
        """True if the brain answers /health with status ok."""
        try:
            r = self._client.get("/health", timeout=5.0)
            return r.status_code == 200 and r.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def decide(self, command: str, ui_tree: str, state: Optional[dict] = None,
               screenshot: Optional[str] = None) -> dict[str, Any]:
        """Ask the brain for the next actions. Returns {actions, done, reasoning_summary}."""
        payload: dict[str, Any] = {"command": command, "ui_tree": ui_tree}
        if state is not None:
            payload["state"] = state
        if screenshot is not None:  # only set on the tree-insufficient fallback
            payload["screenshot"] = screenshot
        try:
            r = self._client.post("/command", json=payload)
        except httpx.HTTPError as e:
            raise BrainError(f"Could not reach the OrphicOS brain: {e}") from e
        if r.status_code == 401:
            raise BrainError("OrphicOS token rejected (401). Check ORPHIC_TOKEN.")
        if r.status_code != 200:
            raise BrainError(f"Brain returned HTTP {r.status_code}.")
        return r.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BrainClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
