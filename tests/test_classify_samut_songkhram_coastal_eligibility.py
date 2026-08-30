from __future__ import annotations

import unittest

from scripts import classify_samut_songkhram_coastal_eligibility as module


class CoastalEligibilityTests(unittest.TestCase):
    def test_treatment_transect_marks_plot_screenable(self) -> None:
        result = module.classify_plot(
            treatment_transect_count=4,
            distance_to_reference_waterline_m=120.0,
            maximum_frontage_distance_m=3500.0,
        )
        self.assertEqual(
            result["eligibility_status"], "COASTAL_FRONTAGE_SCREENABLE"
        )
        self.assertEqual(
            result["coastal_erosion_scope"], "INCLUDED_IN_COASTAL_SCREENING"
        )

    def test_distant_plot_is_excluded_instead_of_forcing_transects(self) -> None:
        result = module.classify_plot(
            treatment_transect_count=0,
            distance_to_reference_waterline_m=8100.0,
            maximum_frontage_distance_m=3500.0,
        )
        self.assertEqual(
            result["eligibility_status"],
            "NO_COASTAL_WATERLINE_WITHIN_ANALYSIS_RANGE",
        )
        self.assertEqual(
            result["coastal_erosion_scope"], "EXCLUDED_FROM_COASTAL_SCREENING"
        )

    def test_nearby_plot_without_intersection_requires_review(self) -> None:
        result = module.classify_plot(
            treatment_transect_count=0,
            distance_to_reference_waterline_m=600.0,
            maximum_frontage_distance_m=3500.0,
        )
        self.assertEqual(
            result["eligibility_status"],
            "NO_INTERSECTING_TRANSECT_REVIEW_REQUIRED",
        )
        self.assertEqual(
            result["coastal_erosion_scope"], "MANUAL_REVIEW_REQUIRED"
        )


if __name__ == "__main__":
    unittest.main()
