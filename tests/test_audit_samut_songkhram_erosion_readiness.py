from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "audit_samut_songkhram_erosion_readiness.py"
)
SPEC = importlib.util.spec_from_file_location("erosion_readiness", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ErosionReadinessTest(unittest.TestCase):
    def config(self) -> dict:
        return {
            "project_id": "TEST",
            "scope": {"plot_ids": ["P1", "P2"]},
            "intervention": {"nominal_year": 2024, "exact_date_status": "UNVERIFIED"},
            "analysis_period": {"post_years": [2025, 2026]},
            "controls": {"status": "DESIGN_REQUIRED", "target_count_per_treatment_segment": 3},
            "drone": {"minimum_repeat_surveys_per_plot_for_observed_stabilization": 2},
            "evidence_gates": {
                "minimum_tide_matched_scene_fraction": 0.8,
                "minimum_post_years_for_comparative_effect": 3,
            },
            "claim_language": {
                "insufficient_data": "insufficient",
                "satellite_screening": "screening",
                "tide_aware_screening": "tide aware",
                "observed_stabilization": "observed",
                "comparative_effect": "comparative",
                "prohibited": ["prohibited"],
            },
        }

    def summary(self) -> dict:
        return {
            "post_boundary_evidence": {
                "feature": "image-derived water-land boundary",
                "period": "2025-2026",
                "transect_count": 3,
                "per_plot": [
                    {"plot_id": "P1", "transect_count": 2},
                    {"plot_id": "P2", "transect_count": 1},
                ],
                "tide_status": "unverified",
                "confidence": "LOW",
            }
        }

    def test_current_style_data_remains_satellite_screening(self) -> None:
        scenes = [
            {
                "acquisition_datetime_utc": "2025-01-01T00:00:00Z",
                "tide_status": "unverified",
            }
        ]
        result = MODULE.build_readiness(
            self.config(), scenes, self.summary(), [], [], source_paths={}
        )
        self.assertEqual(result["evidence_level"], "SATELLITE_SCREENING")
        self.assertFalse(result["erosion_effect_demonstrated"])
        self.assertTrue(any("tide-matched" in value for value in result["blockers"]))

    def test_verified_complete_design_reaches_comparative_effect(self) -> None:
        config = self.config()
        config["intervention"]["exact_date_status"] = "VERIFIED"
        config["controls"]["status"] = "VERIFIED"
        config["analysis_period"]["post_years"] = [2025, 2026, 2027]
        scenes = [
            {
                "acquisition_datetime_utc": "2025-01-01T00:00:00Z",
                "tide_status": "predicted_interpolated",
            }
        ]
        drone = [
            {"plot_id": "P1", "survey_id": "P1-A"},
            {"plot_id": "P1", "survey_id": "P1-B"},
            {"plot_id": "P2", "survey_id": "P2-A"},
            {"plot_id": "P2", "survey_id": "P2-B"},
        ]
        field = [
            {"plot_id": "P1", "observation_id": "F1"},
            {"plot_id": "P2", "observation_id": "F2"},
        ]
        result = MODULE.build_readiness(
            config, scenes, self.summary(), drone, field, source_paths={}
        )
        self.assertEqual(result["evidence_level"], "COMPARATIVE_EFFECT")
        self.assertTrue(result["erosion_effect_demonstrated"])
        self.assertEqual(result["blockers"], [])


if __name__ == "__main__":
    unittest.main()
