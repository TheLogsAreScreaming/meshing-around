"""Reusable themed widgets for the desktop interface.

Built from plain Tk widgets because macOS ignores background colors on native
tk.Button, which made every button grey with low-contrast text. Each container
remembers the surface token it is painted with, so children pick a matching
background without hard-coded colors.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import icons
from design_system import SPACE, tone_colors


def bg_token(widget) -> str:
    while widget is not None:
        token = getattr(widget, "_bg_token", None)
        if token:
            return token
        widget = widget.master
    return "background"


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
    """Bordered surface with optional heading; returns (outer, body)."""
    outer = surface(parent, theme, "surface", border=True)
    body = surface(outer, theme, "surface")
    pad = SPACE[padding]
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
    """Keyboard-accessible button with primary/secondary/ghost/danger styles."""

    def __init__(self, parent, theme, label, command, variant="secondary", width=None):
        self.theme, self.command, self.variant = theme, command, variant
        self.enabled = True
        self._hover = self._pressed = self._focused = False
        self.parent_bg = bg_token(parent)
        self.frame = tk.Frame(parent, bd=0, padx=2, pady=2)
        # Ghost buttons read as links, so they hug their text and line up with it.
        self.label = tk.Label(self.frame, text=label, font=theme.font("body_strong"),
                              padx=SPACE["xs"] if variant == "ghost" else SPACE["l"],
                              pady=SPACE["xs"] + 2, bd=0, cursor="hand2",
                              takefocus=1, width=width)
        self.label.pack(fill="both", expand=True)
        for widget in (self.frame, self.label):
            widget.bind("<Enter>", lambda e: self._set(hover=True))
            widget.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.label.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.label.bind("<ButtonRelease-1>", self._release)
        self.label.bind("<Return>", lambda e: self.invoke())
        self.label.bind("<KP_Enter>", lambda e: self.invoke())
        self.label.bind("<space>", lambda e: self.invoke())
        self.label.bind("<FocusIn>", lambda e: self._set(focused=True))
        self.label.bind("<FocusOut>", lambda e: self._set(focused=False))
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
        inside = 0 <= event.x <= self.label.winfo_width() and 0 <= event.y <= self.label.winfo_height()
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
            self.label.configure(cursor="hand2" if enabled else "arrow",
                                 takefocus=1 if enabled else 0)
            self._paint()

    def set_label(self, value: str):
        if self.label.cget("text") != value:
            self.label.configure(text=value)

    def set_variant(self, variant: str):
        if variant != self.variant:
            self.variant = variant
            self._paint()

    def _set(self, **state):
        for key, value in state.items():
            setattr(self, f"_{key}", value)
        self._paint()

    def _paint(self):
        if not self.label.winfo_exists():
            return
        c = self.theme.colors
        surround = c[self.parent_bg]
        active = self._hover or self._pressed
        if not self.enabled:
            fill, fg, edge = c["field"], c["text_disabled"], c["border"]
        elif self.variant == "primary":
            fill = c["accent_hover"] if active else c["accent"]
            fg, edge = c["on_accent"], fill
        elif self.variant == "danger":
            fill = c["hover"] if active else c["danger_bg"]
            fg, edge = c["danger"], c["danger"]
        elif self.variant == "ghost":
            fill = c["hover"] if active else surround
            fg, edge = c["accent_text"], surround
        else:
            fill = c["hover"] if active else c["field"]
            fg, edge = c["text"], c["border_strong"]
        if self._focused and self.enabled:
            # Primary fill is the accent color, so its ring uses the text color.
            edge = c["text"] if self.variant == "primary" else c["focus"]
        self.label.configure(bg=fill, fg=fg)
        self.frame.configure(bg=edge)


class Pill(tk.Frame):
    """Status indicator: colored dot plus short label."""

    def __init__(self, parent, theme, value="", tone="neutral", style="callout"):
        super().__init__(parent, bd=0, padx=SPACE["s"], pady=SPACE["xxs"] + 1)
        self.theme, self.tone = theme, tone
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
        self.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg)
        self.dot.configure(bg=bg)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 7, 7, fill=fg, outline=fg)


class Segmented(tk.Frame):
    """Mutually exclusive choice, e.g. connection method. Arrow keys move."""

    def __init__(self, parent, theme, variable, options, on_change=None):
        super().__init__(parent, bd=0, padx=1, pady=1)
        self.theme, self.variable, self.on_change = theme, variable, on_change
        self.items = []
        for index, (value, label) in enumerate(options):
            item = tk.Label(self, text=label, font=theme.font("body_strong"), padx=SPACE["l"],
                            pady=SPACE["xs"] + 2, bd=0, cursor="hand2", takefocus=1,
                            highlightthickness=2)
            item.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 1, 0))
            self.columnconfigure(index, weight=1, uniform="segment")
            item.bind("<Button-1>", lambda e, v=value: self.select(v))
            item.bind("<space>", lambda e, v=value: self.select(v))
            item.bind("<Return>", lambda e, v=value: self.select(v))
            item.bind("<Left>", lambda e, i=index: self._step(i, -1))
            item.bind("<Right>", lambda e, i=index: self._step(i, 1))
            self.items.append((value, item))
        variable.trace_add("write", lambda *a: self._paint())
        theme.listen(lambda t: self._paint())

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
        c = self.theme.colors
        self.configure(bg=c["border_strong"])
        for value, item in self.items:
            selected = value == self.variable.get()
            item.configure(bg=c["accent"] if selected else c["field"],
                           fg=c["on_accent"] if selected else c["text"],
                           highlightbackground=c["accent"] if selected else c["field"],
                           highlightcolor=c["focus"] if not selected else c["on_accent"])


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
        self.box = tk.Frame(self, bd=0, padx=1, pady=1)
        self.box.pack(fill="x", pady=(SPACE["xs"] + 2, SPACE["xs"]))
        self.inner = tk.Frame(self.box, bd=0, padx=SPACE["s"], pady=SPACE["s"] - 1)
        self.inner.pack(fill="x")
        self.entry = tk.Entry(self.inner, textvariable=variable, font=theme.font("body"), bd=0,
                              relief="flat", highlightthickness=0)
        self.entry.pack(fill="x")
        for widget in (self.box, self.inner):
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
        edge = c["danger"] if self.error else (c["focus"] if self._focused else c["border_strong"])
        # The 1px box padding is the border; it thickens on focus or error.
        ring = 2 if (self._focused or self.error) else 1
        self.box.configure(bg=edge, padx=ring, pady=ring)
        self.inner.configure(bg=c["field"])
        self.entry.configure(bg=c["field"], fg=c["text"], insertbackground=c["text"],
                             selectbackground=c["accent"], selectforeground=c["on_accent"])
        self.helper.configure(fg=c["danger"] if self.error else c["text_secondary"])


class Banner(tk.Frame):
    """Inline message for results, warnings and errors, with optional details."""

    ICONS = {"success": "success", "danger": "danger", "warning": "warning",
             "info": "info", "accent": "info", "neutral": "info"}

    def __init__(self, parent, theme, dismissible=True):
        super().__init__(parent, bd=0, padx=SPACE["m"], pady=SPACE["m"], highlightthickness=1)
        self.theme, self.tone = theme, "info"
        self._bg_token = "info_bg"
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
        return "neutral_bg" if self.tone == "neutral" else f"{self.tone}_bg"

    def _paint(self):
        if not self.winfo_exists():
            return
        fg, bg = tone_colors(self.theme.colors, self.tone)
        c = self.theme.colors
        self.configure(bg=bg, highlightbackground=fg, highlightcolor=fg)
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


class ScrollArea(tk.Frame):
    """Vertical scrolling container; `body` holds the page content."""

    def __init__(self, parent, theme, token="background"):
        super().__init__(parent, bd=0)
        self._bg_token = token
        theme.paint(self, bg=token)
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, yscrollincrement=12)
        theme.paint(self.canvas, bg=token)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                       style="App.Vertical.TScrollbar")
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
