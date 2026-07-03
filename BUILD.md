# Build Monitor Input Switcher

These steps are for building Monitor Input Switcher on Windows.

The app is currently packaged as a PyInstaller `--onedir` build. Do not use `--onefile` yet.

## 1. Create Virtual Environment

Open PowerShell in the project folder:

```powershell
cd "C:\Path\To\Monitor-Input-Switcher"
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

## 2. Install Requirements

```powershell
python -m pip install --upgrade pip
```

```powershell
python -m pip install -r requirements.txt
```

## 3. Run From Source

```powershell
python app.py
```

## 4. Build PyInstaller Onedir

Install PyInstaller:

```powershell
python -m pip install pyinstaller
```

Build:

```powershell
python -m PyInstaller --noconsole --onedir --name MonitorInputSwitcher --icon "assets/icons/monitor-input-switcher.ico" --add-data "assets;assets" --add-data "controlmymonitor;controlmymonitor" app.py
```

On Windows, PyInstaller `--add-data` uses a semicolon:

```text
source;destination
```

The built app will be here:

```text
dist\MonitorInputSwitcher\MonitorInputSwitcher.exe
```

You can also run the helper script:

```powershell
.\build_onedir.bat
```

## 5. Build Installer With Inno Setup

Install Inno Setup from:

```text
https://jrsoftware.org/isinfo.php
```

Build the PyInstaller folder first:

```powershell
.\build_onedir.bat
```

Open Inno Setup Compiler and compile:

```text
installer\MonitorInputSwitcher.iss
```

The installer output will be:

```text
installer\output\MonitorInputSwitcherSetup-0.1.0.exe
```

The installer is per-user and installs to:

```text
{localappdata}\Programs\Monitor Input Switcher
```

Startup with Windows uses:

```text
"{app}\MonitorInputSwitcher.exe" --startup
```

This starts the app hidden in the tray when setup is already complete. Start Menu and desktop shortcuts launch normally and show the main window.

## 6. Release Config Note

Do not include `config.json` in release builds.

`config.json` is personal user configuration and should be created on first run. Before publishing an installer or portable ZIP, confirm there is no `config.json` in:

```text
dist\MonitorInputSwitcher\
```

## 7. Quick Test

After building, test:

- Run from source
- Run `dist\MonitorInputSwitcher\MonitorInputSwitcher.exe`
- Install with Inno Setup
- Uninstall from Windows Settings
- Confirm startup launches hidden in tray
- Confirm shortcuts and icons work
