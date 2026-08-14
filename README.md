# OrphicOS

**The machine works. You don't.**

OrphicOS lets you run your Windows 11 PC by voice or text. Tell it what you want —
"open Notepad and type the meeting notes", "put these totals into Excel and sum them" —
and OrphicOS reads your screen, decides the exact steps, and does them, live, in front
of you.

## How it works

- You type (or speak) a command into the OrphicOS bar.
- The OrphicOS engine works out the next actions and your machine carries them out —
  clicking, typing, and switching windows like a careful human operator.
- You watch every step in the live log, approve anything risky (delete, send,
  purchase…), and can stop everything instantly with the big red STOP or the global
  kill hotkey.

## Getting started

1. Run the OrphicOS installer (`OrphicOS-Setup.exe`).
2. Start OrphicOS. On first run it creates your settings file and asks for the token
   from your OrphicOS account — paste it in, save, and start OrphicOS again.
3. The OrphicOS window opens in your browser. Type what the machine should do.

## Run from source

The client never holds an LLM key. The brain is `server/`; copy `server/.env.example`
to `server/.env` and fill `LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL`. Real keys
and tokens stay gitignored (`server/.env`, `server/tokens.json`, `client/config.toml`).

```powershell
# brain
python -m venv server\.venv
server\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000
server\.venv\Scripts\python.exe -m server.auth issue demo

# thin client
python -m venv client\.venv
client\.venv\Scripts\python.exe -m pip install -r client\requirements.txt
copy client\config.example.toml client\config.toml
# set SERVER_BASE = "http://localhost:8000" and TOKEN from the issue command
powershell -ExecutionPolicy Bypass -File scripts\run_shell.ps1
```

See `docs/runbook.md` and `server/scripts/deploy.md` for the full operator path.

## Your data

Your commands and a compact map of your screen are **processed securely on OrphicOS
servers. Encrypted in transit. Your screen data is never stored.** Voice, when enabled,
is transcribed locally on your machine — audio never leaves your PC.

## Safety

- **Approval gate:** risky actions (delete, remove, send, submit, purchase, uninstall,
  format) always ask you first.
- **Kill switch:** the STOP button and a global hotkey halt everything instantly, even
  if the OrphicOS window is buried.
- **You confirm voice commands:** transcribed speech is never auto-submitted — you read
  it and press Enter.

Third-party components are listed in `THIRD-PARTY-NOTICES.txt` (installed alongside the app).

## License

MIT. See [LICENSE](LICENSE).
