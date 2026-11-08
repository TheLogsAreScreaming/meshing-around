"""Reusable themed widgets for the desktop interface.

Built from plain Tk widgets because macOS ignores background colors on native
tk.Button, which made every button grey with low-contrast text. Each container
remembers the surface token it is painted with, so children pick a matching
background without hard-coded colors.
"""
from __future__ import annotations

import tkinter as tk

import icons
from design_system import RADIUS, SPACE, mix, tone_colors


def bg_token(widget) -> str:
    while widget is not None:
        token = getattr(widget, "_bg_token", None)
        if token:
            return token
        widget = widget.master
    return "background"


def tone_bg_token(tone: str) -> str:
    return f"{tone}_bg"


def tone_fg_token(tone: str) -> str:
    return "accent_fg" if tone == "accent" else tone


def rounded_points(x0, y0, x1, y1, radius):
    """Control points for a smoothed polygon that draws a rounded rectangle."""
    r = max(0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    return [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y0 + r, x1, y1 - r, x1, y1 - r, x1, y1, x1 - r, y1, x1 - r, y1,
            x0 + r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r,
            x0, y0 + r, x0, y0]


def draw_rounded(canvas, x0, y0, x1, y1, radius, fill, outline="", width=1):
    return canvas.create_polygon(rounded_points(x0, y0, x1, y1, radius), smooth=True,
                                 splinesteps=16, fill=fill, outline=outline, width=width)


class RoundedFrame(tk.Frame):
    """Container with a rounded background; children sit on top of it.

    The shape is drawn on a canvas placed behind the children, so the frame still
    sizes itself from its content. Keep content inside the corners with padding.
    """

    def __init__(self, parent, theme, fill="surface", outline=None, radius=RADIUS["m"], edge=1, **options):
        super().__init__(parent, bd=0, highlightthickness=0, **options)
        self.theme, self.parent_token = theme, bg_token(parent)
        self.fill, self.outline, self.radius, self.edge = fill, outline, radius, edge
        self._bg_token = fill
        self.backing = tk.Canvas(self, bd=0, highlightthickness=0, width=1, height=1)
        self.backing.place(x=0, y=0, relwidth=1, relheight=1, bordermode="ignore")
        self.backing.lower()
        self.backing.bind("<Configure>", lambda e: self._draw())
        theme.listen(lambda t: self.repaint())

    def restyle(self, fill=None, outline=..., edge=None):
        """Change token-based styling; pass outline=None to remove the outline."""
        self.fill = fill or self.fill
        self._bg_token = self.fill
        self.outline = self.outline if outline is ... else outline
        self.edge = edge or self.edge
        self.repaint()

    def repaint(self):
        if self.winfo_exists():
            behind = self.theme.colors[self.parent_token]
            self.configure(bg=behind)
            self.backing.configure(bg=behind)
            self._draw()

    def _draw(self):
        width, height = self.backing.winfo_width(), self.backing.winfo_height()
        self.backing.delete("all")
        if width <= 1 or height <= 1:
            return
        c = self.theme.colors
        inset = self.edge / 2 if self.outline else 0
        draw_rounded(self.backing, inset, inset, width - inset, height - inset, self.radius,
                     c[self.fill], c[self.outline] if self.outline else "",
                     self.edge if self.outline else 0)


def surface(parent, theme, token: str = "surface", border: bool = False) -> tk.Frame:
    frame = tk.Frame(parent, bd=0, highlightthickness=1 if border else 0)
    frame._bg_token = token
    roles = {"bg": token}
    if border:
        roles.update(highlightbackground="border", highlightcolor="border")
    theme.paint(frame, **roles)
    return frame


def text(parent, theme, value=None, variable=None, style="body", tone="text",
         wrap=False, justify="left", **options) -> tk.Label:
    label = tk.Label(parent, text=value, textvariable=variable, font=theme.font(style),
                     anchor="w", justify=justify, bd=0, padx=0, pady=0, **options)
    theme.paint(label, bg=bg_token(parent), fg=tone)
    if wrap:
        # A wrapped label requests almost no width of its own; its size comes from the
        # layout. Otherwise grids size columns from the text, the text re-wraps to the
        # new column width, and the window never settles.
        label.configure(width=1)
        # Re-wrap to the allocated width so text never clips when resized. Using the
        # exact width (and skipping no-op updates) keeps this from feeding back on itself.
        def rewrap(event):
            width = max(event.width, 40)
            if int(str(label.cget("wraplength")) or 0) != width:
                label.configure(wraplength=width)
        label.bind("<Configure>", rewrap)
    return label


def card(parent, theme, title=None, subtitle=None, padding="l"):
    """Rounded surface with optional heading; returns (outer, body)."""
    outer = RoundedFrame(parent, theme, "surface", "border", radius=RADIUS["l"])
    body = surface(outer, theme, "surface")
    pad = SPACE[padding] + 4
    body.pack(fill="both", expand=True, padx=pad, pady=pad)
    if title:
        text(body, theme, title, style="headline").pack(fill="x")
    if subtitle:
        text(body, theme, subtitle, style="callout", tone="text_secondary", wrap=True).pack(
            fill="x", pady=(SPACE["xxs"], 0))
    return outer, body


def eyebrow(parent, theme, value):
    return text(parent, theme, value.upper(), style="caption", tone="text_secondary")


def divider(parent, theme):
    line = tk.Frame(parent, height=1, bd=0)
    theme.paint(line, bg="border")
    return line


def icon_badge(parent, theme, name, tone="accent", size=18):
    """Icon on a soft tinted tile, used to anchor cards visually."""
    badge = RoundedFrame(parent, theme, tone_bg_token(tone), radius=RADIUS["m"], padx=7, pady=7)
    Icon(badge, theme, name, tone_fg_token(tone), size=size).pack()
    return badge


class Icon(tk.Canvas):
    def __init__(self, parent, theme, name, tone="text", size=18):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.theme, self.name, self.tone, self.size = theme, name, tone, size
        self._bg = bg_token(parent)
        theme.listen(self._redraw)

    def set(self, name=None, tone=None, bg=None):
        self.name = name or self.name
        self.tone = tone or self.tone
        self._bg = bg or self._bg
        self._redraw(self.theme)

    def _redraw(self, theme):
        if not self.winfo_exists():
            return
        colors = theme.colors
        self.configure(bg=colors[self._bg])
        icons.draw(self, self.name, colors[self.tone], self.size)


class Button:
    """Keyboard-accessible rounded button: primary/secondary/ghost/danger."""

    def __init__(self, parent, theme, label, command, variant="secondary"):
        self.theme, self.command, self.variant, self.caption = theme, command, variant, label
        self.enabled = True
        self._hover = self._pressed = self._focused = False
        self.parent_bg = bg_token(parent)
        self.frame = tk.Canvas(parent, bd=0, highlightthickness=0, takefocus=1, cursor="hand2",
                               width=1, height=1)
        self.frame.bind("<Enter>", lambda e: self._set(hover=True))
        self.frame.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.frame.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.frame.bind("<ButtonRelease-1>", self._release)
        self.frame.bind("<Return>", lambda e: self.invoke())
        self.frame.bind("<KP_Enter>", lambda e: self.invoke())
        self.frame.bind("<space>", lambda e: self.invoke())
        self.frame.bind("<FocusIn>", lambda e: self._set(focused=True))
        self.frame.bind("<FocusOut>", lambda e: self._set(focused=False))
        self.frame.bind("<Configure>", lambda e: self._paint())
        theme.listen(lambda t: self._paint())

    def pack(self, **kw):
        self.frame.pack(**kw)
        return self

    def grid(self, **kw):
        self.frame.grid(**kw)
        return self

    def pack_forget(self):
        self.frame.pack_forget()

    def _release(self, event):
        inside = 0 <= event.x <= self.frame.winfo_width() and 0 <= event.y <= self.frame.winfo_height()
        self._set(pressed=False)
        if inside:
            self.invoke()

    def invoke(self):
        if self.enabled and self.command:
            self.command()
        return "break"

    def set_enabled(self, enabled: bool):
        if enabled != self.enabled:
            self.enabled = enabled
            self.frame.configure(cursor="hand2" if enabled else "arrow", takefocus=1 if enabled else 0)
            self._paint()

    def set_label(self, value: str):
        if self.caption != value:
            self.caption = value
            self._paint()

    def set_variant(self, variant: str):
        if variant != self.variant:
            self.variant = variant
            self._paint()

    def _set(self, **state):
        for key, value in state.items():
            setattr(self, f"_{key}", value)
        self._paint()

    def _colors(self):
        c = self.theme.colors
        surround = c[self.parent_bg]
        active = self._hover or self._pressed
        if not self.enabled:
            return c["field"], c["text_disabled"], c["border"]
        if self.variant == "primary":
            fill = c["accent_hover"] if active else c["accent"]
            return fill, c["on_accent"], fill
        if self.variant == "danger":
            return c["hover"] if active else c["danger_bg"], c["danger"], c["danger"]
        if self.variant == "ghost":
            fill = mix(surround, c["text"], 0.1) if active else surround
            return fill, c["accent_text"], fill
        return c["hover"] if active else c["field"], c["text"], c["border_strong"]

    def _paint(self):
        canvas = self.frame
        if not canvas.winfo_exists():
            return
        c, font = self.theme.colors, self.theme.font("body_strong")
        pad_x = SPACE["s"] if self.variant == "ghost" else SPACE["l"] + 2
        want_w = font.measure(self.caption) + 2 * pad_x + 4
        want_h = font.metrics("linespace") + 2 * (SPACE["s"] + 1) + 2
        if (int(canvas.cget("width")), int(canvas.cget("height"))) != (want_w, want_h):
            canvas.configure(width=want_w, height=want_h)
        width = canvas.winfo_width() if canvas.winfo_width() > 1 else want_w
        height = canvas.winfo_height() if canvas.winfo_height() > 1 else want_h
        fill, fg, edge = self._colors()
        focused = self._focused and self.enabled
        if focused:
            # Primary fill is the accent color, so its ring uses the text color.
            edge = c["text"] if self.variant == "primary" else c["focus"]
        canvas.configure(bg=c[self.parent_bg])
        canvas.delete("all")
        draw_rounded(canvas, 1, 1, width - 1, height - 1, RADIUS["m"], fill, edge, 2 if focused else 1)
        canvas.create_text(width / 2, height / 2 + (1 if self._pressed else 0), text=self.caption,
                           font=font, fill=fg)


class Pill(RoundedFrame):
    """Status indicator: colored dot plus short label."""

    def __init__(self, parent, theme, value="", tone="neutral", style="callout"):
        super().__init__(parent, theme, tone_bg_token(tone), radius=RADIUS["pill"],
                         padx=SPACE["s"] + 2, pady=SPACE["xxs"] + 1)
        self.tone = tone
        self.dot = tk.Canvas(self, width=8, height=8, highlightthickness=0, bd=0)
        self.dot.pack(side="left", padx=(0, SPACE["xs"] + 2))
        self.label = tk.Label(self, text=value, font=theme.font(style), bd=0)
        self.label.pack(side="left")
        theme.listen(lambda t: self._paint())

    def set(self, value: str, tone: str):
        if (value, tone) != (self.label.cget("text"), self.tone):
            self.tone = tone
            self.label.configure(text=value)
            self._paint()

    def _paint(self):
        if not self.winfo_exists():
            return
        fg, bg = tone_colors(self.theme.colors, self.tone)
        self.restyle(fill=tone_bg_token(self.tone))
        self.label.configure(bg=bg, fg=fg)
        self.dot.configure(bg=bg)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 7, 7, fill=fg, outline=fg)


class StepBadge(tk.Canvas):
    """Small numbered circle for setup steps."""

    def __init__(self, parent, theme, size=24):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.theme, self.size, self.parent_bg = theme, size, bg_token(parent)
        self.value, self.fg, self.bg = "", "#000000", "#ffffff"

    def set(self, value, fg, bg):
        self.value, self.fg, self.bg = value, fg, bg
        self.configure(bg=self.theme.colors[self.parent_bg])
        self.delete("all")
        self.create_oval(1, 1, self.size - 1, self.size - 1, fill=bg, outline=bg)
        self.create_text(self.size / 2, self.size / 2, text=value, fill=fg,
                         font=self.theme.font("caption"))


class BrandMark(tk.Canvas):
    """The app's mesh mark, matching the Dock icon."""

    def __init__(self, parent, theme, size=36):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.theme, self.size, self.parent_bg = theme, size, bg_token(parent)
        theme.listen(lambda t: self._draw())

    def _draw(self):
        if not self.winfo_exists():
            return
        s = self.size
        self.configure(bg=self.theme.colors[self.parent_bg])
        self.delete("all")
        draw_rounded(self, 0.5, 0.5, s - 0.5, s - 0.5, s * 0.25, "#123257")
        points = [(s / 2 + x * s * 0.34, s / 2 + y * s * 0.34) for x, y in icons.MESH_NODES]
        for a, b in icons.MESH_LINKS:
            self.create_line(*points[a], *points[b], fill="#40c4e0", width=1)
        for index, (x, y) in enumerate(points):
            r = s * (0.11 if index == 0 else 0.055)
            color = "#d6fdff" if index == 0 else "#28d9e8"
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=color)


class MeshHero(RoundedFrame):
    """Overview headline with a mesh illustration that lights up when live."""

    def __init__(self, parent, theme):
        super().__init__(parent, theme, "accent_bg", radius=RADIUS["xl"])
        self.live = False
        self.art = tk.Canvas(self, width=250, height=112, highlightthickness=0, bd=0)
        self.art.pack(side="right", padx=(0, SPACE["xl"]), pady=SPACE["s"])
        copy = surface(self, theme, "accent_bg")
        copy.pack(side="left", fill="both", expand=True, padx=(SPACE["xl"], SPACE["l"]), pady=SPACE["l"])
        spacer_top = surface(copy, theme, "accent_bg")
        spacer_top.pack(expand=True)
        self.headline = text(copy, theme, "", style="title")
        self.headline.pack(fill="x")
        self.detail = text(copy, theme, "", style="body", wrap=True)
        self.detail.pack(fill="x", pady=(SPACE["xxs"], 0))
        surface(copy, theme, "accent_bg").pack(expand=True)
        theme.listen(lambda t: self._draw_art())

    def set(self, headline, detail, live):
        self.headline.configure(text=headline)
        self.detail.configure(text=detail)
        if live != self.live:
            self.live = live
            self._draw_art()

    def _draw_art(self):
        if not self.winfo_exists():
            return
        c = self.theme.colors
        bg, art = c["accent_bg"], self.art
        lit = c["success"] if self.live else c["accent_fg"]
        art.configure(bg=bg)
        art.delete("all")
        cx, cy, sx, sy = 125, 56, 118, 66
        points = [(cx + x * sx, cy + y * sy) for x, y in icons.MESH_NODES]
        for a, b in icons.MESH_LINKS:
            art.create_line(*points[a], *points[b], fill=mix(bg, lit, 0.4), width=2)
        for index, (x, y) in enumerate(points):
            r = 12 if index == 0 else 6
            if index == 0:
                art.create_oval(x - 19, y - 19, x + 19, y + 19, fill=mix(bg, lit, 0.25), outline="")
            art.create_oval(x - r, y - r, x + r, y + r, fill=lit, outline=lit)


class Segmented(RoundedFrame):
    """Mutually exclusive choice, e.g. connection method. Arrow keys move."""

    def __init__(self, parent, theme, variable, options, on_change=None):
        super().__init__(parent, theme, "field", "border_strong", radius=RADIUS["m"] + 2, padx=3, pady=3)
        self.variable, self.on_change = variable, on_change
        self.items, self._labels, self._focus = [], {}, None
        for index, (value, label) in enumerate(options):
            item = tk.Canvas(self, bd=0, highlightthickness=0, cursor="hand2", takefocus=1, width=1, height=1)
            item.grid(row=0, column=index, sticky="nsew")
            self.columnconfigure(index, weight=1, uniform="segment")
            item.bind("<Button-1>", lambda e, v=value: self.select(v))
            item.bind("<space>", lambda e, v=value: self.select(v))
            item.bind("<Return>", lambda e, v=value: self.select(v))
            item.bind("<Left>", lambda e, i=index: self._step(i, -1))
            item.bind("<Right>", lambda e, i=index: self._step(i, 1))
            item.bind("<FocusIn>", lambda e, v=value: self._focused(v))
            item.bind("<FocusOut>", lambda e: self._focused(None))
            item.bind("<Configure>", lambda e: self._paint())
            self.items.append((value, item))
            self._labels[value] = label
        variable.trace_add("write", lambda *a: self._paint())
        theme.listen(lambda t: self._paint())

    def _focused(self, value):
        self._focus = value
        self._paint()

    def _step(self, index, delta):
        value, item = self.items[(index + delta) % len(self.items)]
        self.select(value)
        item.focus_set()
        return "break"

    def select(self, value):
        if self.variable.get() != value:
            self.variable.set(value)
            if self.on_change:
                self.on_change(value)

    def _paint(self):
        if not self.winfo_exists():
            return
        c, font = self.theme.colors, self.theme.font("body_strong")
        for value, item in self.items:
            label = self._labels[value]
            want_w, want_h = font.measure(label) + 2 * SPACE["l"] + 4, font.metrics("linespace") + 2 * SPACE["s"]
            if (int(item.cget("width")), int(item.cget("height"))) != (want_w, want_h):
                item.configure(width=want_w, height=want_h)
            width = item.winfo_width() if item.winfo_width() > 1 else want_w
            height = item.winfo_height() if item.winfo_height() > 1 else want_h
            selected = value == self.variable.get()
            item.configure(bg=c["field"])
            item.delete("all")
            focused = value == self._focus
            if selected or focused:
                ring = (c["on_accent"] if selected else c["focus"]) if focused else ""
                draw_rounded(item, 1, 1, width - 1, height - 1, RADIUS["m"],
                             c["accent"] if selected else c["field"], ring, 2 if focused else 0)
            item.create_text(width / 2, height / 2, text=label, font=font,
                             fill=c["on_accent"] if selected else c["text"])


class Toggle(tk.Frame):
    """On/off switch with a label; Space toggles when focused."""

    def __init__(self, parent, theme, label, variable, on_change=None):
        super().__init__(parent, bd=0)
        self._bg_token = bg_token(parent)
        self.theme, self.variable, self.on_change = theme, variable, on_change
        theme.paint(self, bg=self._bg_token)
        self.switch = tk.Canvas(self, width=38, height=22, highlightthickness=2, bd=0,
                                takefocus=1, cursor="hand2")
        self.switch.pack(side="left")
        self.caption = text(self, theme, label, style="body")
        self.caption.pack(side="left", padx=(SPACE["s"], 0))
        self._position = 1.0 if variable.get() else 0.0
        for widget in (self.switch, self.caption):
            widget.bind("<Button-1>", lambda e: self.toggle())
        self.switch.bind("<space>", lambda e: self.toggle())
        self.switch.bind("<Return>", lambda e: self.toggle())
        variable.trace_add("write", lambda *a: self._animate())
        theme.listen(lambda t: self._draw())

    def toggle(self):
        self.variable.set(not self.variable.get())
        if self.on_change:
            self.on_change(self.variable.get())

    def _animate(self):
        target = 1.0 if self.variable.get() else 0.0
        if self.theme.reduce_motion:
            self._position = target
            self._draw()
            return

        def step():
            if not self.winfo_exists():
                return
            delta = target - self._position
            self._position = target if abs(delta) < 0.2 else self._position + delta * 0.5
            self._draw()
            if self._position != target:
                self.after(16, step)
        step()

    def _draw(self, *_):
        if not self.winfo_exists():
            return
        c = self.theme.colors
        on = self.variable.get()
        canvas = self.switch
        canvas.configure(bg=c[self._bg_token], highlightbackground=c[self._bg_token],
                         highlightcolor=c["focus"])
        canvas.delete("all")
        track = c["accent"] if on else c["border_strong"]
        canvas.create_oval(1, 1, 21, 21, fill=track, outline=track)
        canvas.create_oval(15, 1, 35, 21, fill=track, outline=track)
        canvas.create_rectangle(11, 1, 25, 21, fill=track, outline=track)
        x = 3 + self._position * 14
        knob = c["on_accent"] if on else c["surface"]
        canvas.create_oval(x, 3, x + 16, 19, fill=knob, outline=knob)


class Field(tk.Frame):
    """Single-line text input with label, helper text and error state."""

    def __init__(self, parent, theme, label, variable, helper=""):
        super().__init__(parent, bd=0)
        self._bg_token = bg_token(parent)
        self.theme = theme
        theme.paint(self, bg=self._bg_token)
        self.title = text(self, theme, label, style="body_strong")
        self.title.pack(fill="x")
        self.box = RoundedFrame(self, theme, "field", "border_strong", radius=RADIUS["m"],
                                padx=SPACE["m"], pady=SPACE["s"] + 1)
        self.box.pack(fill="x", pady=(SPACE["xs"] + 2, SPACE["xs"]))
        self.entry = tk.Entry(self.box, textvariable=variable, font=theme.font("body"), bd=0,
                              relief="flat", highlightthickness=0)
        self.entry.pack(fill="x")
        for widget in (self.box, self.box.backing):
            widget.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.helper = text(self, theme, helper, style="callout", tone="text_secondary", wrap=True)
        self.helper.pack(fill="x")
        self.error = None
        self._focused = False
        self.entry.bind("<FocusIn>", lambda e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._focus(False))
        theme.listen(lambda t: self._paint())

    def _focus(self, value):
        self._focused = value
        self._paint()

    def set_label(self, label, helper):
        self.title.configure(text=label)
        self._helper_text = helper
        if not self.error:
            self.helper.configure(text=helper)

    def set_error(self, message):
        self.error = message or None
        self.helper.configure(text=message or getattr(self, "_helper_text", self.helper.cget("text")))
        self._paint()

    def _paint(self):
        if not self.winfo_exists():
            return
        c = self.theme.colors
        edge = "danger" if self.error else ("focus" if self._focused else "border_strong")
        self.box.restyle(outline=edge, edge=2 if (self._focused or self.error) else 1)
        self.entry.configure(bg=c["field"], fg=c["text"], insertbackground=c["text"],
                             selectbackground=c["accent"], selectforeground=c["on_accent"])
        self.helper.configure(fg=c["danger"] if self.error else c["text_secondary"])


class Banner(RoundedFrame):
    """Inline message for results, warnings and errors, with optional details."""

    ICONS = {"success": "success", "danger": "danger", "warning": "warning",
             "info": "info", "accent": "info", "neutral": "info"}

    def __init__(self, parent, theme, dismissible=True):
        super().__init__(parent, theme, "info_bg", "info", radius=RADIUS["m"],
                         padx=SPACE["m"], pady=SPACE["m"])
        self.tone = "info"
        self.icon = tk.Canvas(self, width=18, height=18, highlightthickness=0, bd=0)
        self.icon.grid(row=0, column=0, sticky="n", padx=(0, SPACE["s"]), pady=(1, 0))
        self.title = tk.Label(self, font=theme.font("body_strong"), anchor="w", justify="left", bd=0)
        self.title.grid(row=0, column=1, sticky="ew")
        self.message = tk.Label(self, font=theme.font("callout"), anchor="w", justify="left", bd=0)
        self.message.grid(row=1, column=1, sticky="ew", pady=(SPACE["xxs"], 0))
        self.actions = tk.Frame(self, bd=0)
        self.actions.grid(row=2, column=1, sticky="w", pady=(SPACE["s"], 0))
        self.details = tk.Label(self, font=theme.font("mono"), anchor="w", justify="left", bd=0)
        self.columnconfigure(1, weight=1)
        self.close = None
        if dismissible:
            self.close = tk.Label(self, text="✕", font=theme.font("body"), bd=0, cursor="hand2",
                                  takefocus=1, padx=SPACE["xs"])
            self.close.grid(row=0, column=2, sticky="ne")
            self.close.bind("<Button-1>", lambda e: self.hide())
            self.close.bind("<Return>", lambda e: self.hide())
            self.close.bind("<space>", lambda e: self.hide())
        self.bind("<Configure>", self._wrap)
        self._buttons = []
        self._detail_text = ""
        self._timer = None
        self.visible = False
        self._pack_options = None
        self.actions._bg_token = "info_bg"
        theme.listen(lambda t: self._paint())

    def place_with(self, **pack_options):
        self._pack_options = pack_options

    def _wrap(self, event):
        width = max(event.width - 90, 80)
        for label in (self.title, self.message, self.details):
            label.configure(wraplength=width)

    def show(self, tone, title, message="", details="", actions=(), timeout=None):
        if self._timer:
            self.after_cancel(self._timer)
            self._timer = None
        self.tone = tone
        self.title.configure(text=title)
        self.message.configure(text=message)
        self.message.grid() if message else self.message.grid_remove()
        for button in self._buttons:
            button.frame.destroy()
        self._buttons = []
        self._detail_text = details
        self.details.grid_remove()
        self.actions.configure(bg=tone_colors(self.theme.colors, tone)[1])
        self.actions._bg_token = self._tone_bg()
        items = list(actions)
        if details:
            items.append(("Show details", self._toggle_details))
        for label, command in items:
            button = Button(self.actions, self.theme, label, command, variant="ghost")
            button.pack(side="left", padx=(0, SPACE["s"]))
            self._buttons.append(button)
        self.actions.grid() if items else self.actions.grid_remove()
        self._paint()
        if not self.visible and self._pack_options is not None:
            self.pack(**self._pack_options)
        self.visible = True
        if timeout:
            self._timer = self.after(timeout, self.hide)

    def _toggle_details(self):
        if self.details.winfo_ismapped():
            self.details.grid_remove()
            self._buttons[-1].set_label("Show details")
        else:
            self.details.configure(text=self._detail_text)
            self.details.grid(row=3, column=1, sticky="ew", pady=(SPACE["s"], 0))
            self._buttons[-1].set_label("Hide details")

    def hide(self):
        if self._timer:
            self.after_cancel(self._timer)
            self._timer = None
        if self.visible:
            self.pack_forget()
        self.visible = False

    def _tone_bg(self):
        return tone_bg_token(self.tone)

    def _paint(self):
        if not self.winfo_exists():
            return
        fg, bg = tone_colors(self.theme.colors, self.tone)
        c = self.theme.colors
        self.restyle(fill=self._tone_bg(), outline=tone_fg_token(self.tone))
        self.icon.configure(bg=bg)
        icons.draw(self.icon, self.ICONS.get(self.tone, "info"), fg)
        self.title.configure(bg=bg, fg=fg)
        self.message.configure(bg=bg, fg=c["text"])
        self.details.configure(bg=bg, fg=c["text_secondary"])
        self.actions.configure(bg=bg)
        if self.close:
            self.close.configure(bg=bg, fg=c["text_secondary"])
        for button in self._buttons:
            button.parent_bg = self._tone_bg()
            button._paint()


class Spinner(tk.Canvas):
    """Small activity indicator; static when reduce motion is on."""

    def __init__(self, parent, theme, size=16):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.theme, self.size, self.angle, self.running = theme, size, 90, False
        self._bg = bg_token(parent)
        theme.listen(lambda t: self._draw())

    def start(self):
        if not self.running:
            self.running = True
            self._tick()

    def stop(self):
        self.running = False

    def _tick(self):
        if not self.running or not self.winfo_exists():
            return
        if not self.theme.reduce_motion:
            self.angle = (self.angle - 30) % 360
        self._draw()
        self.after(80, self._tick)

    def _draw(self):
        if not self.winfo_exists():
            return
        c = self.theme.colors
        self.configure(bg=c[self._bg])
        self.delete("all")
        s = self.size
        self.create_oval(2, 2, s - 2, s - 2, outline=c["border"], width=2)
        self.create_arc(2, 2, s - 2, s - 2, start=self.angle, extent=100, style="arc",
                        outline=c["accent_text"], width=2)


class ScrollBar(tk.Canvas):
    """Slim rounded scrollbar; hides its thumb when everything fits."""

    WIDTH = 10
    MIN_THUMB = 32

    def __init__(self, parent, theme, command):
        super().__init__(parent, width=self.WIDTH, height=1, bd=0, highlightthickness=0)
        self.theme, self.command, self.parent_bg = theme, command, bg_token(parent)
        self.first, self.last, self._grab, self._hover = 0.0, 1.0, None, False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_grab", None))
        self.bind("<Enter>", lambda e: self._hovering(True))
        self.bind("<Leave>", lambda e: self._hovering(False))
        theme.listen(lambda t: self._draw())

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _hovering(self, value):
        self._hover = value
        self._draw()

    def thumb(self):
        """(top, bottom) of the thumb in pixels."""
        height = max(self.winfo_height(), 1)
        size = max((self.last - self.first) * height, min(self.MIN_THUMB, height))
        travel = max(height - size, 0)
        span = 1 - (self.last - self.first)
        top = travel * (self.first / span) if span > 0 else 0
        return top, top + size

    def _fraction(self, y):
        top, bottom = self.thumb()
        travel = max(self.winfo_height() - (bottom - top), 1)
        return max(0.0, min(1.0, y / travel)) * (1 - (self.last - self.first))

    def _press(self, event):
        top, bottom = self.thumb()
        if top <= event.y <= bottom:
            self._grab = event.y - top
        else:
            self._grab = (bottom - top) / 2
            self.command("moveto", self._fraction(event.y - self._grab))

    def _drag(self, event):
        if self._grab is not None:
            self.command("moveto", self._fraction(event.y - self._grab))

    def _draw(self):
        if not self.winfo_exists():
            return
        c = self.theme.colors
        self.configure(bg=c[self.parent_bg])
        self.delete("all")
        if self.last - self.first >= 1 or self.winfo_height() <= 1:
            return
        top, bottom = self.thumb()
        color = c["text_secondary"] if self._hover or self._grab is not None else c["border_strong"]
        draw_rounded(self, 2, top + 2, self.WIDTH - 2, bottom - 2, 3, color)


class ScrollArea(tk.Frame):
    """Vertical scrolling container; `body` holds the page content."""

    def __init__(self, parent, theme, token="background"):
        super().__init__(parent, bd=0)
        self._bg_token = token
        theme.paint(self, bg=token)
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, yscrollincrement=12)
        theme.paint(self.canvas, bg=token)
        self.scrollbar = ScrollBar(self, theme, self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        # The scrollbar's width is always reserved by a spacer when it is hidden, so
        # showing it never narrows the content (which would re-wrap text and loop).
        self.spacer = tk.Frame(self, width=14, bd=0)
        theme.paint(self.spacer, bg=token)
        self.spacer.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = surface(self.canvas, theme, token)
        self._window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", self._resize)

    def _resize(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync()

    def _sync(self, *_):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        overflow = self.body.winfo_reqheight() > self.canvas.winfo_height() + 1
        showing = bool(self.scrollbar.winfo_manager())
        if overflow and not showing:
            self.spacer.pack_forget()
            self.scrollbar.pack(side="right", fill="y", before=self.canvas)
        elif not overflow and showing:
            self.scrollbar.pack_forget()
            self.spacer.pack(side="right", fill="y", before=self.canvas)
            self.canvas.yview_moveto(0)

    def scroll(self, event):
        """Scroll from a mouse-wheel event routed by the app window."""
        if self.body.winfo_reqheight() <= self.canvas.winfo_height():
            return
        delta = event.delta if abs(event.delta) < 20 else event.delta // 120
        self.canvas.yview_scroll(-delta, "units")

    def to_top(self):
        self.canvas.yview_moveto(0)
