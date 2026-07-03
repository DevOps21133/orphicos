# OrphicOS Brain â€” Deploy (TLS)

The brain is hosted by us and **never shipped to users**. The client only ever
talks to `SERVER_BASE` (e.g. `https://brain.orphicos.app`) over HTTPS with a
per-user OrphicOS token. The LLM key lives only in `server/.env` on the host.

## 1. Local (do this first)
```powershell
python -m venv server\.venv
server\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
# server\.env must contain LLM_API_KEY, LLM_MODEL, LLM_BASE_URL (gitignored)
server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```
Issue a token for a user:
```powershell
server\.venv\Scripts\python.exe -m server.auth issue <user_id>
```

## 2. Host (VPS, Docker â€” the standard path)
Turnkey stack in `server/`: `Dockerfile` (the brain) + `docker-compose.yml`
(brain + Caddy with automatic Let's Encrypt TLS) + `Caddyfile`.

1. Rent a Linux VPS (any provider; 2GB RAM is plenty â€” the brain is a thin proxy).
2. Point DNS: `A` record for `brain.orphicos.app` -> the VPS IP.
3. Copy **only** `server/` to the host (never `client/`). Create `server/.env`
   there (`LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`), `chmod 600`. Never commit it.
4. ```bash
   cd server
   DOMAIN=brain.orphicos.app docker compose up -d --build
   ```
5. Issue tokens: `docker compose exec brain python -m server.auth issue <user_id>`
   (tokens persist on the `brain_data` volume via `ORPHIC_TOKENS_PATH`).

Keep it to **one worker** (the Dockerfile does): per-user call metering and the
token store are in-process (server/auth.py). Scaling to multiple workers/hosts
requires moving both to a shared backend (Redis/DB) first.

The Caddyfile's `max_size 10MB` enforces the body cap for chunked/spoofed
Content-Length (the app's middleware handles the honest case), and no access log
is configured (Rule 4). Point the client's `SERVER_BASE` at
`https://brain.orphicos.app`.

Verified 2026-07-03 (Docker in WSL2): image builds, `/health` 200 via the
container, token issuing writes to the volume. (Full `/command` smoke was
gateway-limited that day â€” re-run it against the deployed host.)

## 4. Zero-retention in production (Rule 4)
- Do not enable any request-body logging in the proxy or the app. The UI tree /
  screenshot must never hit disk or logs â€” only metadata (action types, latency,
  token counts) is logged.
- Keep `server/.env` `chmod 600`, owned by the service user; never in the image
  layer or the repo.

## 5. Health
`GET https://brain.orphicos.app/health` â†’ `{"status":"ok"}` (no auth). The client
uses this for its startup reachability check.
