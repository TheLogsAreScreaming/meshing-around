"""Draw the Meshing Around app icon. Needs only Python, plus macOS for the .icns.

Run `python desktop/make_icon.py` to regenerate desktop/assets/AppIcon.icns.
"""
from __future__ import annotations

import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

from icons import MESH_LINKS, MESH_NODES

SIZE = 1024
TOP, BOTTOM = (22, 58, 104), (6, 15, 32)
LINK, NODE, HUB = (64, 196, 224), (40, 217, 232), (214, 253, 255)
HALF = 412          # macOS icon body is 824 of 1024
ART = 285           # distance of the outermost nodes from the centre
LINK_WIDTH = 15
NODE_RADIUS = 50
HUB_RADIUS = 92


def body(x, y, offset_y=0.0):
    """Approximate signed distance to the rounded-square icon body."""
    px, py = abs(x) / HALF, abs(y - offset_y) / HALF
    return ((px ** 5 + py ** 5) ** 0.2 - 1) * HALF


def segment(x, y, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def over(under, color, alpha):
    return tuple(u + (c - u) * alpha for u, c in zip(under, color))


def coverage(distance):
    return max(0.0, min(1.0, 0.5 - distance))


def render() -> bytes:
    nodes = [(x * ART, y * ART) for x, y in MESH_NODES]
    links = [(nodes[a], nodes[b]) for a, b in MESH_LINKS]
    rows = bytearray()
    for row in range(SIZE):
        rows.append(0)
        y = row + 0.5 - SIZE / 2
        shade = over(TOP, BOTTOM, (y + HALF) / (2 * HALF))
        for column in range(SIZE):
            x = column + 0.5 - SIZE / 2
            inside = coverage(body(x, y))
            shadow = 0.32 * max(0.0, min(1.0, -body(x, y, 16) / 30 + 0.5))
            if inside <= 0:
                rows += bytes((0, 0, 0, round(255 * shadow)))
                continue
            color = shade
            hub_distance = math.hypot(x - nodes[0][0], y - nodes[0][1])
            glow = 0.42 * math.exp(-(hub_distance / 250) ** 2)
            color = over(color, NODE, glow)
            nearest = min(segment(x, y, a, b) for a, b in links)
            color = over(color, LINK, 0.85 * coverage(nearest - LINK_WIDTH))
            for px, py in nodes[1:]:
                color = over(color, NODE, coverage(math.hypot(x - px, y - py) - NODE_RADIUS))
            color = over(color, BOTTOM, coverage(hub_distance - HUB_RADIUS - 16))
            color = over(color, HUB, coverage(hub_distance - HUB_RADIUS))
            alpha = inside + (1 - inside) * shadow
            rows += bytes((*(round(c) for c in color), round(255 * alpha)))
    return bytes(rows)


def png(pixels: bytes) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


def build_icns(master: Path, target: Path) -> None:
    with tempfile.TemporaryDirectory() as folder:
        iconset = Path(folder) / "AppIcon.iconset"
        iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = points * scale
                suffix = "@2x" if scale == 2 else ""
                out = iconset / f"icon_{points}x{points}{suffix}.png"
                if pixels == SIZE:
                    shutil.copy(master, out)
                else:
                    subprocess.run(["sips", "-z", str(pixels), str(pixels), str(master), "--out", str(out)],
                                   check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)], check=True)


def main() -> int:
    assets = Path(__file__).with_name("assets")
    assets.mkdir(exist_ok=True)
    master = assets / "AppIcon-1024.png"
    master.write_bytes(png(render()))
    if sys.platform == "darwin":
        build_icns(master, assets / "AppIcon.icns")
    print(f"Wrote {master}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
