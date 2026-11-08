"""Best-effort real desktop screenshot capture on a logged-in macOS GUI session.

This script never synthesizes screenshots. It exits nonzero if no usable GUI
session or capture is available; the CI step is explicitly optional.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import struct
import time


def valid_png(path: Path) -> bool:
    """Check PNG signature, IHDR and reasonable dimensions without dependencies."""
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
        if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        if header[12:16] != b"IHDR":
            return False
        width, height = struct.unpack(">II", header[16:24])
        return width >= 640 and height >= 480
    except OSError:
        return False


def capture(target: Path, page: str | None = None) -> int:
    """Launch the desktop app (optionally on one section) and screenshot it."""
    if sys.platform != "darwin":
        print("Screenshots require macOS", file=sys.stderr)
        return 2
    if not os.environ.get("DISPLAY") and not os.environ.get("TERM_PROGRAM"):
        print("No confirmed GUI session; attempting macOS capture anyway")
    target.parent.mkdir(parents=True, exist_ok=True)
    launcher = Path(__file__).with_name("launcher.py")
    env = dict(os.environ, MESHING_AROUND_PAGE=page) if page else None
    proc = subprocess.Popen([sys.executable, str(launcher)], cwd=launcher.parent.parent,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        time.sleep(6)
        if proc.poll() is not None:
            print("Desktop application exited before capture", file=sys.stderr)
            return 3
        result = subprocess.run(["screencapture", "-x", str(target)],
                                capture_output=True, text=True, timeout=20)
        if result.returncode or not target.is_file() or target.stat().st_size < 1000 or not valid_png(target):
            target.unlink(missing_ok=True)
            print("No usable macOS screenshot: " + result.stderr.strip(), file=sys.stderr)
            return 4
        print(f"Captured real desktop screen: {target}")
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: capture_dashboard.py OUTPUT.png [overview|radio|bot|activity|settings]")
    raise SystemExit(capture(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else None))
