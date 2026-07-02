# OrphicOS Brain — Deploy (TLS)

The brain is hosted by us and **never shipped to users**. The client only ever
talks to `SERVER_BASE` (e.g. `https://brain.orphicos.ai`) over HTTPS with a
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

## 2. Host (Linux/VPS/Docker)
1. Copy **only** `server/` to the host (never `client/`). Create `server/.env`
   there with the real `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`. Never commit it.
2. Run the app bound to localhost behind a TLS-terminating reverse proxy:
   ```bash
   uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1
   ```
   Keep it to **one worker** for now: per-user call metering and the token store
   are in-process (server/auth.py). Scaling to multiple workers/hosts requires
   moving both to a shared backend (Redis/DB) first, or counts split per worker.

## 3. TLS termination (Caddy — simplest)
`Caddyfile`:
```
brain.orphicos.ai {
    request_body {
        max_size 10MB
    }
    reverse_proxy 127.0.0.1:8000
}
```
The `max_size` cap enforces the body limit for chunked/spoofed Content-Length
(the app's own middleware handles the honest-Content-Length case).
Caddy fetches and renews a Let's Encrypt certificate automatically. (nginx +
certbot is an equivalent alternative.) Point `SERVER_BASE` in the client config
at `https://brain.orphicos.ai`.

## 4. Zero-retention in production (Rule 4)
- Do not enable any request-body logging in the proxy or the app. The UI tree /
  screenshot must never hit disk or logs — only metadata (action types, latency,
  token counts) is logged.
- Keep `server/.env` `chmod 600`, owned by the service user; never in the image
  layer or the repo.

## 5. Health
`GET https://brain.orphicos.ai/health` → `{"status":"ok"}` (no auth). The client
uses this for its startup reachability check.
