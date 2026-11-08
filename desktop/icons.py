"""Small line icons drawn on a Tk canvas so they follow theme colors.

All icons share one 18-unit grid, stroke weight and round caps, giving the
interface a single consistent icon style without bundling image files.
"""
from __future__ import annotations

GRID = 18
NAMES = ("overview", "radio", "bot", "activity", "settings",
         "success", "danger", "warning", "info", "search")


def draw(canvas, name: str, color: str, size: int = GRID) -> None:
    canvas.delete("icon")
    k = size / GRID
    width = max(1.4, 1.6 * k)

    def line(*points, **extra):
        canvas.create_line(*[v * k for v in points], fill=color, width=extra.get("w", width),
                           capstyle="round", joinstyle="round", tags="icon")

    def oval(x0, y0, x1, y1, fill=""):
        canvas.create_oval(x0 * k, y0 * k, x1 * k, y1 * k, outline=color, width=width,
                           fill=fill, tags="icon")

    def rect(x0, y0, x1, y1):
        canvas.create_rectangle(x0 * k, y0 * k, x1 * k, y1 * k, outline=color, width=width, tags="icon")

    def arc(x0, y0, x1, y1, start, extent):
        canvas.create_arc(x0 * k, y0 * k, x1 * k, y1 * k, start=start, extent=extent,
                          style="arc", outline=color, width=width, tags="icon")

    if name == "overview":
        for x, y in ((2.5, 2.5), (10, 2.5), (2.5, 10), (10, 10)):
            rect(x, y, x + 5.5, y + 5.5)
    elif name == "radio":
        line(9, 8, 9, 16)
        oval(7.6, 6.6, 10.4, 9.4, fill=color)
        arc(4.5, 3.5, 13.5, 12.5, 135, 90)
        arc(4.5, 3.5, 13.5, 12.5, -45, 90)
        arc(1.5, 0.5, 16.5, 15.5, 135, 90)
        arc(1.5, 0.5, 16.5, 15.5, -45, 90)
    elif name == "bot":
        rect(3, 6, 15, 15)
        line(9, 6, 9, 3)
        oval(8, 1.5, 10, 3.5, fill=color)
        oval(5.8, 9, 7.6, 10.8, fill=color)
        oval(10.4, 9, 12.2, 10.8, fill=color)
        line(7, 13, 11, 13)
    elif name == "activity":
        line(3, 4.5, 15, 4.5)
        line(3, 9, 12, 9)
        line(3, 13.5, 14, 13.5)
    elif name == "settings":
        line(3, 5, 15, 5)
        line(3, 13, 15, 13)
        oval(9.5, 3, 13.5, 7, fill=canvas["bg"])
        oval(4.5, 11, 8.5, 15, fill=canvas["bg"])
    elif name == "success":
        oval(1.5, 1.5, 16.5, 16.5)
        line(5.5, 9.2, 8, 11.7, 12.5, 6.5)
    elif name == "danger":
        oval(1.5, 1.5, 16.5, 16.5)
        line(6.3, 6.3, 11.7, 11.7)
        line(11.7, 6.3, 6.3, 11.7)
    elif name == "warning":
        line(9, 2, 16.5, 15.5, 1.5, 15.5, 9, 2)
        line(9, 7, 9, 10.5)
        oval(8.4, 12.4, 9.6, 13.6, fill=color)
    elif name == "info":
        oval(1.5, 1.5, 16.5, 16.5)
        line(9, 8.5, 9, 12.5)
        oval(8.4, 5.2, 9.6, 6.4, fill=color)
    elif name == "search":
        oval(2.5, 2.5, 11.5, 11.5)
        line(10.5, 10.5, 15.5, 15.5)
    else:
        raise ValueError(f"Unknown icon: {name}")
