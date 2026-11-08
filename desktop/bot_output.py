"""Interpret the original bot's console output for the desktop interface.

Pure functions only (no Tk), so they can be unit tested.
"""
from __future__ import annotations

import configparser
from pathlib import Path
import re

from recovery_diagnostics import classify

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
STARTED = re.compile(r"Autoresponder Started for Device\d+ ([^,]+)")
FAILED = re.compile(r"abort\. Initializing Interface\d+ (.*)")


def clean(line: str) -> str:
    """Remove terminal color codes and trailing whitespace."""
    return ANSI.sub("", line).rstrip()


def level(line: str) -> str:
    """'error', 'warning', 'debug' or 'info' for coloring a log line."""
    if "| CRITICAL |" in line or "|    ERROR |" in line or "| ERROR |" in line \
            or line.startswith("Traceback") or "Error:" in line[:60]:
        return "error"
    if "| WARNING |" in line or "|  WARNING |" in line:
        return "warning"
    if "|    DEBUG |" in line or "| DEBUG |" in line:
        return "debug"
    return "info"


def interpret(line: str):
    """(event, detail) for lines that change radio state, else None."""
    match = STARTED.search(line)
    if match:
        return "radio_connected", match.group(1).strip()
    match = FAILED.search(line)
    if match:
        return "radio_failed", match.group(1).strip()
    event = classify(line)
    if event == "disconnected":
        return "radio_lost", line
    if event == "retrying":
        return "radio_retrying", line
    return None


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


FEATURE_NAMES = {
    "bbs": "Bulletin board (BBS)",
    "location": "Location & weather",
    "games": "Games",
    "checklist": "Check-in list",
    "inventory": "Inventory",
    "qrz": "QRZ greeting",
    "repeater": "Repeater",
    "scheduler": "Scheduled messages",
    "emergencyHandler": "Emergency keyword handler",
    "dataPersistence": "Save data between runs",
    "smtp": "Email",
}
BROADCASTS = (("sentry", "SentryEnabled", "Proximity alerts"),
              ("sentry", "highFlyingAlert", "High-altitude node alerts"),
              ("location", "ipawsAlertEnabled", "Emergency alerts"))


def config_summary(path: Path) -> dict:
    """Enabled modules and unprompted broadcasts from the bot's config.ini."""
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return {"features": [], "broadcasts": [], "dm_only": None}

    def enabled(section, option):
        try:
            return cfg.getboolean(section, option, fallback=False)
        except ValueError:
            return False

    features = [FEATURE_NAMES.get(name, name) for name in cfg.sections()
                if name in FEATURE_NAMES and enabled(name, "enabled")]
    broadcasts = [label for section, option, label in BROADCASTS if enabled(section, option)]
    dm_only = enabled("general", "respond_by_dm_only") if cfg.has_section("general") else None
    return {"features": features, "broadcasts": broadcasts, "dm_only": dm_only}
