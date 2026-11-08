"""Design tokens and the runtime theme for the desktop interface.

Every color, font and spacing value used by the screens comes from here, so
the five-plus palettes, text sizes and states stay consistent. Semantic color
tokens are derived from each palette in appearance.THEMES and nudged until
they meet WCAG contrast targets.
"""
from __future__ import annotations

from appearance import THEMES, TEXT_SIZES

# Spacing scale in pixels (4-point grid).
SPACE = {"xxs": 2, "xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24, "xxl": 32}
SIDEBAR_WIDTH = 236
CONTENT_MAX_COLUMNS_WIDTH = 760  # below this, two-column layouts stack

# Type ramp: name -> (point size, weight).
TYPE_SCALE = {
    "display": (24, "bold"),
    "title": (20, "bold"),
    "headline": (15, "bold"),
    "body": (13, "normal"),
    "body_strong": (13, "bold"),
    "callout": (12, "normal"),
    "caption": (11, "bold"),
    "mono": (12, "normal"),
}
TEXT_SCALE = dict(zip(TEXT_SIZES, (1.0, 1.15, 1.3)))

STATUS_DARK = {"success": "#4ade80", "warning": "#fbbf24", "danger": "#f87171", "info": "#60a5fa"}
STATUS_LIGHT = {"success": "#15803d", "warning": "#a16207", "danger": "#b91c1c", "info": "#1d4ed8"}
TONES = ("neutral", "accent", "success", "warning", "danger", "info")

# Minimum contrast ratios (WCAG 2.1 AA).
BODY_CONTRAST = 4.5
UI_CONTRAST = 3.0


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mix(base: str, other: str, amount: float) -> str:
    """Blend amount (0-1) of other into base."""
    a, b = _rgb(base), _rgb(other)
    return _hex(x + (y - x) * amount for x, y in zip(a, b))


def luminance(color: str) -> float:
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def readable_on(background: str) -> str:
    """Near-black or white, whichever reads better on background."""
    return max(("#ffffff", "#111418"), key=lambda color: contrast(color, background))


def ensure_contrast(color: str, *backgrounds: str, target: float = BODY_CONTRAST) -> str:
    """Move color toward black or white until it meets target on every background."""
    darkest = min(backgrounds, key=luminance)
    toward = "#ffffff" if luminance(darkest) < 0.18 else "#000000"
    candidate = color
    for step in range(21):
        candidate = mix(color, toward, step * 0.05)
        if all(contrast(candidate, bg) >= target for bg in backgrounds):
            return candidate
    return candidate


def tokens(theme_name: str) -> dict:
    """Semantic color tokens for one palette."""
    p = THEMES[theme_name]
    dark = luminance(p["bg"]) < 0.4
    status = STATUS_DARK if dark else STATUS_LIGHT
    surfaces = (p["bg"], p["panel"], p["sidebar"], p["input"])
    t = {
        "background": p["bg"],
        "sidebar": p["sidebar"],
        "surface": p["panel"],
        "field": p["input"],
        "text": ensure_contrast(p["fg"], *surfaces),
        "text_secondary": ensure_contrast(p["muted"], *surfaces),
        "accent": p["accent"],
        "accent_text": ensure_contrast(p["accent"], *surfaces),
        "on_accent": readable_on(p["accent"]),
    }
    t["accent_hover"] = mix(p["accent"], t["on_accent"], 0.14)
    t["border"] = mix(p["panel"], p["fg"], 0.13)
    t["border_strong"] = ensure_contrast(mix(p["panel"], p["fg"], 0.30), p["panel"], p["input"],
                                         target=UI_CONTRAST)
    t["hover"] = mix(p["input"], p["fg"], 0.08)
    t["sidebar_hover"] = mix(p["sidebar"], p["fg"], 0.07)
    t["selected"] = mix(p["sidebar"], p["accent"], 0.18)
    t["text_disabled"] = mix(p["input"], p["fg"], 0.42)
    t["focus"] = t["accent_text"]
    t["search_hit"] = mix(p["input"], p["accent"], 0.32)
    t["neutral_bg"] = mix(p["panel"], p["fg"], 0.08)
    t["neutral"] = t["text_secondary"]
    t["accent_bg"] = mix(p["panel"], p["accent"], 0.16)
    t["accent_fg"] = ensure_contrast(p["accent"], t["accent_bg"])
    for name, color in status.items():
        t[f"{name}_bg"] = mix(p["panel"], color, 0.16)
        t[name] = ensure_contrast(color, t[f"{name}_bg"], p["panel"], p["input"])
    t["log_debug"] = t["text_secondary"]
    return t


def is_dark(theme_name: str) -> bool:
    return luminance(THEMES[theme_name]["bg"]) < 0.4


def tone_colors(colors: dict, tone: str) -> tuple[str, str]:
    """(foreground, background) for a status tone."""
    if tone == "accent":
        return colors["accent_fg"], colors["accent_bg"]
    if tone == "neutral":
        return colors["neutral"], colors["neutral_bg"]
    return colors[tone], colors[f"{tone}_bg"]


class Theme:
    """Live theme: named fonts plus a registry of widgets painted with tokens.

    Widgets are registered with token names rather than colors, so switching
    palettes or text sizes repaints the whole window without rebuilding it.
    """

    def __init__(self, root, name: str, text_size: str = "Default", reduce_motion: bool = False):
        from tkinter import font as tkfont
        self.root = root
        self.name = name
        self.text_size = text_size
        self.reduce_motion = reduce_motion
        self.colors = tokens(name)
        family = tkfont.nametofont("TkDefaultFont").actual("family")
        mono = "Menlo" if "Menlo" in tkfont.families(root) else tkfont.nametofont("TkFixedFont").actual("family")
        self.fonts = {}
        for style, (size, weight) in TYPE_SCALE.items():
            self.fonts[style] = tkfont.Font(root, family=mono if style == "mono" else family,
                                            size=self._scaled(size), weight=weight)
        self._painted = []
        self._listeners = []

    def _scaled(self, size: int) -> int:
        return round(size * TEXT_SCALE[self.text_size])

    def font(self, style: str):
        return self.fonts[style]

    def paint(self, widget, **roles):
        """Register widget options (e.g. bg="surface") to follow the theme."""
        self._painted.append((widget, roles))
        self._apply(widget, roles)
        return widget

    def listen(self, callback):
        """Call callback(theme) now and after every theme change."""
        self._listeners.append(callback)
        callback(self)

    def _apply(self, widget, roles):
        widget.configure(**{option: self.colors[token] for option, token in roles.items()})

    def set_theme(self, name: str) -> None:
        self.name = name
        self.colors = tokens(name)
        self.refresh()

    def set_text_size(self, size: str) -> None:
        self.text_size = size
        for style, (base, _weight) in TYPE_SCALE.items():
            self.fonts[style].configure(size=self._scaled(base))
        self.refresh()

    def refresh(self) -> None:
        self._painted = [(w, r) for w, r in self._painted if w.winfo_exists()]
        for widget, roles in self._painted:
            self._apply(widget, roles)
        for callback in list(self._listeners):
            callback(self)
        self._style_ttk()

    def _style_ttk(self) -> None:
        from tkinter import ttk
        c = self.colors
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.Vertical.TScrollbar", background=c["border"], troughcolor=c["background"],
                        bordercolor=c["background"], arrowcolor=c["text_secondary"],
                        lightcolor=c["border"], darkcolor=c["border"], gripcount=0, arrowsize=12)
        style.map("App.Vertical.TScrollbar", background=[("active", c["border_strong"])])
