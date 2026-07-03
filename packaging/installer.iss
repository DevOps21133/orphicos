; OrphicOS Windows installer (Inno Setup 6).
; Wraps ONLY the frozen thin client from dist\OrphicOS (CLAUDE.md §10.1):
; never server/, never any LLM key, never a provider name.
;
; Build:  1) .venv\Scripts\python.exe -m PyInstaller packaging\orphicos.spec --noconfirm
;         2) .venv\Scripts\python.exe packaging\verify_dist.py     (must PASS)
;         3) iscc packaging\installer.iss
; Output: dist\OrphicOS-Setup.exe

[Setup]
AppName=OrphicOS
AppVersion=0.1.0
AppPublisher=OrphicOS
DefaultDirName={autopf}\OrphicOS
DefaultGroupName=OrphicOS
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=OrphicOS-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\THIRD-PARTY-NOTICES.txt
PrivilegesRequired=lowest

[Files]
Source: "..\dist\OrphicOS\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\OrphicOS"; Filename: "{app}\OrphicOS.exe"
Name: "{autodesktop}\OrphicOS"; Filename: "{app}\OrphicOS.exe"

[Run]
Filename: "{app}\OrphicOS.exe"; Description: "Start OrphicOS"; Flags: nowait postinstall skipifsilent
