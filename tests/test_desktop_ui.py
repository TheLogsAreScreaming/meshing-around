"""Builds the real Tk window and exercises every screen without a radio.

Skipped when no display is available. Nothing is sent to a radio: the TCP
probe is stubbed and the bot is never started.
"""
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))

import tkinter as tk

from appearance import THEMES, TEXT_SIZES, load_preferences


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise unittest.SkipTest(f"No display: {exc}")
    root.withdraw()
    return root


class DesktopUITests(unittest.TestCase):
    def setUp(self):
        import dashboard
        self.dashboard = dashboard
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "config.template", self.tmp / "config.template")
        self.prefs = self.tmp / "desktop.json"
        self.root = _root()
        self.app = dashboard.DesktopApp(self.root, self.tmp, ROOT / "mesh_bot.py",
                                        lambda address: True, prefs_path=self.prefs)
        self.root.update_idletasks()

    def tearDown(self):
        self.app.dispose()
        self.root.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pump(self):
        # Lay out and redraw. A full update() can spin forever on macOS when a
        # second Tk window in one process has a recurring timer, so tests avoid it.
        self.root.update_idletasks()

    def test_every_page_renders(self):
        for key, title, _icon, _subtitle in self.dashboard.PAGES:
            self.app.show(key)
            self.pump()
            self.assertEqual(self.app.page_title.cget("text"), title)
            self.assertTrue(self.app.nav[key].selected)

    def test_every_theme_and_text_size_applies_and_persists(self):
        for name in THEMES:
            self.app.select_theme(name)
            self.pump()
            self.assertEqual(self.root.cget("bg"), THEMES[name]["bg"])
        self.assertEqual(load_preferences(self.prefs)["theme"], list(THEMES)[-1])
        for size in TEXT_SIZES:
            self.app._set_text_size(size)
            self.pump()
        self.assertEqual(load_preferences(self.prefs)["text_size"], TEXT_SIZES[-1])
        self.app.restore_appearance()
        self.assertEqual(load_preferences(self.prefs)["text_size"], "Default")

    def test_radio_edits_validate_and_save(self):
        self.app.show("radio")
        self.assertFalse(self.app.save_button.enabled)
        self.app.mode.set("tcp")  # the bare template defaults to USB serial
        self.app.endpoint.set("radio.local:99999")
        self.pump()
        self.assertTrue(self.app.address.error)
        self.assertFalse(self.app.save_button.enabled)
        self.app.endpoint.set("192.168.1.50")
        self.pump()
        self.assertIsNone(self.app.address.error)
        self.assertTrue(self.app.save_button.enabled)
        self.app.save_radio_settings()
        self.assertIn("hostname = 192.168.1.50", (self.tmp / "config.ini").read_text())
        self.assertFalse(self.app.save_button.enabled)
        self.app.mode.set("serial")
        self.pump()
        self.assertTrue(self.app.usb_button.frame.winfo_ismapped())
        self.app.revert_radio()
        self.assertEqual(self.app.mode.get(), "tcp")

    def test_connection_result_states(self):
        self.app.probe_settings = (self.app.mode.get(), self.app.endpoint.get())
        self.app.probe_active = True
        self.app._probe_finished("radio_error", ("ConnectionRefusedError", "[Errno 61] Connection refused"))
        self.assertEqual(self.app.radio_state, "error")
        self.assertEqual(self.app.radio_banner.tone, "danger")
        self.app.probe_active = True
        self.app._probe_finished("radio", {"long_name": "Base", "short_name": "BS", "hardware": "RAK4631",
                                           "firmware": "2.7.15", "node_num": 1})
        self.assertEqual(self.app.radio_state, "ok")
        self.assertEqual(self.app.side_radio.label.cget("text"), "Reachable")
        self.assertEqual(len(self.app.recent), 2)

    def test_activity_log_strips_color_codes_tags_levels_and_searches(self):
        self.app.show("activity")
        self.app._append(["\x1b[38;5;39m2026-11-06 12:00:00 |    DEBUG | System: hello\x1b[0m\n",
                          "\x1b[38;5;196m2026-11-06 12:00:01 |    ERROR | File not found\x1b[0m\n",
                          "2026-11-06 12:00:02 |     INFO | System: Autoresponder Started for "
                          "Device1 TEST UNIT,TEST. NodeID: 1\n"])
        content = self.app.output.get("1.0", "end")
        self.assertNotIn("\x1b", content)
        self.assertIn("error", self.app.output.tag_names("2.5"))
        self.app.search_text.set("system")
        self.app.find(1)
        self.assertEqual(self.app.match_label.cget("text"), "1 of 2")
        self.app.find(1)
        self.assertEqual(self.app.match_label.cget("text"), "2 of 2")
        self.app.reset_search()
        self.assertEqual(self.app.match_label.cget("text"), "")

    def test_bot_output_updates_radio_state(self):
        self.app._bot_event("INFO | System: Autoresponder Started for Device1 TEST UNIT,TEST. NodeID: 1")
        self.assertEqual(self.app.radio_state, "live")
        self.assertEqual(self.app.radio_title, "TEST UNIT")
        self.app._bot_event("CRITICAL | System: abort. Initializing Interface1 [Errno 61] Connection refused")
        self.assertEqual(self.app.radio_state, "error")

    def test_window_survives_small_sizes(self):
        for size in ("880x600", "1400x900", "880x600"):
            self.root.deiconify()
            self.root.geometry(size)
            for key, *_ in self.dashboard.PAGES:
                self.app.show(key)
                self.pump()


if __name__ == "__main__":
    unittest.main()
