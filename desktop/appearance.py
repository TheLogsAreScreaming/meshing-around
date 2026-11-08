"""Desktop appearance palettes and persistent user preferences."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

DEFAULT_THEME = "Midnight Cyan"
THEMES = {
    "Midnight Cyan": {"bg": "#0d1420", "panel": "#182434", "sidebar": "#111d2b", "fg": "#e8f3ff", "muted": "#a3b6c9", "accent": "#28d9e8", "input": "#233447"},
    "Futuristic Neon": {"bg": "#100e1c", "panel": "#211a36", "sidebar": "#17122b", "fg": "#f6efff", "muted": "#bdb0d6", "accent": "#d05cff", "input": "#302548"},
    "Mocha Mousse": {"bg": "#211b19", "panel": "#352a26", "sidebar": "#2b211d", "fg": "#f5e9dd", "muted": "#c8b3a5", "accent": "#e0ad83", "input": "#483832"},
    "Fun & Vibrant": {"bg": "#15222b", "panel": "#203744", "sidebar": "#192c38", "fg": "#f6fcff", "muted": "#b4d0db", "accent": "#ffb74d", "input": "#2a4856"},
    "Dusk": {"bg": "#1d1c30", "panel": "#302b47", "sidebar": "#26233b", "fg": "#f1eafb", "muted": "#c3b8d7", "accent": "#b39bfa", "input": "#403958"},
    "Daylight": {"bg": "#f3f4f7", "panel": "#ffffff", "sidebar": "#e8ebf0", "fg": "#1a1d23", "muted": "#596271", "accent": "#0b63ce", "input": "#f6f7f9"},
}
TEXT_SIZES = ("Default", "Large", "Larger")
DEFAULT_PREFERENCES = {"theme": DEFAULT_THEME, "text_size": "Default", "reduce_motion": None}


def preferences_path() -> Path:
    return Path.home() / "Library" / "Application Support" / "MeshingAround" / "desktop.json"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_preferences(path: Path | None = None) -> dict:
    """Stored preferences merged over defaults; invalid values fall back."""
    stored = _read(path if path is not None else preferences_path())
    prefs = dict(DEFAULT_PREFERENCES)
    if stored.get("theme") in THEMES:
        prefs["theme"] = stored["theme"]
    if stored.get("text_size") in TEXT_SIZES:
        prefs["text_size"] = stored["text_size"]
    if isinstance(stored.get("reduce_motion"), bool):
        prefs["reduce_motion"] = stored["reduce_motion"]
    return prefs


def save_preferences(changes: dict, path: Path | None = None) -> None:
    """Validate and merge changes into the stored file, keeping other keys."""
    if "theme" in changes and changes["theme"] not in THEMES:
        raise ValueError("Unknown theme")
    if "text_size" in changes and changes["text_size"] not in TEXT_SIZES:
        raise ValueError("Unknown text size")
    if "reduce_motion" in changes and not isinstance(changes["reduce_motion"], (bool, type(None))):
        raise ValueError("Reduce motion must be true, false or unset")
    target = path if path is not None else preferences_path()
    data = _read(target)
    data.update(changes)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False,
                                         encoding="utf-8") as handle:
            temp = handle.name
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def load_theme(path: Path | None = None) -> str:
    return load_preferences(path)["theme"]


def save_theme(theme: str, path: Path | None = None) -> None:
    save_preferences({"theme": theme}, path)


def system_reduce_motion() -> bool:
    """Whether macOS Accessibility → Display → Reduce motion is on."""
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                                capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == "1"
