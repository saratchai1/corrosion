from __future__ import annotations

import csv
import importlib.util
import math
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "scrape_thailandtidetables_mae_klong.py"
)
SPEC = importlib.util.spec_from_file_location("secondary_tides", MODULE_PATH)
assert SPEC and SPEC.loader
secondary_tides = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(secondary_tides)


class SecondaryTideScraperTests(unittest.TestCase):
    def test_parse_event_table_handles_blank_day_and_moon_cell(self) -> None:
        html = """
        <table>
          <tr><th>DAY</th><th>TIME</th><th>HEIGHT</th></tr>
          <tr><td>01</td><td>04:07 (04:07 AM)</td><td>2.11</td></tr>
          <tr><td></td><td>08:16 (08:16 AM)</td><td>2.56</td></tr>
          <tr><td><img alt="First Quarter"></td><td>15:30 (03:30 PM)</td><td>0.83</td></tr>
          <tr><td></td><td>22:10 (10:10 PM)</td><td>3.32</td></tr>
          <tr><td>02</td><td>04:45 (04:45 AM)</td><td>1.85</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = secondary_tides.parse_event_table(soup.find("table"))
        self.assertEqual(len(rows), 5)
        self.assertEqual((rows[2].day, rows[2].hour, rows[2].minute), (1, 15, 30))
        self.assertAlmostEqual(rows[2].height, 0.83)
        self.assertEqual(rows[-1].day, 2)

    def test_parse_month_requires_every_calendar_day(self) -> None:
        rows = []
        for day in range(1, 29):
            rows.append(
                f"<tr><td>{day:02d}</td><td>03:00 (03:00 AM)</td><td>1.00</td></tr>"
            )
            rows.append(
                "<tr><td></td><td>15:00 (03:00 PM)</td><td>3.00</td></tr>"
            )
        html = (
            "<html><body><h1>Pak Nam Mae Klong Tide Tables February 2023</h1>"
            "<table>" + "".join(rows) + "</table></body></html>"
        )
        events = secondary_tides.parse_month(
            html,
            year=2023,
            month=2,
            source_url="https://example.test/2023-02",
            fetched_at_utc="2026-08-30T00:00:00+00:00",
            page_sha256="a" * 64,
            conversion_status="TEST",
        )
        self.assertEqual(len(events), 56)
        self.assertEqual(events[0].event_type_inferred, "LOW")
        self.assertEqual(events[1].event_type_inferred, "HIGH")
        self.assertAlmostEqual(events[0].height_m_msl_candidate, -1.14)

    def test_cosine_interpolation_is_halfway_at_midpoint(self) -> None:
        before = secondary_tides.TideEvent(
            station_id="474",
            station_name="Pak Nam Mae Klong",
            station_name_th="ปากน้ำแม่กลอง",
            latitude=13.3767,
            longitude=99.9956,
            datetime_bangkok="2025-01-01T00:00:00+07:00",
            datetime_utc="2024-12-31T17:00:00+00:00",
            year=2025,
            month=1,
            day=1,
            time_bangkok="00:00",
            event_sequence_in_day=1,
            event_type_inferred="LOW",
            height_m_chart_datum=1.14,
            height_m_msl_candidate=-1.0,
            chart_datum_to_msl_offset_m=2.14,
            msl_conversion_status="TEST",
            source_tier="secondary_published_extrema",
            source_url="https://example.test",
            source_attribution="test",
            page_sha256="a" * 64,
            fetched_at_utc="2026-08-30T00:00:00+00:00",
            qa_status="test",
        )
        after = secondary_tides.TideEvent(
            **{
                **before.__dict__,
                "datetime_bangkok": "2025-01-01T06:00:00+07:00",
                "datetime_utc": "2024-12-31T23:00:00+00:00",
                "time_bangkok": "06:00",
                "event_sequence_in_day": 2,
                "event_type_inferred": "HIGH",
                "height_m_chart_datum": 3.14,
                "height_m_msl_candidate": 1.0,
            }
        )
        target = datetime.fromisoformat("2025-01-01T03:00:00+07:00")
        value = secondary_tides.cosine_between_extrema(target, before, after)
        self.assertTrue(math.isclose(value, 0.0, abs_tol=1e-9))

    def test_complete_scene_catalog_preserves_official_and_fills_secondary(self) -> None:
        base_event = secondary_tides.TideEvent(
            station_id="474",
            station_name="Pak Nam Mae Klong",
            station_name_th="ปากน้ำแม่กลอง",
            latitude=13.3767,
            longitude=99.9956,
            datetime_bangkok="2025-03-01T08:00:00+07:00",
            datetime_utc="2025-03-01T01:00:00+00:00",
            year=2025,
            month=3,
            day=1,
            time_bangkok="08:00",
            event_sequence_in_day=1,
            event_type_inferred="LOW",
            height_m_chart_datum=1.14,
            height_m_msl_candidate=-1.0,
            chart_datum_to_msl_offset_m=2.14,
            msl_conversion_status="TEST",
            source_tier="secondary_published_extrema",
            source_url="https://example.test/2025-03",
            source_attribution="test",
            page_sha256="a" * 64,
            fetched_at_utc="2026-08-30T00:00:00+00:00",
            qa_status="test",
        )
        after = secondary_tides.TideEvent(
            **{
                **base_event.__dict__,
                "datetime_bangkok": "2025-03-01T14:00:00+07:00",
                "datetime_utc": "2025-03-01T07:00:00+00:00",
                "time_bangkok": "14:00",
                "event_sequence_in_day": 2,
                "event_type_inferred": "HIGH",
                "height_m_chart_datum": 3.14,
                "height_m_msl_candidate": 1.0,
            }
        )
        validation = {
            "acceptance": {"status": "PASSED"},
            "metrics_m": {"mean_absolute_error": 0.05},
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scenes.csv"
            output = Path(tmp) / "completed.csv"
            fields = [
                "scene_id",
                "acquisition_datetime_bangkok",
                "tide_station",
                "tide_level",
                "tide_datum",
                "tide_status",
                "tide_source_url",
                "tide_match_method",
                "tide_match_gap_minutes",
                "tide_prediction_qa",
            ]
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "scene_id": "secondary",
                        "acquisition_datetime_bangkok": "2025-03-01T11:00:00+07:00",
                        "tide_status": "unmatched_no_bracket",
                    }
                )
                writer.writerow(
                    {
                        "scene_id": "official",
                        "acquisition_datetime_bangkok": "2026-03-01T11:00:00+07:00",
                        "tide_status": "predicted_interpolated",
                    }
                )
            result = secondary_tides.complete_scene_catalog(
                source,
                output=output,
                secondary_events=[base_event, after],
                validation=validation,
            )
            self.assertEqual(result["secondary_completed"], 1)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["tide_status"], "modelled_secondary_extrema_cosine")
            self.assertEqual(rows[0]["tide_level"], "0.0000")
            self.assertEqual(rows[1]["tide_status"], "predicted_interpolated")
            self.assertEqual(rows[1]["tide_source_tier"], "official_hourly_prediction")


if __name__ == "__main__":
    unittest.main()
