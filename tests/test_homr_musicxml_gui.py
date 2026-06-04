from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from homr_musicxml_gui import build_timestamped_output_path, load_settings, save_settings


class TestHomrMusicXmlGuiHelpers(unittest.TestCase):
    def test_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_path = tmp_path / "settings.json"
            output_dir = tmp_path / "out"
            output_dir.mkdir()

            save_settings(settings_path, output_dir)

            self.assertEqual(load_settings(settings_path).output_dir, output_dir.resolve())

    def test_load_settings_returns_empty_settings_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "missing.json"

            self.assertIsNone(load_settings(settings_path).output_dir)

    def test_load_settings_ignores_invalid_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text('{"output_dir": "/does/not/exist"}', encoding="utf-8")

            self.assertIsNone(load_settings(settings_path).output_dir)

    def test_load_settings_ignores_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text("{not valid json", encoding="utf-8")

            self.assertIsNone(load_settings(settings_path).output_dir)

    def test_timestamp_output_path_uses_timestamped_musicxml_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = build_timestamped_output_path(
                Path(tmp), now=datetime(2026, 6, 5, 14, 30, 12)
            )

            self.assertEqual(output_path.name, "homr_20260605_143012.musicxml")

    def test_timestamp_output_path_adds_suffix_on_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = build_timestamped_output_path(
                tmp_path, now=datetime(2026, 6, 5, 14, 30, 12)
            )
            first.write_text("existing", encoding="utf-8")

            second = build_timestamped_output_path(
                tmp_path, now=datetime(2026, 6, 5, 14, 30, 12)
            )

            self.assertEqual(second.name, "homr_20260605_143012_1.musicxml")
