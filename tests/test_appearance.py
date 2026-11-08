"""Headless theme persistence tests."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "desktop"))
from appearance import (DEFAULT_THEME, THEMES, load_preferences, load_theme,
                        save_preferences, save_theme)


class ThemeTests(unittest.TestCase):
    def test_original_palettes_kept_and_all_have_required_colors(self):
        for name in ("Midnight Cyan", "Futuristic Neon", "Mocha Mousse", "Fun & Vibrant", "Dusk"):
            self.assertIn(name, THEMES)
        for colors in THEMES.values():
            for key in ("bg", "panel", "sidebar", "fg", "muted", "accent", "input"):
                self.assertRegex(colors[key], r"^#[0-9a-fA-F]{6}$")

    def test_default_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "prefs.json"
            self.assertEqual(load_theme(path), DEFAULT_THEME)
            save_theme("Dusk", path)
            self.assertEqual(load_theme(path), "Dusk")
            path.write_text('{"theme":"invalid"}', encoding="utf-8")
            self.assertEqual(load_theme(path), DEFAULT_THEME)

    def test_older_preference_file_still_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "prefs.json"
            path.write_text('{"theme": "Dusk"}', encoding="utf-8")
            prefs = load_preferences(path)
            self.assertEqual(prefs["theme"], "Dusk")
            self.assertEqual(prefs["text_size"], "Default")
            self.assertIsNone(prefs["reduce_motion"])

    def test_saving_one_preference_keeps_the_others(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "prefs.json"
            save_preferences({"text_size": "Larger", "reduce_motion": True}, path)
            save_theme("Daylight", path)
            prefs = load_preferences(path)
            self.assertEqual((prefs["theme"], prefs["text_size"], prefs["reduce_motion"]),
                             ("Daylight", "Larger", True))
            with self.assertRaises(ValueError):
                save_preferences({"text_size": "Huge"}, path)

    def test_rejects_unknown_theme(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                save_theme("Unknown", pathlib.Path(folder) / "prefs.json")


if __name__ == "__main__":
    unittest.main()
