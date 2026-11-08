# Meshing Around — Intel Mac Desktop Beta

This folder contains the Tkinter desktop application and Intel macOS packaging helpers for this fork. The existing Meshtastic bot remains the backend.

## Launch from source

From the repository root with dependencies installed:

```bash
python desktop/launcher.py
```

## Desktop sections

The sidebar has five sections (⌘1–⌘5) and a status area that always shows whether the bot is running and whether the radio is connected.

- **Overview:** A three-step "Get started" checklist until the bot is running, bot and radio status cards with their main actions, and recent events from this session.
- **Radio:** Choose Wi-Fi / Network, Bluetooth or USB cable, enter the address (checked as you type), then Save and Test connection. A test reads the radio's name, hardware and firmware and disconnects without transmitting. Failures explain what to check in plain language, with the technical detail one click away. USB shows a Find USB radio button.
- **Bot:** Start, stop or restart the bot, see how long it has run, and see what it does on your mesh (reply mode, enabled features, automatic broadcasts), read from `config.ini`. Advanced options open the config file or show it in Finder.
- **Activity:** Live bot output with errors and warnings colored, search with match count (Return / Shift-Return for next and previous, Escape to reset), export to `~/Documents/Meshing Around Logs`, clear (asks first), and a Follow new output switch.
- **Settings:** Six themes (five dark, one light: Daylight), text size (Default / Large / Larger), Reduce motion (follows macOS until changed), app folders and keyboard shortcuts.

The menu bar mirrors these actions: ⌘T test connection, ⌘S save radio settings, ⌘R start and ⌘. stop the bot, ⌘F search activity, ⌘E export, ⌘, settings. Quitting while the bot runs asks first, then stops it.

### Design system

All styling comes from [`design_system.py`](design_system.py) (color tokens derived per theme and checked against WCAG AA contrast, type scale, spacing) and the components in [`components.py`](components.py) and [`icons.py`](icons.py). Screens should use these rather than hard-coded colors or fonts.

The default Wi-Fi/TCP address is `meshtastic.local`. You can specify a reachable radio host and port (for example `192.168.1.50:4403`). The app also supports BLE and USB/serial selection, subject to hardware and platform compatibility.

New installs start with unprompted channel broadcasts switched off: Sentry
proximity alerts (`SentryEnabled`), high-altitude node alerts
(`highFlyingAlert`) and iPAWS emergency alerts (`ipawsAlertEnabled`). The bot
still answers direct messages. To turn any of these on, set it to `True` in
`~/Library/Application Support/MeshingAround/runtime/config.ini`. Existing
configurations are never changed.

## Intel Mac build

The [Intel Mac workflow](../.github/workflows/intel-mac-app.yml) builds an x86_64 `.app` and `.dmg` on a macOS Intel runner, runs automated checks, and uploads the `meshing-around-intel-mac-beta` artifact. The beta is not notarized. See [MAC_PACKAGING.md](MAC_PACKAGING.md) and [BETA_RELEASE.md](BETA_RELEASE.md).

## Screenshots

The build workflow has an optional `dashboard-screenshot` artifact step that captures each of the five sections. Screenshot capture is best effort and should not be treated as a verified image until the capture is inspected. The main [README](../README.md) will display actual desktop screenshots once available.

## Validation status

CI exercises syntax, packaging, and headless smoke checks. A live radio connection, Bluetooth permissions, and UI appearance must still be checked on a physical Intel Mac before a stable release.
