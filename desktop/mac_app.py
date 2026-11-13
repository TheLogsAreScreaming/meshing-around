"""Frozen macOS entry point with first-run configuration and smoke validation."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

from dashboard import launch


def locate_bot(bundle: Path) -> Path:
    """PyInstaller can place added binaries in a nested internal directory."""
    candidates = [bundle / "meshing-around-bot", bundle / "Contents" / "Frameworks" / "meshing-around-bot"]
    candidates.extend(bundle.rglob("meshing-around-bot"))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError("Bundled Meshtastic bot executable missing")


# Features that post to a mesh channel without anyone messaging the bot.
# New desktop installs start quiet; users can opt in by editing config.ini.
QUIET_BROADCASTS = {
    "[sentry]": ("SentryEnabled", "highFlyingAlert"),
    "[location]": ("ipawsAlertEnabled",),
}


def mac_defaults(text: str) -> str:
    """Point the Linux serial default at a Wi-Fi radio and switch off
    unprompted channel broadcasts; leave comments intact."""
    lines, section = [], None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped
        elif section == "[interface]":
            if stripped == "type = serial":
                line = "type = tcp\n"
            elif stripped == "port = /dev/ttyACM0":
                line = "hostname = meshtastic.local\n"
        elif section in QUIET_BROADCASTS:
            key = stripped.partition("=")[0].strip()
            if key in QUIET_BROADCASTS[section]:
                line = f"{key} = False\n"
        lines.append(line)
    return "".join(lines)


def prepare_workspace(bundle: Path, workspace: Path) -> tuple[Path, Path]:
    source = bundle / "payload"
    if not source.is_dir():
        raise FileNotFoundError("Application payload missing")
    bot = locate_bot(bundle)
    workspace.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = workspace / item.name
        if destination.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
    # The bot reads config.ini, not config.template. Never replace user settings.
    config = workspace / "config.ini"
    template = workspace / "config.template"
    if not config.exists():
        if not template.is_file():
            raise FileNotFoundError("Bundled config.template missing")
        config.write_text(mac_defaults(template.read_text(encoding="utf-8")), encoding="utf-8")
    return workspace, bot


def main() -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("mac_app.py is intended for packaged execution")
    bundle = Path(sys._MEIPASS)
    workspace = Path.home() / "Library" / "Application Support" / "MeshingAround" / "runtime"
    workspace, bot = prepare_workspace(bundle, workspace)
    if "--assistant-mcp" in sys.argv:
        # Started by an assistant (e.g. Claude Desktop) as an MCP stdio server.
        import assistant_mcp
        sys.exit(assistant_mcp.main(workspace / "config.ini", workspace / "data"))
    if "--probe-radio" in sys.argv:
        import radio_probe
        index = sys.argv.index("--probe-radio")
        sys.exit(radio_probe.main(sys.argv[index + 1:index + 3]))
    if "--self-test" in sys.argv:
        print(f"MAC_APP_SELF_TEST_OK: {bot.name}", flush=True)
        return
    from launcher import check_tcp
    launch(workspace, bot, check_tcp)


if __name__ == "__main__":
    main()
