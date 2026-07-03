; Monitor Input Switcher installer script
; Build the PyInstaller --onedir folder before compiling this installer.

#define MyAppName "Monitor Input Switcher"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Monitor Input Switcher"
#define MyAppExeName "MonitorInputSwitcher.exe"

[Setup]
; AppId uniquely identifies this app to Windows/Inno Setup.
AppId={{E0E8C63B-4F68-4C4A-95E1-7F7F5A6CC901}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; This is a per-user tray utility, so it installs without admin rights.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=MonitorInputSwitcherSetup-0.1.0
SetupIconFile=..\assets\icons\monitor-input-switcher.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Tasks]
; Desktop shortcut is optional and unchecked by default.
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

; Startup is checked by default, but the user can uncheck it.
Name: "startup"; Description: "Start Monitor Input Switcher with Windows"; GroupDescription: "Startup options:"

[Files]
; Copy the full PyInstaller folder into {app}.
; config.json is personal user data, so do not include it in the installer.
Source: "..\dist\MonitorInputSwitcher\*"; DestDir: "{app}"; Excludes: "config.json"; Flags: ignoreversion recursesubdirs createallsubdirs

; Keep a root assets\icons copy for Windows shortcuts and Start Menu icons.
; PyInstaller may store bundled data under _internal, but shortcuts need a
; stable installed icon path.
Source: "..\assets\icons\monitor-input-switcher.ico"; DestDir: "{app}\assets\icons"; Flags: ignoreversion

[Icons]
; Start Menu shortcut.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icons\monitor-input-switcher.ico"

; Optional desktop shortcut.
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icons\monitor-input-switcher.ico"; Tasks: desktopicon

[Registry]
; Optional current-user startup entry.
; HKCU is used so the app starts only for the current user.
; The uninstaller removes this value if it was created.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MonitorInputSwitcher"; ValueData: """{app}\{#MyAppExeName}"" --startup"; Flags: uninsdeletevalue; Tasks: startup
