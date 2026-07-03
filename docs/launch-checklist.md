# OrphicOS launch checklist (Phase 6)

## Build the package (repeat for every release)

```powershell
cd C:\orphicOS
.venv\Scripts\python.exe -m PyInstaller packaging\orphicos.spec --noconfirm
.venv\Scripts\python.exe packaging\verify_dist.py      # MUST print PASS (wall + license check)
iscc packaging\installer.iss                            # -> dist\OrphicOS-Setup.exe
```

`verify_dist.py` fails the build if any LLM-provider SDK, telemetry client, or GPL
module shipped in the app — run it on EVERY build, no exceptions.

## Release blockers (founder decisions / actions)

- [x] **Code signing — DEFERRED (founder decision 2026-07-03): ship unsigned.**
      Users on standard Windows 11 will see SmartScreen ("More info" → "Run anyway");
      users with Smart App Control ON are hard-blocked with no override and are
      accepted as lost for now. Revisit at first paying interest — options: Certum OV
      (~$70–100/yr) or Azure Trusted Signing (~$10/mo), then sign both `OrphicOS.exe`
      and `OrphicOS-Setup.exe` with `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 ...`.
      Until then, test installs on a machine/VM with Smart App Control off.
- [x] **Server deployed at the production `SERVER_BASE`** — https://brain.orphicos.app
      (TLS via Let's Encrypt) and `packaging/entry.py` defaults to it.
- [ ] **Token issuing = sign-in.** v1 onboarding is paste-a-token; the account/sign-in
      flow (`/auth/register`, `/auth/login` on `feat/signin`) replaces it once merged
      and deployed.
- [x] Install Inno Setup 6 on the build machine (`winget install JRSoftware.InnoSetup`).

## Demo recording (Phase 4 command)

1. `scripts\reset_demo.ps1` — regenerate `C:\OrphicDemo\invoices\` identically.
2. OBS: record the OrphicOS browser window with the wordmark in frame.
3. Run the canonical command from `docs/demo-task.md`, once typed, once spoken.
4. Cold open: placeholder — founder script.
5. Landing page copy: placeholder — founder writes final copy.

## Stranger test (Phase 6 DONE gate)

A person who has never seen the project: installs `OrphicOS-Setup.exe`, pastes their
token on first run, and runs the demo command — with zero other setup. Record outcome.
