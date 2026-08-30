from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_rtn_mae_klong_tide_catalog.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "build_rtn_mae_klong_tide_catalog", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakePage:
    width = 1000.0

    def __init__(self, words):
        self._words = words

    def extract_words(self, **_kwargs):
        return self._words


class MaeKlongTideCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_2023_archive_candidates_are_present(self):
        candidates = self.module.year_url_candidates(2023)
        self.assertTrue(
            any("Water_lever66/MSL/KL2023%20msl.pdf" in url for url in candidates)
        )
        self.assertEqual(len(candidates), len(set(candidates)))

    def test_parse_page_rows_requires_day_plus_24_hours(self):
        words = []
        for day in (1, 2):
            top = 100.0 + day * 15.0
            words.append({"text": str(day), "x0": 50.0, "top": top})
            for hour in range(24):
                words.append(
                    {
                        "text": f"{(hour - 12) / 10:.1f}",
                        "x0": 150.0 + hour * 30.0,
                        "top": top + (0.4 if hour % 2 else 0.0),
                    }
                )
        parsed = self.module.parse_page_rows(FakePage(words), expected_days=2)
        self.assertEqual(sorted(parsed), [1, 2])
        self.assertEqual(len(parsed[1]), 24)
        self.assertAlmostEqual(parsed[2][0], -1.2)
        self.assertAlmostEqual(parsed[2][-1], 1.1)

    def test_write_csv_preserves_bangkok_offset_and_provenance(self):
        when = datetime(2026, 1, 1, 0, tzinfo=timezone(timedelta(hours=7)))
        prediction = self.module.HourlyPrediction(
            when_local=when,
            level_m_msl=0.4,
            source_url="https://example.invalid/official.pdf",
            source_year=2026,
            qa_status="official_pdf_parsed_word_coordinates",
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "tides.csv"
            count = self.module.write_csv(output, [prediction])
            text = output.read_text(encoding="utf-8")
        self.assertEqual(count, 1)
        self.assertIn("2026-01-01T00:00:00+07:00", text)
        self.assertIn(",0.4,Pak Nam Mae Klong,MSL,", text)
        self.assertIn("official_pdf_parsed_word_coordinates", text)


if __name__ == "__main__":
    unittest.main()
