# Release Checklist

Use this checklist before publishing a GitHub release.

## Build

- [ ] Test from source.
- [ ] Build PyInstaller `--onedir`.
- [ ] Test portable build.
- [ ] Build Inno Setup installer.
- [ ] Test installer.
- [ ] Test uninstall.

## App Behavior

- [ ] Test startup hidden in tray.
- [ ] Test manual launch opens the main window.
- [ ] Test tray menu Show.
- [ ] Test tray Quit exits the app.
- [ ] Test global hotkeys.
- [ ] Test monitor switching.
- [ ] Test laptop internal screen skipped.

## Release Files

- [ ] Confirm no `config.json` included.
- [ ] Confirm icon appears in app window.
- [ ] Confirm icon appears in tray.
- [ ] Confirm icon appears in Start Menu.
- [ ] Confirm icon appears in installer.
- [ ] Confirm NirSoft notice included.
- [ ] Create portable ZIP from `dist\MonitorInputSwitcher`.
- [ ] Create GitHub release.
- [ ] Upload installer.
- [ ] Upload portable ZIP.
