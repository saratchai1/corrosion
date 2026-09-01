from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import build_tide_aware_project_edges as module


class TideAwareProjectEdgeTests(unittest.TestCase):
    def catalog_rows(self) -> list[dict[str, str]]:
        path = (
            ROOT
            / "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
        )
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_selects_low_spread_scenes_with_acceptable_secondary_brackets(self) -> None:
        result = module.select_common_tide_scenes(self.catalog_rows())
        selected = {
            module.year_of(row): row["scene_id"]
            for row in result["selected_rows"]
        }
        self.assertEqual(
            selected,
            {
                2023: "S2A_MSIL2A_20230116T034101_R061_T47PNQ_20230116T121416",
                2024: "S2B_MSIL2A_20240215T033839_R061_T47PNQ_20240215T081344",
                2025: "S2C_MSIL2A_20250214T033901_R061_T47PNQ_20250214T090512",
                2026: "S2C_MSIL2A_20260130T034001_R061_T47PNQ_20260130T081910",
            },
        )
        self.assertEqual(
            result["status"], "ACCEPTABLE_FOR_TIDE_AWARE_SCREENING"
        )
        self.assertAlmostEqual(result["tide_spread_m"], 0.3450, places=4)
        self.assertLessEqual(
            result["maximum_secondary_bracket_minutes"], 720
        )

    def test_rejects_long_secondary_bracket_even_when_tide_range_is_smaller(self) -> None:
        result = module.select_common_tide_scenes(self.catalog_rows())
        selected_ids = {row["scene_id"] for row in result["selected_rows"]}
        long_bracket_scene = next(
            row
            for row in self.catalog_rows()
            if row["acquisition_datetime_bangkok"].startswith("2025-01-15")
        )
        self.assertNotIn(long_bracket_scene["scene_id"], selected_ids)
        audit = next(
            row
            for row in result["audit"]
            if row["scene_id"] == long_bracket_scene["scene_id"]
        )
        self.assertFalse(audit["secondary_bracket_acceptable"])

    def test_series_metrics_use_positive_as_seaward(self) -> None:
        result = module.series_metrics(
            {2023: -10.0, 2024: -5.0, 2025: 8.0, 2026: 25.0}
        )
        self.assertEqual(result["nsm_2023_2026_m"], 35.0)
        self.assertEqual(result["classification"], "APPARENT_SEAWARD")
        self.assertAlmostEqual(
            result["epr_2023_2026_m_per_year"], 11.67, places=2
        )
        self.assertEqual(result["sce_m"], 35.0)

    def test_series_metrics_classifies_source_resolution_band(self) -> None:
        result = module.series_metrics(
            {2023: 0.0, 2024: 5.0, 2025: -2.0, 2026: 19.9}
        )
        self.assertEqual(result["classification"], "WITHIN_20M")

    def test_control_score_penalizes_pretrend_mismatch(self) -> None:
        treatment = {"WATERLINE": 5.0, "MANGROVE_EDGE_PROXY": 2.0}
        good = {"WATERLINE": 6.0, "MANGROVE_EDGE_PROXY": 1.0}
        poor = {"WATERLINE": 30.0, "MANGROVE_EDGE_PROXY": -20.0}
        self.assertLess(
            module.control_score(treatment, good, 1000),
            module.control_score(treatment, poor, 1000),
        )


if __name__ == "__main__":
    unittest.main()
