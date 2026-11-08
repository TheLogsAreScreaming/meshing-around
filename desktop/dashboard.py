"""Desktop interface for Meshing Around. Runs the original bot as a subprocess.

Layout: a sidebar with five sections (Overview, Radio, Bot, Activity,
Settings) and a persistent status area, plus a macOS menu bar with keyboard
shortcuts. All styling comes from design_system and components.
"""
from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from appearance import (DEFAULT_THEME, THEMES, TEXT_SIZES, load_preferences, save_preferences,
                        system_reduce_motion)
import bot_output
from components import (Banner, Button, Field, Icon, Pill, ScrollArea, Segmented, Spinner,
                        Toggle, bg_token, card, divider, eyebrow, surface, text)
from design_system import CONTENT_MAX_COLUMNS_WIDTH, SIDEBAR_WIDTH, SPACE, Theme, is_dark, tokens
from log_export import export_logs
from radio_config import read_radio, save_radio, validate
import radio_probe
from startup_preflight import check_paths
import ui_text

PAGES = (
    ("overview", "Overview", "overview", "Bot and radio status at a glance"),
    ("radio", "Radio", "radio", "Choose how this Mac connects to your Meshtastic radio"),
    ("bot", "Bot", "bot", "Start, stop and review what the bot does on your mesh"),
    ("activity", "Activity", "activity", "Live output from the bot and connection tests"),
    ("settings", "Settings", "settings", "Appearance, accessibility and app information"),
)
LOG_LIMIT = 5000
MOD = "Command" if sys.platform == "darwin" else "Control"
EXPORT_FOLDER = Path.home() / "Documents" / "Meshing Around Logs"


def reveal(path: Path) -> None:
    """Select a file in Finder, or open a folder (its nearest existing parent)."""
    if sys.platform != "darwin":
        return
    path = Path(path)
    if path.is_file():
        subprocess.Popen(["open", "-R", str(path)])
        return
    while not path.exists() and path != path.parent:
        path = path.parent
    subprocess.Popen(["open", str(path)])


class NavItem(tk.Frame):
    """Sidebar destination with icon, label, hover and selected states."""

    def __init__(self, parent, theme, label, icon_name, command, shortcut):
        super().__init__(parent, bd=0, cursor="hand2", takefocus=1, highlightthickness=2)
        self.theme, self.command, self.selected, self.hover = theme, command, False, False
        self.indicator = tk.Frame(self, width=3, bd=0)
        self.indicator.pack(side="left", fill="y")
        self.icon = Icon(self, theme, icon_name, tone="text_secondary")
        self.icon._bg = "sidebar"
        self.icon.pack(side="left", padx=(SPACE["m"], SPACE["s"] + 2), pady=SPACE["s"] + 1)
        self.label = tk.Label(self, text=label, font=theme.font("body"), anchor="w", bd=0)
        self.label.pack(side="left", fill="x", expand=True)
        self.hint = tk.Label(self, text=shortcut, font=theme.font("callout"), bd=0)
        self.hint.pack(side="right", padx=(0, SPACE["m"]))
        for widget in (self, self.icon, self.label, self.hint, self.indicator):
            widget.bind("<Button-1>", lambda e: self.command())
            widget.bind("<Enter>", lambda e: self._hover(True))
            widget.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Return>", lambda e: self.command())
        self.bind("<space>", lambda e: self.command())
        theme.listen(lambda t: self._paint())

    def _hover(self, value):
        self.hover = value
        self._paint()

    def set_selected(self, value):
        self.selected = value
        self._paint()

    def _paint(self):
        if not self.winfo_exists():
            return
        c = self.theme.colors
        bg = c["selected"] if self.selected else (c["sidebar_hover"] if self.hover else c["sidebar"])
        self.configure(bg=bg, highlightbackground=c["sidebar"], highlightcolor=c["focus"])
        self.indicator.configure(bg=c["accent"] if self.selected else bg)
        self.label.configure(bg=bg, fg=c["text"] if self.selected else c["text_secondary"],
                             font=self.theme.font("body_strong" if self.selected else "body"))
        self.hint.configure(bg=bg, fg=c["text_secondary"])
        self.icon._bg = "selected" if self.selected else ("sidebar_hover" if self.hover else "sidebar")
        self.icon.set(tone="accent_text" if self.selected else "text_secondary")


class DesktopApp:
    def __init__(self, root, root_path, bot_path, tcp_probe, prefs_path=None):
        self.root, self.root_path, self.bot_path, self.tcp_probe = root, Path(root_path), bot_path, tcp_probe
        self.prefs_path = prefs_path
        prefs = load_preferences(prefs_path)
        reduce = prefs["reduce_motion"]
        self.theme = Theme(root, prefs["theme"], prefs["text_size"],
                           system_reduce_motion() if reduce is None else reduce)
        self.config = self.root_path / "config.ini"
        self.template = self.root_path / "config.template"
        transport, address = read_radio(self.config if self.config.exists() else self.template)
        self.mode = tk.StringVar(value=transport)
        self.endpoint = tk.StringVar(value=address or "meshtastic.local")
        self.saved_radio = (transport, address or "meshtastic.local")
        self.events = queue.Queue()
        self.process = None
        self.stop_requested = self.stopping = self.closing = False
        self.started_at = None
        self.probe_active = False
        self.probe_settings = None
        self.radio_state, self.radio_title, self.radio_detail = "untested", "Not tested yet", ""
        self.bot_state, self.bot_note = "stopped", ""
        self.recent = deque(maxlen=6)
        self.page = None
        self.nav = {}
        self.pages = {}
        self.search_hits, self.search_index, self.search_query, self.log_version = [], -1, "", 0
        self.searched_version = -1
        self._restart_pending = False
        self.follow = tk.BooleanVar(value=True)
        self.reduce_motion = tk.BooleanVar(value=self.theme.reduce_motion)
        self.text_size = tk.StringVar(value=self.theme.text_size)
        self.theme_name = tk.StringVar(value=self.theme.name)

        root.title("Meshing Around")
        root.geometry("1140x780")
        root.minsize(880, 600)
        self.theme.paint(root, bg="background")
        self._build_shell()
        self._build_overview()
        self._build_radio()
        self._build_bot()
        self._build_activity()
        self._build_settings()
        self._build_menu()
        self.mode.trace_add("write", lambda *a: self._radio_edited())
        self.endpoint.trace_add("write", lambda *a: self._radio_edited())
        root.protocol("WM_DELETE_WINDOW", self.request_quit)
        try:
            root.createcommand("tk::mac::Quit", self.request_quit)
            root.createcommand("tk::mac::ShowPreferences", lambda: self.show("settings"))
        except tk.TclError:
            pass
        self.theme.listen(lambda t: self.render() if self.page else None)
        self.theme.listen(self._paint_tiles)
        root.bind_all("<MouseWheel>", self._wheel)
        self.theme.refresh()
        initial = os.environ.get("MESHING_AROUND_PAGE", "overview").lower()
        self.show(initial if initial in dict((p[0], p) for p in PAGES) else "overview")
        self._radio_edited()
        self.render()
        self._poll_id = root.after(100, self.poll)

    def dispose(self):
        """Cancel the event poll; used when the window is torn down in tests."""
        self.root.after_cancel(self._poll_id)

    # ----- shell -------------------------------------------------------------------------

    def _build_shell(self):
        t = self.theme
        shell = surface(self.root, t, "background")
        shell.pack(fill="both", expand=True)
        side = surface(shell, t, "sidebar")
        side.configure(width=SIDEBAR_WIDTH)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        rule = tk.Frame(shell, width=1, bd=0)
        t.paint(rule, bg="border")
        rule.pack(side="left", fill="y")
        brand = surface(side, t, "sidebar")
        brand.pack(fill="x", padx=SPACE["l"] + 2, pady=(SPACE["xl"] + 4, SPACE["xl"]))
        text(brand, t, "Meshing Around", style="title").pack(fill="x")
        text(brand, t, "Meshtastic bot for Mac", style="callout", tone="text_secondary").pack(fill="x")
        for index, (key, label, icon_name, _subtitle) in enumerate(PAGES, start=1):
            item = NavItem(side, t, label, icon_name, lambda k=key: self.show(k), f"⌘{index}")
            item.pack(fill="x", padx=SPACE["s"], pady=1)
            item.bind("<Up>", lambda e, i=index: self._nav_step(i - 2))
            item.bind("<Down>", lambda e, i=index: self._nav_step(i))
            self.nav[key] = item
        status = surface(side, t, "sidebar")
        status.pack(side="bottom", fill="x", padx=SPACE["l"] + 2, pady=SPACE["xl"])
        eyebrow(status, t, "Status").pack(fill="x", pady=(0, SPACE["s"]))
        self.side_bot = self._status_row(status, "Bot", "bot")
        self.side_radio = self._status_row(status, "Radio", "radio")

        content = surface(shell, t, "background")
        content.pack(side="left", fill="both", expand=True)
        header = surface(content, t, "background")
        header.pack(fill="x", padx=SPACE["xxl"], pady=(SPACE["xl"] + 4, SPACE["l"]))
        self.page_title = text(header, t, "", style="display")
        self.page_title.pack(fill="x")
        self.page_subtitle = text(header, t, "", style="body", tone="text_secondary", wrap=True)
        self.page_subtitle.pack(fill="x", pady=(SPACE["xs"], 0))
        self.page_host = surface(content, t, "background")
        self.page_host.pack(fill="both", expand=True)
        self.toast = Banner(content, t)
        self.toast.place_with(fill="x", padx=SPACE["xxl"], pady=(0, SPACE["m"]), before=self.page_host)

    def _status_row(self, parent, label, page):
        row = surface(parent, self.theme, "sidebar")
        row.pack(fill="x", pady=(0, SPACE["s"]))
        name = text(row, self.theme, label, style="callout", tone="text_secondary")
        name.pack(side="left")
        pill = Pill(row, self.theme)
        pill.pack(side="right")
        for widget in (row, name, pill, pill.label, pill.dot):
            widget.bind("<Button-1>", lambda e: self.show(page))
            widget.configure(cursor="hand2")
        return pill

    def _wheel(self, event):
        frame, area = self.pages.get(self.page, (None, None))
        if area is not None:
            area.scroll(event)

    def _nav_step(self, index):
        key = PAGES[index % len(PAGES)][0]
        self.nav[key].focus_set()
        return "break"

    def _page(self, key, scroll=True):
        if scroll:
            area = ScrollArea(self.page_host, self.theme)
            column = surface(area.body, self.theme, "background")
            column.pack(fill="both", expand=True, padx=SPACE["xxl"], pady=(0, SPACE["xxl"]))
            self.pages[key] = (area, area)
            return column
        frame = surface(self.page_host, self.theme, "background")
        self.pages[key] = (frame, None)
        inner = surface(frame, self.theme, "background")
        inner.pack(fill="both", expand=True, padx=SPACE["xxl"], pady=(0, SPACE["xl"]))
        return inner

    def show(self, key):
        if key == self.page:
            return
        for name, (frame, _area) in self.pages.items():
            if name != key:
                frame.pack_forget()
        frame, area = self.pages[key]
        frame.pack(fill="both", expand=True)
        if area:
            area.to_top()
        for name, item in self.nav.items():
            item.set_selected(name == key)
        _key, title, _icon, subtitle = next(p for p in PAGES if p[0] == key)
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        self.page = key
        if key == "bot":
            self._refresh_summary()

    def _build_menu(self):
        root = self.root
        bar = tk.Menu(root)
        accel = "Command" if MOD == "Command" else "Ctrl"

        def add(menu, label, command, key=None):
            shown = "." if key == "period" else key
            menu.add_command(label=label, command=command,
                             accelerator=f"{accel}-{shown}" if key else None)
            if key:
                sequence = key.lower() if len(key) == 1 and key.isalpha() else key
                root.bind_all(f"<{MOD}-{sequence}>", lambda e: (command(), "break")[1])

        view = tk.Menu(bar, tearoff=0)
        for index, (key, label, _i, _s) in enumerate(PAGES, start=1):
            add(view, label, lambda k=key: self.show(k), str(index))
        bar.add_cascade(label="View", menu=view)
        radio = tk.Menu(bar, tearoff=0)
        add(radio, "Test Connection", self.test_connection, "T")
        add(radio, "Save Radio Settings", self.save_radio_settings, "S")
        add(radio, "Find USB Radio", self.find_usb)
        bar.add_cascade(label="Radio", menu=radio)
        bot = tk.Menu(bar, tearoff=0)
        add(bot, "Start Bot", self.start, "R")
        add(bot, "Stop Bot", self.stop, "period")
        add(bot, "Restart Bot", self.restart)
        bar.add_cascade(label="Bot", menu=bot)
        activity = tk.Menu(bar, tearoff=0)
        add(activity, "Find in Activity", self.focus_search, "F")
        add(activity, "Export Activity…", self.export_activity, "E")
        add(activity, "Clear Activity…", self.clear_activity)
        bar.add_cascade(label="Activity", menu=activity)
        root.configure(menu=bar)

    # ----- overview ----------------------------------------------------------------------

    def _build_overview(self):
        t = self.theme
        page = self._page("overview")
        self.setup_outer, setup = card(page, t, "Get started",
                                       "Three steps to put the bot on your mesh.")
        self.setup_outer.pack(fill="x", pady=(0, SPACE["l"]))
        self.setup_rows = []
        steps = (("Choose how your radio connects", "Open radio setup", lambda: self.show("radio")),
                 ("Test the connection", "Test connection", self.test_connection),
                 ("Start the bot", "Start bot", self.start))
        for number, (label, action, command) in enumerate(steps, start=1):
            row = surface(setup, t)
            row.pack(fill="x", pady=(SPACE["m"], 0))
            badge = tk.Label(row, text=str(number), font=t.font("caption"), width=2, bd=0, pady=2)
            badge.pack(side="left")
            name = text(row, t, label, style="body")
            name.pack(side="left", padx=(SPACE["m"], 0))
            button = Button(row, t, action, command, variant="primary")
            self.setup_rows.append((badge, name, button))

        grid = surface(page, t, "background")
        grid.pack(fill="x")
        self.overview_grid = grid
        bot_outer, bot = card(grid, t)
        eyebrow(bot, t, "Bot").pack(fill="x")
        self.ov_bot_pill = Pill(bot, t)
        self.ov_bot_pill.pack(anchor="w", pady=(SPACE["s"], SPACE["s"]))
        self.ov_bot_title = text(bot, t, "", style="headline")
        self.ov_bot_title.pack(fill="x")
        self.ov_bot_detail = text(bot, t, "", style="callout", tone="text_secondary", wrap=True)
        self.ov_bot_detail.pack(fill="x", pady=(SPACE["xxs"], SPACE["l"]))
        row = surface(bot, t)
        row.pack(fill="x")
        self.ov_bot_button = Button(row, t, "Start bot", self.toggle_bot, "primary").pack(side="left")
        Button(row, t, "Bot details", lambda: self.show("bot"), "ghost").pack(side="left", padx=SPACE["s"])

        radio_outer, radio = card(grid, t)
        eyebrow(radio, t, "Radio").pack(fill="x")
        self.ov_radio_pill = Pill(radio, t)
        self.ov_radio_pill.pack(anchor="w", pady=(SPACE["s"], SPACE["s"]))
        self.ov_radio_title = text(radio, t, "", style="headline")
        self.ov_radio_title.pack(fill="x")
        self.ov_radio_detail = text(radio, t, "", style="callout", tone="text_secondary", wrap=True)
        self.ov_radio_detail.pack(fill="x", pady=(SPACE["xxs"], SPACE["l"]))
        row = surface(radio, t)
        row.pack(fill="x")
        self.ov_test_button = Button(row, t, "Test connection", self.test_connection).pack(side="left")
        Button(row, t, "Change", lambda: self.show("radio"), "ghost").pack(side="left", padx=SPACE["s"])
        self.overview_cards = (bot_outer, radio_outer)
        self._columns = None
        grid.bind("<Configure>", self._reflow_overview)

        recent_outer, recent = card(page, t, "Recent activity",
                                    "Connection results and bot events from this session.")
        recent_outer.pack(fill="x", pady=(SPACE["l"], 0))
        self.recent_list = surface(recent, t)
        self.recent_list.pack(fill="x", pady=(SPACE["m"], 0))
        self.recent_empty = text(self.recent_list, t,
                                 "Nothing yet. Test your radio or start the bot and events appear here.",
                                 style="callout", tone="text_secondary", wrap=True)
        self.recent_empty.pack(fill="x")
        Button(recent, t, "Open activity log", lambda: self.show("activity"), "ghost").pack(
            anchor="w", pady=(SPACE["m"], 0))

    def _reflow_overview(self, event):
        columns = 2 if event.width >= CONTENT_MAX_COLUMNS_WIDTH else 1
        if columns == self._columns:
            return
        self._columns = columns
        first, second = self.overview_cards
        gap = SPACE["l"]
        if columns == 2:
            first.grid(row=0, column=0, sticky="nsew", padx=(0, gap // 2))
            second.grid(row=0, column=1, sticky="nsew", padx=(gap // 2, 0), pady=0)
            self.overview_grid.columnconfigure(1, weight=1, uniform="cards")
        else:
            first.grid(row=0, column=0, sticky="nsew", padx=0)
            second.grid(row=1, column=0, sticky="nsew", padx=0, pady=(gap, 0))
            self.overview_grid.columnconfigure(1, weight=0, uniform="")
        self.overview_grid.columnconfigure(0, weight=1, uniform="cards" if columns == 2 else "")

    def _render_recent(self):
        for child in self.recent_list.winfo_children():
            if child is not self.recent_empty:
                child.destroy()
        if not self.recent:
            self.recent_empty.pack(fill="x")
            return
        self.recent_empty.pack_forget()
        for index, (stamp, tone, message) in enumerate(reversed(self.recent)):
            if index:
                divider(self.recent_list, self.theme).pack(fill="x", pady=SPACE["s"])
            row = surface(self.recent_list, self.theme)
            row.pack(fill="x")
            icon = {"success": "success", "danger": "danger", "warning": "warning"}.get(tone, "info")
            Icon(row, self.theme, icon, tone if tone in ("success", "danger", "warning") else "info",
                 size=16).pack(side="left", anchor="n", pady=2)
            text(row, self.theme, stamp, style="callout", tone="text_secondary").pack(
                side="right", anchor="n")
            text(row, self.theme, message, style="body", wrap=True).pack(
                side="left", fill="x", expand=True, padx=(SPACE["s"], SPACE["m"]))

    def note(self, tone, message):
        self.recent.append((time.strftime("%H:%M"), tone, message))
        self._render_recent()

    # ----- radio -------------------------------------------------------------------------

    def _build_radio(self):
        t = self.theme
        page = self._page("radio")
        outer, body = card(page, t, "Connection method")
        outer.pack(fill="x", pady=(0, SPACE["l"]))
        Segmented(body, t, self.mode, ui_text.TRANSPORTS).pack(anchor="w", pady=(SPACE["m"], SPACE["s"]))
        self.method_help = text(body, t, "", style="callout", tone="text_secondary", wrap=True)
        self.method_help.pack(fill="x")

        outer, body = card(page, t)
        outer.pack(fill="x", pady=(0, SPACE["l"]))
        self.address = Field(body, t, "Radio address", self.endpoint)
        self.address.pack(fill="x")
        self.address.entry.bind("<Return>", lambda e: self.save_radio_settings())
        self.usb_button = Button(body, t, "Find USB radio", self.find_usb)

        actions = surface(page, t, "background")
        actions.pack(fill="x")
        self.save_button = Button(actions, t, "Save", self.save_radio_settings, "primary").pack(side="left")
        self.test_button = Button(actions, t, "Test connection", self.test_connection).pack(
            side="left", padx=(SPACE["s"], 0))
        self.radio_spinner = Spinner(actions, t)
        self.revert_button = Button(actions, t, "Revert", self.revert_radio, "ghost")
        self.dirty_label = text(actions, t, "", style="callout", tone="warning")
        self.dirty_label.pack(side="right")

        self.radio_banner = Banner(page, t)
        outer, body = card(page, t, "Good to know")
        outer.pack(fill="x", pady=(SPACE["l"], 0))
        self.radio_banner.place_with(fill="x", pady=(SPACE["l"], 0), before=outer)
        for line in ("A radio talks to one app at a time. Stop the bot before testing.",
                     "Testing reads the radio's name and firmware. Nothing is sent on the mesh.",
                     "Saving keeps a backup of your previous settings next to config.ini."):
            row = surface(body, t)
            row.pack(fill="x", pady=(SPACE["s"], 0))
            text(row, t, "•", style="body", tone="text_secondary").pack(side="left", anchor="n")
            text(row, t, line, style="body", wrap=True).pack(side="left", fill="x", expand=True,
                                                            padx=(SPACE["s"], 0))

    def _radio_edited(self):
        mode = self.mode.get()
        label, helper = ui_text.ADDRESS_HELP.get(mode, ui_text.ADDRESS_HELP["tcp"])
        self.address.set_label(label, helper)
        self.method_help.configure(text=ui_text.METHOD_HELP.get(mode, ""))
        if mode == "serial":
            self.usb_button.pack(anchor="w", pady=(SPACE["s"], 0))
        else:
            self.usb_button.pack_forget()
        try:
            validate(mode, self.endpoint.get())
            self.address.set_error(None)
            valid = True
        except ValueError as exc:
            self.address.set_error(str(exc))
            valid = False
        dirty = (mode, self.endpoint.get().strip()) != self.saved_radio
        self.save_button.set_enabled(dirty and valid)
        self.dirty_label.configure(text="Unsaved changes" if dirty else "")
        if dirty:
            self.revert_button.pack(side="left", padx=(SPACE["s"], 0))
        else:
            self.revert_button.pack_forget()
        if self.radio_state in ("ok", "error") and self.probe_settings != (mode, self.endpoint.get()):
            self.radio_state, self.radio_title = "changed", "Settings changed"
            self.radio_detail = "Test again to check the new settings."
        self.render()

    def revert_radio(self):
        self.mode.set(self.saved_radio[0])
        self.endpoint.set(self.saved_radio[1])

    def bot_running(self):
        return self.process is not None and self.process.poll() is None

    def save_radio_settings(self):
        if self.bot_running():
            messagebox.showwarning("Stop the bot first",
                                   "Radio settings can't change while the bot is running.",
                                   parent=self.root)
            return
        try:
            save_radio(self.config, self.template, self.mode.get(), self.endpoint.get())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Couldn't save radio settings", str(exc), parent=self.root)
            return
        self.saved_radio = (self.mode.get(), self.endpoint.get().strip())
        self.log("Radio settings saved. A backup is kept for existing configurations.")
        self.toast.show("success", "Radio settings saved", timeout=3000)
        self._radio_edited()

    def test_connection(self):
        if self.bot_running():
            self.radio_banner.show("warning", "Stop the bot to test",
                                   "The radio is in use by the bot. A radio talks to one app at a time.")
            return
        if self.probe_active:
            return
        transport, address = self.mode.get(), self.endpoint.get()
        try:
            validate(transport, address)
        except ValueError as exc:
            self.radio_banner.show("danger", "Check the address", str(exc))
            return
        self.probe_settings = (transport, address)
        self.probe_active = True
        self.radio_state, self.radio_title = "testing", "Testing connection…"
        self.radio_detail = f"{ui_text.TRANSPORT_LABEL[transport]} · {address}"
        self.radio_banner.hide()
        self.log(f"Testing {transport} connection to {address}…")
        self.render()

        def worker():
            try:
                if transport == "tcp":
                    self.tcp_probe(address)
                result = radio_probe.probe_with_retry(transport, address)
                self.events.put(("radio", result))
            except Exception as exc:  # radio libraries raise many error types
                self.events.put(("radio_error", (type(exc).__name__, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def find_usb(self):
        try:
            ports = radio_probe.serial_ports()
        except Exception as exc:
            self.radio_banner.show("danger", "USB scan failed", str(exc))
            return
        if not ports:
            self.radio_banner.show("warning", "No USB radio found",
                                   "Check the cable and that the radio is powered on, then try again.")
            return
        self.mode.set("serial")
        self.endpoint.set(ports[0])
        others = f" Also found: {', '.join(ports[1:])}." if len(ports) > 1 else ""
        self.radio_banner.show("info", f"Selected {ports[0]}",
                               f"Save, then test the connection.{others}")
        self.log("USB devices found: " + ", ".join(ports) + f". Selected {ports[0]}.")

    # ----- bot ---------------------------------------------------------------------------

    def _build_bot(self):
        t = self.theme
        page = self._page("bot")
        outer, body = card(page, t)
        outer.pack(fill="x", pady=(0, SPACE["l"]))
        self.bot_pill = Pill(body, t)
        self.bot_pill.pack(anchor="w")
        self.bot_title = text(body, t, "", style="title")
        self.bot_title.pack(fill="x", pady=(SPACE["s"], 0))
        self.bot_detail = text(body, t, "", style="body", tone="text_secondary", wrap=True)
        self.bot_detail.pack(fill="x", pady=(SPACE["xxs"], SPACE["l"]))
        row = surface(body, t)
        row.pack(fill="x")
        self.start_button = Button(row, t, "Start bot", self.start, "primary").pack(side="left")
        self.stop_button = Button(row, t, "Stop bot", self.stop, "danger").pack(
            side="left", padx=(SPACE["s"], 0))
        self.restart_button = Button(row, t, "Restart", self.restart).pack(side="left", padx=(SPACE["s"], 0))
        self.bot_banner = Banner(page, t)

        outer, body = card(page, t, "When the bot is running",
                           "Based on the bot's configuration file.")
        outer.pack(fill="x", pady=(0, SPACE["l"]))
        self.summary = surface(body, t)
        self.summary.pack(fill="x", pady=(SPACE["s"], 0))
        self.bot_banner.place_with(fill="x", pady=(0, SPACE["l"]), before=outer)

        outer, body = card(page, t, "Advanced")
        outer.pack(fill="x")
        self.advanced = surface(body, t)
        self.advanced_button = Button(body, t, "Show advanced options", self.toggle_advanced, "ghost")
        self.advanced_button.pack(anchor="w", pady=(SPACE["s"], 0))
        text(self.advanced, t, "Configuration file", style="body_strong").pack(fill="x", pady=(SPACE["s"], 0))
        text(self.advanced, t, str(self.config), style="mono", tone="text_secondary", wrap=True).pack(
            fill="x", pady=(SPACE["xxs"], SPACE["s"]))
        text(self.advanced, t, "The bot has many more options than this app shows. Edit config.ini "
             "to change them; changes apply the next time the bot starts. config.template lists "
             "every option with notes.", style="callout", tone="text_secondary", wrap=True).pack(fill="x")
        row = surface(self.advanced, t)
        row.pack(fill="x", pady=(SPACE["m"], 0))
        Button(row, t, "Open config file", self.open_config).pack(side="left")
        Button(row, t, "Show in Finder", lambda: reveal(self.config if self.config.exists() else self.root_path),
               "ghost").pack(side="left", padx=(SPACE["s"], 0))

    def toggle_advanced(self):
        if self.advanced.winfo_ismapped():
            self.advanced.pack_forget()
            self.advanced_button.set_label("Show advanced options")
        else:
            self.advanced.pack(fill="x", before=self.advanced_button.frame)
            self.advanced_button.set_label("Hide advanced options")

    def open_config(self):
        if not self.config.exists():
            messagebox.showinfo("No configuration yet", "Save your radio settings first.", parent=self.root)
            return
        if self.bot_running():
            messagebox.showinfo("Bot is running",
                                "You can edit the file now; changes apply after you restart the bot.",
                                parent=self.root)
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", str(self.config)])

    def _refresh_summary(self):
        for child in self.summary.winfo_children():
            child.destroy()
        info = bot_output.config_summary(self.config if self.config.exists() else self.template)
        mode, address = self.saved_radio
        rows = [("Radio", f"{ui_text.TRANSPORT_LABEL.get(mode, mode)} · {address}")]
        if info["dm_only"] is not None:
            rows.append(("Replies", "To direct messages only" if info["dm_only"]
                         else "To direct messages and channel messages"))
        rows.append(("Features", ", ".join(info["features"]) or "None enabled"))
        rows.append(("Automatic broadcasts", ", ".join(info["broadcasts"]) + " — on" if info["broadcasts"]
                     else "Off — the bot only posts when someone messages it"))
        for index, (label, value) in enumerate(rows):
            row = surface(self.summary, self.theme)
            row.pack(fill="x", pady=(SPACE["s"], 0))
            row.columnconfigure(1, weight=1)
            text(row, self.theme, label, style="body", tone="text_secondary", width=18).grid(
                row=0, column=0, sticky="nw")
            text(row, self.theme, value, style="body", wrap=True).grid(row=0, column=1, sticky="ew")

    def toggle_bot(self):
        self.stop() if self.bot_running() else self.start()

    def start(self):
        if (self.mode.get(), self.endpoint.get().strip()) != self.saved_radio:
            self.show("radio")
            self.radio_banner.show("warning", "Save your radio settings first",
                                   "The bot starts with your saved settings.",
                                   actions=(("Save now", self.save_radio_settings),))
            return
        if self.closing or self.stopping:
            self.toast.show("info", "The bot is still stopping", "Try again in a moment.", timeout=3000)
            return
        if self.bot_running():
            return
        if self.probe_active:
            self.toast.show("info", "Connection test in progress",
                            "Start the bot after the test finishes.", timeout=3000)
            return
        try:
            check_paths(self.root_path, self.bot_path)
            command = ([str(self.bot_path)] if getattr(sys, "frozen", False)
                       else [sys.executable, "-u", str(self.bot_path)])
            child = subprocess.Popen(command, cwd=self.root_path, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as exc:
            messagebox.showerror("The bot couldn't start", str(exc), parent=self.root)
            return
        self.process = child
        self.stop_requested = False
        self.started_at = time.monotonic()
        self.bot_state, self.bot_note = "running", ""
        self.bot_banner.hide()
        self.radio_state, self.radio_title = "connecting", "Connecting…"
        self.radio_detail = "The bot is connecting to your radio."
        self.log("Started original mesh_bot.py using saved radio settings.")
        self.note("info", "Bot started")
        self.render()

        def reader():
            for line in child.stdout:
                self.events.put(("log", line))
            self.events.put(("exit", (child, child.wait())))
        threading.Thread(target=reader, daemon=True).start()
        self._tick()

    def stop(self, wait=False):
        child = self.process
        if child is None or child.poll() is not None or self.stopping:
            return
        self.stopping = self.stop_requested = True
        self.bot_state = "stopping"
        child.terminate()
        self.log("Stop requested")
        self.render()

        def ensure_stopped():
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                self.events.put(("log", "Bot did not stop within 5 seconds; force-stopped."))
        if wait:
            ensure_stopped()
        else:
            threading.Thread(target=ensure_stopped, daemon=True).start()

    def restart(self):
        if not self.bot_running():
            self.start()
            return
        self._restart_pending = True
        self.stop()

    def _tick(self):
        if self.bot_state == "running" and self.started_at is not None:
            self.render()
            self.root.after(1000, self._tick)

    # ----- activity ----------------------------------------------------------------------

    def _build_activity(self):
        t = self.theme
        page = self._page("activity", scroll=False)
        bar = surface(page, t, "background")
        bar.pack(fill="x", pady=(0, SPACE["m"]))
        box = tk.Frame(bar, bd=0, padx=1, pady=1)
        box.pack(side="left")
        inner = surface(box, t, "field")
        inner.pack(fill="both")
        Icon(inner, t, "search", "text_secondary", size=14).pack(side="left", padx=(SPACE["s"], SPACE["xs"]))
        self.search_text = tk.StringVar()
        self.search_entry = tk.Entry(inner, textvariable=self.search_text, font=t.font("body"),
                                     bd=0, highlightthickness=0, width=26)
        self.search_entry.pack(side="left", ipady=SPACE["xs"] + 2, padx=(0, SPACE["s"]))
        t.paint(self.search_entry, bg="field", fg="text", insertbackground="text")
        t.paint(box, bg="border_strong")
        self.search_entry.bind("<FocusIn>", lambda e: box.configure(bg=t.colors["focus"]))
        self.search_entry.bind("<FocusOut>", lambda e: box.configure(bg=t.colors["border_strong"]))
        self.search_entry.bind("<Return>", lambda e: self.find(1))
        self.search_entry.bind("<Shift-Return>", lambda e: self.find(-1))
        self.search_entry.bind("<Escape>", lambda e: self.reset_search())
        self.search_text.trace_add("write", lambda *a: self._search_changed())
        Button(bar, t, "Previous", lambda: self.find(-1)).pack(side="left", padx=(SPACE["s"], 0))
        Button(bar, t, "Next", lambda: self.find(1)).pack(side="left", padx=(SPACE["xs"], 0))
        self.match_label = text(bar, t, "", style="callout", tone="text_secondary")
        self.match_label.pack(side="left", padx=(SPACE["m"], 0))
        Button(bar, t, "Clear…", self.clear_activity, "danger").pack(side="right")
        Button(bar, t, "Export…", self.export_activity).pack(side="right", padx=(0, SPACE["s"]))

        frame = surface(page, t, "field", border=True)
        frame.pack(fill="both", expand=True)
        self.output = tk.Text(frame, state="disabled", bd=0, padx=SPACE["m"], pady=SPACE["m"],
                              font=t.font("mono"), wrap="word", highlightthickness=0,
                              spacing1=1, spacing3=1)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.output.yview,
                               style="App.Vertical.TScrollbar")
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self.empty_state = surface(frame, t, "field")
        Icon(self.empty_state, t, "activity", "text_secondary", size=28).pack()
        text(self.empty_state, t, "No activity yet", style="headline", justify="center").pack(
            pady=(SPACE["s"], SPACE["xxs"]))
        text(self.empty_state, t, "Bot output and connection tests appear here as they happen.",
             style="callout", tone="text_secondary", justify="center").pack()
        self.empty_state.place(relx=0.5, rely=0.42, anchor="center")
        footer = surface(page, t, "background")
        footer.pack(fill="x", pady=(SPACE["s"], 0))
        self.line_count = text(footer, t, "", style="callout", tone="text_secondary")
        self.line_count.pack(side="left")
        Toggle(footer, t, "Follow new output", self.follow,
               lambda on: self.output.see("end") if on else None).pack(side="right")
        t.listen(self._paint_log)

    def _paint_log(self, theme):
        c = theme.colors
        self.output.configure(bg=c["field"], fg=c["text"], insertbackground=c["text"],
                              selectbackground=c["accent"], selectforeground=c["on_accent"])
        self.output.tag_configure("error", foreground=c["danger"])
        self.output.tag_configure("warning", foreground=c["warning"])
        self.output.tag_configure("debug", foreground=c["log_debug"])
        self.output.tag_configure("hit", background=c["search_hit"])
        self.output.tag_configure("current", background=c["accent"], foreground=c["on_accent"])
        self.output.tag_raise("current")

    def log(self, message):
        self._append([message])

    def _append(self, lines):
        out = self.output
        out.configure(state="normal")
        for raw in lines:
            line = bot_output.clean(raw)
            out.insert("end", line + "\n", bot_output.level(line))
        count = int(out.index("end-1c").split(".")[0]) - 1
        if count > LOG_LIMIT:
            # Bound memory during long sessions with verbose bot logs.
            out.delete("1.0", f"{count - LOG_LIMIT + 1}.0")
            count = LOG_LIMIT
        if self.follow.get():
            out.see("end")
        out.configure(state="disabled")
        self.log_version += 1
        if count and self.empty_state.winfo_manager():
            self.empty_state.place_forget()
        self.line_count.configure(text=f"{count:,} lines" + (" · showing the latest 5,000"
                                                            if count >= LOG_LIMIT else ""))

    def _search_changed(self):
        if not self.search_text.get():
            self.reset_search(keep_focus=True)

    def find(self, direction):
        query = self.search_text.get().strip()
        out = self.output
        if not query:
            return
        if query != self.search_query or self.searched_version != self.log_version:
            out.tag_remove("hit", "1.0", "end")
            self.search_hits, start = [], "1.0"
            count = tk.IntVar()
            while True:
                index = out.search(query, start, stopindex="end", nocase=True, count=count)
                if not index or not count.get():
                    break
                end = f"{index}+{count.get()}c"
                self.search_hits.append((index, end))
                out.tag_add("hit", index, end)
                start = end
            self.search_query, self.searched_version = query, self.log_version
            self.search_index = -1 if direction > 0 else 0
        out.tag_remove("current", "1.0", "end")
        if not self.search_hits:
            self.match_label.configure(text="No matches", fg=self.theme.colors["warning"])
            return
        self.search_index = (self.search_index + direction) % len(self.search_hits)
        index, end = self.search_hits[self.search_index]
        out.tag_add("current", index, end)
        out.see(index)
        self.match_label.configure(text=f"{self.search_index + 1} of {len(self.search_hits)}",
                                   fg=self.theme.colors["text_secondary"])

    def reset_search(self, keep_focus=False):
        if self.search_text.get():
            self.search_text.set("")
        self.output.tag_remove("hit", "1.0", "end")
        self.output.tag_remove("current", "1.0", "end")
        self.search_hits, self.search_index, self.search_query = [], -1, ""
        self.match_label.configure(text="")
        if not keep_focus:
            self.search_entry.focus_set()

    def focus_search(self):
        self.show("activity")
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def export_activity(self):
        try:
            target = export_logs(EXPORT_FOLDER, self.output.get("1.0", "end-1c"))
        except OSError as exc:
            messagebox.showerror("Couldn't export activity", str(exc), parent=self.root)
            return
        self.log(f"Exported diagnostics to {target}")
        self.toast.show("success", "Activity exported", str(target),
                        actions=(("Show in Finder", lambda: reveal(target)),), timeout=6000)

    def clear_activity(self):
        if self.output.index("end-1c") == "1.0":
            return
        if not messagebox.askyesno("Clear activity?",
                                   "This clears the window only. The bot keeps running and exported "
                                   "files are not affected.", icon="warning", parent=self.root):
            return
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.reset_search(keep_focus=True)
        self.log_version += 1
        self.line_count.configure(text="")
        self.empty_state.place(relx=0.5, rely=0.42, anchor="center")

    # ----- settings ----------------------------------------------------------------------

    def _build_settings(self):
        t = self.theme
        page = self._page("settings")
        outer, body = card(page, t, "Appearance", "Your choices are saved and restored next time.")
        outer.pack(fill="x", pady=(0, SPACE["l"]))
        eyebrow(body, t, "Theme").pack(fill="x", pady=(SPACE["l"], SPACE["s"]))
        tiles = surface(body, t)
        tiles.pack(fill="x")
        self.theme_tiles = {}
        for index, name in enumerate(THEMES):
            tile = self._theme_tile(tiles, name)
            tile.grid(row=index // 3, column=index % 3, sticky="ew",
                      padx=(0 if index % 3 == 0 else SPACE["s"], 0), pady=(0, SPACE["s"]))
            tiles.columnconfigure(index % 3, weight=1, uniform="tiles")
        eyebrow(body, t, "Text size").pack(fill="x", pady=(SPACE["l"], SPACE["s"]))
        Segmented(body, t, self.text_size, [(s, s) for s in TEXT_SIZES],
                  on_change=self._set_text_size).pack(anchor="w")
        eyebrow(body, t, "Motion").pack(fill="x", pady=(SPACE["l"], SPACE["s"]))
        Toggle(body, t, "Reduce motion", self.reduce_motion, self._set_reduce_motion).pack(anchor="w")
        text(body, t, "Turns off animated indicators. Follows your Mac's Accessibility setting "
             "until you change it here.", style="callout", tone="text_secondary", wrap=True).pack(
            fill="x", pady=(SPACE["xs"], 0))
        Button(body, t, "Restore default appearance", self.restore_appearance, "ghost").pack(
            anchor="w", pady=(SPACE["l"], 0))

        outer, body = card(page, t, "About")
        outer.pack(fill="x")
        rows = (("Version", "Intel Mac beta"),
                ("Bot data folder", str(self.root_path)),
                ("Exported activity", str(EXPORT_FOLDER)))
        for label, value in rows:
            row = surface(body, t)
            row.pack(fill="x", pady=(SPACE["m"], 0))
            row.columnconfigure(1, weight=1)
            text(row, t, label, style="body", tone="text_secondary", width=18).grid(row=0, column=0, sticky="nw")
            text(row, t, value, style="body", wrap=True).grid(row=0, column=1, sticky="ew")
            if label != "Version":
                Button(row, t, "Show in Finder", lambda v=value: reveal(Path(v)), "ghost").grid(
                    row=0, column=2, sticky="ne")
        divider(body, t).pack(fill="x", pady=SPACE["l"])
        text(body, t, "Keyboard shortcuts", style="body_strong").pack(fill="x")
        shortcuts = (("⌘1 – ⌘5", "Switch section"), ("⌘T", "Test radio connection"),
                     ("⌘S", "Save radio settings"), ("⌘R / ⌘.", "Start / stop the bot"),
                     ("⌘F", "Search activity"), ("⌘E", "Export activity"), ("⌘,", "Settings"))
        grid = surface(body, t)
        grid.pack(fill="x", pady=(SPACE["s"], 0))
        for index, (keys, action) in enumerate(shortcuts):
            text(grid, t, keys, style="mono", tone="text_secondary", width=12).grid(
                row=index, column=0, sticky="w", pady=1)
            text(grid, t, action, style="body").grid(row=index, column=1, sticky="w", pady=1)

    def _theme_tile(self, parent, name):
        t = self.theme
        ring = tk.Frame(parent, bd=0, padx=2, pady=2, takefocus=1, cursor="hand2", highlightthickness=0)
        inner = surface(ring, t, "surface")
        inner.pack(fill="both", expand=True)
        preview = tk.Canvas(inner, height=64, highlightthickness=0, bd=0)
        preview.pack(fill="x")
        caption = surface(inner, t, "surface")
        caption.pack(fill="x", padx=SPACE["s"], pady=SPACE["s"])
        title = text(caption, t, name, style="body_strong")
        title.pack(side="left")
        text(caption, t, "Dark" if is_dark(name) else "Light", style="callout",
             tone="text_secondary").pack(side="right")

        def draw(event=None):
            colors = tokens(name)
            width = max(preview.winfo_width(), 120)
            preview.delete("all")
            preview.create_rectangle(0, 0, width, 64, fill=colors["background"], width=0)
            preview.create_rectangle(0, 0, width * 0.28, 64, fill=colors["sidebar"], width=0)
            preview.create_rectangle(width * 0.05, 12, width * 0.22, 18, fill=colors["accent"], width=0)
            preview.create_rectangle(width * 0.05, 26, width * 0.2, 30, fill=colors["text_secondary"], width=0)
            preview.create_rectangle(width * 0.35, 12, width * 0.94, 52, fill=colors["surface"],
                                     outline=colors["border"])
            preview.create_rectangle(width * 0.40, 20, width * 0.7, 26, fill=colors["text"], width=0)
            preview.create_rectangle(width * 0.40, 36, width * 0.56, 44, fill=colors["accent"], width=0)

        preview.bind("<Configure>", draw)
        for widget in (ring, inner, preview, caption, title):
            widget.bind("<Button-1>", lambda e: self.select_theme(name))
        ring.bind("<Return>", lambda e: self.select_theme(name))
        ring.bind("<space>", lambda e: self.select_theme(name))
        ring.bind("<FocusIn>", lambda e: self._paint_tiles())
        ring.bind("<FocusOut>", lambda e: self._paint_tiles())
        self.theme_tiles[name] = ring
        return ring

    def _paint_tiles(self, *_):
        c = self.theme.colors
        focused = self.root.focus_get()
        for name, ring in self.theme_tiles.items():
            if name == self.theme.name:
                color = c["accent"]
            elif focused is ring:
                color = c["focus"]
            else:
                color = c["border"]
            ring.configure(bg=color)

    def select_theme(self, name):
        if name == self.theme.name:
            return
        self.theme_name.set(name)
        self.theme.set_theme(name)
        self._paint_tiles()
        self._persist({"theme": name})

    def _set_text_size(self, size):
        self.theme.set_text_size(size)
        self._persist({"text_size": size})

    def _set_reduce_motion(self, value):
        self.theme.reduce_motion = bool(value)
        self._persist({"reduce_motion": bool(value)})

    def restore_appearance(self):
        self.select_theme(DEFAULT_THEME)
        self.text_size.set("Default")
        self.theme.set_text_size("Default")
        system = system_reduce_motion()
        self.reduce_motion.set(system)
        self.theme.reduce_motion = system
        self._persist({"theme": DEFAULT_THEME, "text_size": "Default", "reduce_motion": None})

    def _persist(self, changes):
        try:
            save_preferences(changes, self.prefs_path)
        except (OSError, ValueError) as exc:
            self.toast.show("danger", "Couldn't save your preference", str(exc))

    # ----- state ------------------------------------------------------------------------

    def render(self):
        """Push bot and radio state into every place that shows it."""
        running = self.bot_running()
        bot_tone, bot_short = {
            "running": ("success", "Running"), "stopping": ("warning", "Stopping"),
            "failed": ("danger", "Stopped"), "stopped": ("neutral", "Stopped"),
        }[self.bot_state]
        if self.bot_state == "running":
            uptime = bot_output.format_duration(time.monotonic() - (self.started_at or time.monotonic()))
            title = "The bot is running"
            detail = f"Running for {uptime}. It answers messages that arrive through your radio."
        elif self.bot_state == "stopping":
            title, detail = "Stopping the bot…", "This takes up to 5 seconds."
        elif self.bot_state == "failed":
            title, detail = "The bot stopped", self.bot_note
        else:
            title = "The bot is stopped"
            detail = "Start the bot to answer messages on your mesh using your saved radio settings."
        for pill in (self.side_bot, self.ov_bot_pill, self.bot_pill):
            pill.set(bot_short, bot_tone)
        self.ov_bot_title.configure(text=title)
        self.ov_bot_detail.configure(text=detail)
        self.bot_title.configure(text=title)
        self.bot_detail.configure(text=detail)
        busy = self.stopping or self.closing
        self.ov_bot_button.set_label("Stop bot" if running else "Start bot")
        self.ov_bot_button.set_variant("danger" if running else "primary")
        self.ov_bot_button.set_enabled(not busy and not self.probe_active)
        self.start_button.set_enabled(not running and not busy and not self.probe_active)
        self.stop_button.set_enabled(running and not busy)
        self.restart_button.set_enabled(running and not busy)

        radio_tone, radio_short = {
            "untested": ("neutral", "Not tested"), "testing": ("info", "Testing"),
            "ok": ("success", "Reachable"), "error": ("danger", "Failed"),
            "changed": ("warning", "Not tested"), "connecting": ("info", "Connecting"),
            "live": ("success", "Connected"), "lost": ("danger", "Disconnected"),
        }[self.radio_state]
        for pill in (self.side_radio, self.ov_radio_pill):
            pill.set(radio_short, radio_tone)
        mode, address = self.saved_radio
        where = f"{ui_text.TRANSPORT_LABEL.get(mode, mode)} · {address}"
        self.ov_radio_title.configure(text=self.radio_title)
        self.ov_radio_detail.configure(text=self.radio_detail or where)
        can_test = not running and not self.probe_active
        self.ov_test_button.set_enabled(can_test)
        self.test_button.set_enabled(can_test)
        self.test_button.set_label("Testing…" if self.probe_active else "Test connection")
        if self.probe_active:
            self.radio_spinner.pack(side="left", padx=(SPACE["s"], 0), after=self.test_button.frame)
            self.radio_spinner.start()
        else:
            self.radio_spinner.stop()
            self.radio_spinner.pack_forget()

        done = (self.config.exists(), self.radio_state in ("ok", "live"), running)
        if all(done):
            self.setup_outer.pack_forget()
        else:
            if not self.setup_outer.winfo_ismapped():
                self.setup_outer.pack(fill="x", pady=(0, SPACE["l"]), before=self.overview_grid)
            next_step = done.index(False)
            c = self.theme.colors
            for index, (badge, name, button) in enumerate(self.setup_rows):
                complete = done[index]
                badge.configure(text="✓" if complete else str(index + 1),
                                bg=c["success_bg"] if complete else c["accent_bg"] if index == next_step
                                else c["neutral_bg"],
                                fg=c["success"] if complete else c["accent_fg"] if index == next_step
                                else c["neutral"])
                name.configure(fg=c["text_secondary"] if complete else c["text"])
                if index == next_step:
                    button.pack(side="right")
                    button.set_enabled(not self.probe_active and not busy)
                else:
                    button.pack_forget()

    def _probe_finished(self, kind, value):
        self.probe_active = False
        transport, address = self.probe_settings
        current = self.probe_settings == (self.mode.get(), self.endpoint.get())
        if kind == "radio":
            summary = radio_probe.describe(value)
            self.log(summary)
            title = f"{value['long_name']} ({value['short_name']})"
            detail = f"{value['hardware']} · firmware {value['firmware']} · {ui_text.TRANSPORT_LABEL[transport]}"
            self.radio_banner.show("success", f"Connected to {title}", detail)
            self.note("success", f"Radio test passed: {title}")
            if current:
                self.radio_state, self.radio_title, self.radio_detail = "ok", title, detail
        else:
            error_type, message = value
            headline, advice = ui_text.friendly_error(transport, error_type, message)
            self.log(f"Connection test failed: {error_type}: {message}")
            self.radio_banner.show("danger", headline, advice, details=f"{error_type}: {message}",
                                   actions=(("Try again", self.test_connection),))
            self.note("danger", f"Radio test failed: {headline}")
            if current:
                self.radio_state, self.radio_title, self.radio_detail = "error", headline, address
        if not current:
            self.radio_state, self.radio_title = "changed", "Settings changed"
            self.radio_detail = "Test again to check the new settings."
        self.render()

    def _bot_event(self, line):
        event = bot_output.interpret(line)
        if not event:
            return
        kind, detail = event
        if kind == "radio_connected":
            self.radio_state, self.radio_title = "live", detail
            self.radio_detail = f"The bot is connected · {ui_text.TRANSPORT_LABEL.get(self.saved_radio[0], '')}"
            self.note("success", f"Bot connected to {detail}")
        elif kind == "radio_failed":
            self.radio_state, self.radio_title = "error", "The bot couldn't connect"
            self.radio_detail = detail
            self.note("danger", f"Bot couldn't connect: {detail}")
        elif kind == "radio_lost":
            self.radio_state, self.radio_title = "lost", "Connection lost"
            self.radio_detail = "The bot will try to reconnect. See Activity for details."
            self.note("warning", "Radio connection lost")
        elif kind == "radio_retrying" and self.radio_state == "lost":
            self.radio_detail = "Reconnecting…"
        self.render()

    def _bot_exited(self, child, code):
        if self.process is not child:
            return
        requested = self.stop_requested
        self.process, self.stopping, self.started_at = None, False, None
        tone, sentence = ui_text.exit_message(code, requested)
        if tone == "danger":
            self.bot_state, self.bot_note = "failed", sentence
            self.bot_banner.show("danger", "The bot stopped unexpectedly", sentence,
                                 actions=(("View activity", lambda: self.show("activity")),
                                          ("Start again", self.start)))
            self.note("danger", "Bot stopped unexpectedly")
        else:
            self.bot_state = "stopped"
            self.note("info", "Bot stopped")
        if self.radio_state in ("live", "connecting", "lost"):
            self.radio_state, self.radio_title, self.radio_detail = "untested", "Not connected", ""
        self.render()
        if getattr(self, "_restart_pending", False):
            self._restart_pending = False
            self.start()

    def poll(self):
        lines = []
        try:
            for _ in range(500):  # keep the window responsive during log bursts
                kind, value = self.events.get_nowait()
                if kind == "log":
                    lines.append(value)
                    self._bot_event(bot_output.clean(value))
                    continue
                if lines:
                    self._append(lines)
                    lines = []
                if kind == "close":
                    self.root.destroy()
                    return
                if kind in ("radio", "radio_error"):
                    self._probe_finished(kind, value)
                elif kind == "exit":
                    self._bot_exited(*value)
        except queue.Empty:
            pass
        if lines:
            self._append(lines)
        self._poll_id = self.root.after(100, self.poll)

    def request_quit(self):
        if self.closing:
            return
        if self.bot_running() and not messagebox.askokcancel(
                "Quit Meshing Around?", "The bot is running. Quitting stops it.",
                icon="warning", parent=self.root):
            return
        self.closing = True
        self.bot_state = "stopping" if self.bot_running() else self.bot_state
        self.render()
        child = self.process

        def shutdown():
            # Waiting on the UI thread would freeze the window during slow shutdown.
            if child is not None and child.poll() is None:
                try:
                    child.terminate()
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                except OSError as exc:
                    self.events.put(("log", f"Shutdown error: {exc}"))
            self.events.put(("close", None))
        threading.Thread(target=shutdown, daemon=True).start()


def launch(root_path, bot_path, tcp_probe):
    root = tk.Tk()
    DesktopApp(root, root_path, bot_path, tcp_probe)
    root.mainloop()
