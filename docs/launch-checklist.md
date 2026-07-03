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

- [ ] **Code signing (REQUIRED before any distribution).** Windows 11 Smart App Control
      and SmartScreen block unsigned executables — our own dev machine blocked the
      unsigned build. Buy an OV or EV Authenticode certificate (EV = instant SmartScreen
      reputation), then sign both `OrphicOS.exe` and `OrphicOS-Setup.exe` with
      `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 ...`.
      Until signing is in place, test installs on a machine/VM with Smart App Control off.
- [ ] **Server deployed at the production `SERVER_BASE`** (TLS, real domain) and the
      default in `packaging/entry.py` pointing at it.
- [ ] **Token issuing = sign-in.** v1 onboarding is paste-a-token; the account/sign-in
      flow that issues tokens automatically is the next iteration.
- [ ] Install Inno Setup 6 on the build machine (`winget install JRSoftware.InnoSetup`).

## Demo recording (Phase 4 command)

1. `scripts\reset_demo.ps1` — regenerate `C:\OrphicDemo\invoices\` identically.
2. OBS: record the OrphicOS browser window with the wordmark in frame.
3. Run the canonical command from `docs/demo-task.md`, once typed, once spoken.
4. Cold open: placeholder — founder script.
5. Landing page copy: placeholder — founder writes final copy.

## Stranger test (Phase 6 DONE gate)

A person who has never seen the project: installs `OrphicOS-Setup.exe`, pastes their
token on first run, and runs the demo command — with zero other setup. Record outcome.
