"""Design tokens meet contrast targets in every theme; UI helpers behave."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "desktop"))
from appearance import THEMES
import bot_output
from design_system import BODY_CONTRAST, UI_CONTRAST, contrast, tokens
import ui_text


class ContrastTests(unittest.TestCase):
    def test_text_readable_on_every_surface(self):
        for name in THEMES:
            t = tokens(name)
            for surface in ("background", "surface", "sidebar", "field"):
                for fg in ("text", "text_secondary", "accent_text"):
                    with self.subTest(theme=name, fg=fg, surface=surface):
                        self.assertGreaterEqual(contrast(t[fg], t[surface]), BODY_CONTRAST)

    def test_buttons_and_status_colors(self):
        for name in THEMES:
            t = tokens(name)
            with self.subTest(theme=name):
                self.assertGreaterEqual(contrast(t["on_accent"], t["accent"]), BODY_CONTRAST)
                self.assertGreaterEqual(contrast(t["border_strong"], t["surface"]), UI_CONTRAST)
                for tone in ("success", "warning", "danger", "info"):
                    self.assertGreaterEqual(contrast(t[tone], t[f"{tone}_bg"]), BODY_CONTRAST)
                    self.assertGreaterEqual(contrast(t[tone], t["field"]), BODY_CONTRAST)
                self.assertGreaterEqual(contrast(t["accent_fg"], t["accent_bg"]), BODY_CONTRAST)

    def test_light_theme_available(self):
        self.assertIn("Daylight", THEMES)


class BotOutputTests(unittest.TestCase):
    def test_clean_and_level(self):
        line = bot_output.clean("\x1b[31;1m2026 | CRITICAL | System: abort\x1b[0m\n")
        self.assertEqual(line, "2026 | CRITICAL | System: abort")
        self.assertEqual(bot_output.level(line), "error")
        self.assertEqual(bot_output.level("x |  WARNING | y"), "warning")
        self.assertEqual(bot_output.level("x |    DEBUG | y"), "debug")
        self.assertEqual(bot_output.level("plain"), "info")

    def test_interpret(self):
        self.assertEqual(bot_output.interpret(
            "INFO | System: Autoresponder Started for Device1 TEST UNIT,TEST. NodeID: 1"),
            ("radio_connected", "TEST UNIT"))
        self.assertEqual(bot_output.interpret("System: abort. Initializing Interface1 refused")[0],
                         "radio_failed")
        self.assertEqual(bot_output.interpret("Device disconnected")[0], "radio_lost")
        self.assertIsNone(bot_output.interpret("System: Games Enabled!"))

    def test_format_duration(self):
        self.assertEqual(bot_output.format_duration(42), "42 s")
        self.assertEqual(bot_output.format_duration(185), "3 min")
        self.assertEqual(bot_output.format_duration(3900), "1 h 5 min")

    def test_config_summary_of_shipped_template(self):
        template = pathlib.Path(__file__).resolve().parents[1] / "config.template"
        info = bot_output.config_summary(template)
        self.assertIn("Bulletin board (BBS)", info["features"])
        self.assertTrue(info["dm_only"])
        with tempfile.TemporaryDirectory() as folder:
            missing = bot_output.config_summary(pathlib.Path(folder) / "none.ini")
            self.assertEqual(missing["features"], [])


class WordingTests(unittest.TestCase):
    def test_friendly_errors(self):
        self.assertIn("refused", ui_text.friendly_error("tcp", "ConnectionRefusedError", "refused")[0])
        self.assertIn("find", ui_text.friendly_error("tcp", "gaierror", "nodename nor servname")[0])
        self.assertIn("respond", ui_text.friendly_error("tcp", "TimeoutError", "timed out")[0])
        self.assertIn("USB", ui_text.friendly_error("serial", "SerialException", "busy")[0])
        self.assertEqual(ui_text.friendly_error("tcp", "ValueError", "bad port")[1], "bad port")
        # A programming error mentioning "timeout" must not be reported as a radio timeout.
        self.assertNotIn("respond", ui_text.friendly_error(
            "tcp", "TypeError", "unexpected keyword argument 'timeout'")[0])

    def test_exit_messages(self):
        self.assertEqual(ui_text.exit_message(-15, True), ("neutral", "Stopped"))
        self.assertEqual(ui_text.exit_message(1, False)[0], "danger")


if __name__ == "__main__":
    unittest.main()
