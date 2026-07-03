"""OrphicOS brain API — POST /command turns a command + screen map into actions.

Zero-retention (CLAUDE.md Rule 4): the UI tree and any screenshot are used only
to serve the single request and are NEVER written to disk or logs. Only metadata
(action types, counts, latency, token usage) is logged.

Run locally:
    uvicorn server.app:app --host 127.0.0.1 --port 8000   # from the repo root
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# Load server-only secrets (LLM_API_KEY etc.) from server/.env before serving.
load_dotenv(Path(__file__).with_name(".env"))

from server import accounts, auth, brain  # noqa: E402 - must follow load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# Keep the provider host and any request bodies OUT of our logs (Rules 2 & 4):
# httpx logs the full request URL (the provider hostname) at INFO, and the OpenAI
# SDK can log serialized request bodies (ui_tree/screenshot) at DEBUG. Pin both below
# that so neither leaks even if the app or OPENAI_LOG raises the level.
for _noisy in ("httpx", "httpcore", "openai"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger("orphicos.brain")

app = FastAPI(title="OrphicOS Engine", version="0.1.0")

# Reject oversized bodies before they are buffered into RAM (unauthenticated DoS
# defense — FastAPI reads the full body before the auth dependency runs). The reverse
# proxy (deploy.md) enforces the same cap for chunked/spoofed Content-Length; the
# pydantic max_length constraints below are a parsed-size backstop.
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB — generous for a base64 fallback screenshot


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for name, value in scope.get("headers", []):
                if name == b"content-length":
                    try:
                        too_big = int(value) > self.max_bytes
                    except ValueError:
                        too_big = False
                    if too_big:
                        await send({"type": "http.response.start", "status": 413,
                                    "headers": [(b"content-type", b"application/json")]})
                        await send({"type": "http.response.body",
                                    "body": b'{"detail":"Request body too large."}'})
                        return
                    break
        await self.app(scope, receive, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)


class Action(BaseModel):
    type: str
    target_selector: Optional[str] = None
    coords: Optional[list[float]] = None
    value: Optional[str] = None


class CommandRequest(BaseModel):
    command: str = Field(max_length=4000)
    ui_tree: str = Field(default="", max_length=300_000)
    screenshot: Optional[str] = Field(default=None, max_length=8_000_000)  # base64; fallback only
    state: Optional[dict[str, Any]] = None


class CommandResponse(BaseModel):
    actions: list[Action]
    done: bool
    reasoning_summary: str


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class AuthResponse(BaseModel):
    token: str
    user_id: str


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(creds: Credentials) -> AuthResponse:
    # Never log the email/password/token — metadata-only logging throughout.
    problem = accounts.validate_new_credentials(creds.email, creds.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    try:
        token = accounts.register(creds.email, creds.password)
    except accounts.EmailTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    log.info("account registered")
    return AuthResponse(token=token, user_id=accounts.normalize_email(creds.email))


@app.post("/auth/login", response_model=AuthResponse)
async def login(creds: Credentials) -> AuthResponse:
    try:
        token = accounts.login(creds.email, creds.password)
    except accounts.LockedOut as e:
        raise HTTPException(status_code=429, detail=str(e))
    except accounts.InvalidCredentials as e:
        raise HTTPException(status_code=401, detail=str(e))
    return AuthResponse(token=token, user_id=accounts.normalize_email(creds.email))


async def current_user(authorization: str = Header(default="")) -> str:
    raw = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    user_id = auth.validate_token(raw.strip() or None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing OrphicOS token.")
    return user_id


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "OrphicOS engine"}


@app.post("/command", response_model=CommandResponse)
async def command(req: CommandRequest, user_id: str = Depends(current_user)) -> CommandResponse:
    try:
        decision, usage = brain.decide(req.command, req.ui_tree, req.state, req.screenshot)
        response = CommandResponse(**decision)  # build inside the guard: a bad shape → 502, not 500
    except Exception as e:  # noqa: BLE001 - never surface engine internals to the client
        log.error("brain error user=%s err=%s", user_id, type(e).__name__)
        raise HTTPException(status_code=502, detail="Engine could not produce a decision.")

    # Meter only a successful decision. Metadata-only log — never the ui_tree,
    # screenshot, or command text (Rule 4).
    calls = auth.record_call(user_id)
    log.info(
        "cmd user=%s actions=%d types=%s done=%s latency_ms=%s tokens=%s calls=%d",
        user_id, len(response.actions),
        ",".join(a.type for a in response.actions) or "-",
        response.done, usage.get("latency_ms"), usage.get("total_tokens"), calls,
    )
    return response
