; Inno Setup script for RiftLab.
;
; Wraps the PyInstaller folder from dist\RiftLab into a single setup .exe that
; installs without Python, pip or an internet connection. RiftLab's dependency
; stack is the heavier of the two tools - Qt, pyqtgraph, matplotlib, numpy - so
; the failure that stopped RiftRec's zipped version from starting on somebody
; else's PC applies here with more ways to go wrong, not fewer.
;
; Anyone who wants to change RiftLab still works from a source checkout; this is
; for opening a recording and looking at it.
;
; Build:  ISCC.exe /DAppVersion=0.1.0 packaging\riftlab.iss
; Signed: ISCC.exe /DSIGN /Ssigntool="<signtool command> $f"

#ifndef AppVersion
  ; Fallback for a bare ISCC run. tests/test_packaging.py keeps this in step
  ; with riftlab.__version__, so an unversioned build is never mislabelled.
  #define AppVersion "0.1.0"
#endif

#define AppName "RiftLab"
#define AppPublisher "MechatronikMonkey"
#define AppURL "https://github.com/MechatronikMonkey/RiftLab"
#define AppExe "RiftLab.exe"

[Setup]
; Never change AppId - it is how Windows recognises an existing installation and
; upgrades it in place instead of leaving two copies behind. Distinct from
; RiftRec's, so the two install and uninstall independently.
AppId={{9F4D1C82-6E27-4B93-8A5D-2C7E0B1F4A63}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
VersionInfoVersion={#AppVersion}

; Per-user install: no admin prompt, no UAC dialog. Same reasoning as RiftRec -
; and it means a researcher can install this on a university machine.
PrivilegesRequired=lowest
DefaultDirName={userpf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto

OutputDir=..\dist
OutputBaseFilename=RiftLab-Setup-{#AppVersion}
SetupIconFile=riftlab.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

CloseApplications=yes
RestartApplications=no

#ifdef SIGN
; Enabled only for a signed build, so an unsigned local build still works.
SignTool=signtool
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\RiftLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start RiftLab now"; Flags: nowait postinstall skipifsilent

; Nothing under [UninstallDelete]: RiftLab writes no settings of its own, and it
; must never touch a .sqlite. The recordings are somebody's study data and the
; only copy - an uninstaller has no business anywhere near them.
