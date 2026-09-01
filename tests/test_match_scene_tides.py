from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "match_scene_tides.py"
SPEC = importlib.util.spec_from_file_location("match_scene_tides", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MatchSceneTidesTest(unittest.TestCase):
    def write_csv(self, path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_linear_interpolation_and_output_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scenes = root / "scenes.csv"
            tides = root / "tides.csv"
            output = root / "matched.csv"
            self.write_csv(
                scenes,
                ["scene_id", "acquisition_datetime_utc", "tide_status"],
                [
                    {
                        "scene_id": "S2_TEST",
                        "acquisition_datetime_utc": "2026-01-01T00:30:00Z",
                        "tide_status": "unverified",
                    }
                ],
            )
            self.write_csv(
                tides,
                [
                    "datetime_bangkok",
                    "tide_m_msl",
                    "station_name",
                    "datum",
                    "source_url",
                    "qa_status",
                ],
                [
                    {
                        "datetime_bangkok": "2026-01-01T07:00:00+07:00",
                        "tide_m_msl": "1.0",
                        "station_name": "Pak Nam Mae Klong",
                        "datum": "MSL",
                        "source_url": "https://example.test/tide.pdf",
                        "qa_status": "checked",
                    },
                    {
                        "datetime_bangkok": "2026-01-01T08:00:00+07:00",
                        "tide_m_msl": "2.0",
                        "station_name": "Pak Nam Mae Klong",
                        "datum": "MSL",
                        "source_url": "https://example.test/tide.pdf",
                        "qa_status": "checked",
                    },
                ],
            )
            report = MODULE.match_catalog(
                scenes,
                tides,
                output,
                max_gap_minutes=90,
                default_station="Pak Nam Mae Klong",
                default_datum="MSL",
                default_source_url="",
            )
            self.assertEqual(report["matched_count"], 1)
            with output.open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["tide_level"], "1.500")
            self.assertEqual(row["tide_status"], "predicted_interpolated")
            self.assertEqual(row["tide_match_gap_minutes"], "30.0")
            self.assertEqual(row["tide_datum"], "MSL")

    def test_gap_limit_rejects_distant_predictions(self) -> None:
        points = [
            MODULE.TidePoint(
                MODULE.parse_datetime("2026-01-01T00:00:00Z"),
                1.0,
                "Pak Nam Mae Klong",
                "MSL",
                "",
                "checked",
            ),
            MODULE.TidePoint(
                MODULE.parse_datetime("2026-01-01T02:00:00Z"),
                2.0,
                "Pak Nam Mae Klong",
                "MSL",
                "",
                "checked",
            ),
        ]
        result = MODULE.match_tide(
            MODULE.parse_datetime("2026-01-01T01:00:00Z"),
            points,
            [point.epoch_seconds for point in points],
            max_gap_minutes=45,
        )
        self.assertEqual(result["tide_status"], "unmatched_gap")
        self.assertEqual(result["tide_level"], "")

    def test_naive_tide_time_is_bangkok_local_time(self) -> None:
        parsed = MODULE.parse_datetime(
            "2026-01-01T07:00:00", naive_timezone=MODULE.BANGKOK
        )
        self.assertEqual(parsed.isoformat(), "2026-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
