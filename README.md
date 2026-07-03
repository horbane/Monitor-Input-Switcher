# Monitor Input Switcher

A Windows tray utility for switching external monitor inputs using one click, tray menu, or global hotkeys.

Monitor Input Switcher is built with Python and PySide6. It uses ControlMyMonitor by NirSoft as the monitor-control backend and uses DDC/CI VCP code 60 for monitor input switching.

Status: beta / testing.

## Screenshots

Screenshots coming soon.

## Features

- One-click monitor input switching
- Multi-monitor support
- Per-monitor switching
- Global hotkeys
- System tray support
- Start with Windows
- Setup wizard
- Skips unsupported/internal displays when possible

## Requirements

- Windows
- External monitor with DDC/CI support
- DDC/CI enabled in the monitor settings

## First-Time Setup

Monitor input values are not universal. Each monitor can use different values for HDMI, DisplayPort, USB-C, and other inputs.

For a two-device setup, think of the devices as Device A and Device B.

1. Install/open Monitor Input Switcher on Device A and Device B.
2. While the monitors are showing Device A, run setup on Device A and read the current input values.
3. Manually switch the monitors to Device B using the monitor buttons or input menu.
4. While the monitors are showing Device B, run setup on Device B and read the current input values.
5. Configure Device A using the input values that were detected on Device B.
6. Configure Device B using the input values that were detected on Device A.

After setup, each device can switch the monitors to the other device.

## Downloads

Release downloads will be available from GitHub Releases.

- Installer: use GitHub Releases
- Portable ZIP: use GitHub Releases

## Build From Source

See [BUILD.md](BUILD.md).

## Third-Party Notice

This app uses ControlMyMonitor by NirSoft as the monitor-control backend. ControlMyMonitor is not created by this project.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Limitations

- Some monitors do not support DDC/CI input switching.
- Some monitors report input values differently.
- Switching back from the same device may not work after the monitor switches away.
- Setup is required once per device.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
