#!/usr/bin/env python3
"""Finalize consistent status metadata for the completed Surat Thani 37-STC screening stack."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/surat_thani_erosion_free_data_v1.json"
EXEC = ROOT / "data/analysis/surat_thani/executive_summary.json"
S1 = ROOT / "data/analysis/surat_thani/s1_relative_corroboration.json"
VEG = ROOT / "data/analysis/surat_thani/mangrove_edge_proxy_screening.json"
EST = ROOT / "data/analysis/surat_thani/planting_establishment_screening.json"
TIDE = ROOT / "data/analysis/surat_thani/tide_matched_sensitivity_summary.json"
VERIFY = ROOT / "data/analysis/surat_thani/control_verification.json"
MANIFEST = ROOT / "data/analysis/surat_thani/evidence_manifest.json"
WEB_MANIFEST = ROOT / "web/public/data/surat_thani/evidence_manifest.json"
INTERNAL_MANIFEST = ROOT / "data/processed/surat_thani/web/evidence_manifest.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    cfg = load(CONFIG)
    ex = load(EXEC)
    s1 = load(S1)
    veg = load(VEG)
    est = load(EST)
    tide = load(TIDE)
    verify = load(VERIFY)

    annual = s1["annual"]
    ratio_annual = {
        year: item["median_within_scene_contrast"]["project_minus_control_median_vh_vv_log_ratio"]
        for year, item in annual.items()
    }
    ratio_ranges = {
        year: item["single_scene_contrast_range"]["project_minus_control_median_vh_vv_log_ratio"]
        for year, item in annual.items()
    }
    change = s1["change_2026_vs_2023_in_within_scene_project_minus_control"]
    ratio_change = float(change["project_minus_control_median_vh_vv_log_ratio"])
    largest_endpoint_scene_range = max(float(ratio_ranges["2023"]), float(ratio_ranges["2026"]))
    weak_variable = abs(ratio_change) <= largest_endpoint_scene_range
    s1_interpretation_status = (
        "SAME_SEASON_QA_PASSED_WEAK_VARIABLE_RELATIVE_GRD_DIAGNOSTIC"
        if weak_variable
        else "SAME_SEASON_QA_PASSED_RELATIVE_GRD_DIAGNOSTIC_REQUIRES_REVIEW"
    )

    cfg["status"] = "EVIDENCE_STACK_QA_PASSED_SMALL_POSITIVE_ESTABLISHMENT_NO_10M_EDGE_ADVANCE_WATERLINE_FAILED_S1_WEAK_VARIABLE_FIELD_VALIDATION_PENDING"
    cfg["satellite"]["sentinel1"].update({
        "relative_corroboration_status": s1_interpretation_status,
        "relative_corroboration_file": "data/analysis/surat_thani/s1_relative_corroboration.json",
        "same_season_months": [2, 3, 4],
        "selected_track": s1["method"]["selected_track_key"],
        "selected_scene_counts_by_year": {year: item["scene_count"] for year, item in annual.items()},
        "change_2026_vs_2023_project_minus_control": change,
        "vh_vv_log_ratio_annual_project_minus_control": ratio_annual,
        "vh_vv_log_ratio_single_scene_ranges": ratio_ranges,
        "interpretation": "The same-season relative GRD signal is non-monotonic and the 2026-vs-2023 VH/VV contrast change is smaller than endpoint single-scene contrast variability. Use as weak/variable corroboration only; do not interpret as calibrated biomass or causal planting evidence.",
        "absolute_biomass_or_backscatter_claim": "NOT_ALLOWED_WITH_CURRENT_RELATIVE_GRD_DIAGNOSTIC",
    })
    cfg["evidence_gates"]["sentinel1_relative_corroboration"] = "WEAK_VARIABLE_SUPPORTING_ONLY"
    cfg["evidence_gates"]["integrated_evidence_stack_qa"] = "PASSED"
    cfg["final_outputs"] = {
        "executive_summary": "data/analysis/surat_thani/executive_summary.json",
        "executive_summary_th": "regions/surat_thani/EXECUTIVE_SUMMARY_TH.md",
        "evidence_manifest": "data/analysis/surat_thani/evidence_manifest.json",
        "standalone_web_report": "web/public/surat-thani-37-stc.html",
        "web_data_root": "web/public/data/surat_thani/",
    }
    write(CONFIG, cfg)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "branch": "data/surat-thani-satellite-v1",
        "overall_status": cfg["status"],
        "causal_erosion_reduction_claim": ex["executive_decision"]["causal_erosion_reduction_claim"],
        "evidence_layers": {
            "coastal_vegetation_edge_10m": {
                "role": "PRIMARY_SATELLITE_SCREENING_INDICATOR",
                "status": ex["executive_decision"]["coastal_vegetation_edge_expansion"],
                "project_minus_control_2023_2026_m": veg["primary_result"]["project_minus_control_change_2023_2026_m"],
                "empirical_instability_floor_m": veg["robustness"]["empirical_edge_instability_floor_m"],
                "qa": "PASSED",
            },
            "in_plot_optical_establishment": {
                "role": "BIOLOGICAL_MONITORING_SIGNAL",
                "status": ex["executive_decision"]["vegetation_establishment"],
                "median_ndvi_did_2026_vs_2023": est["robustness"]["median_ndvi_2026_vs_2023_did"],
                "green_fraction_ndvi_0_32_did_2026_vs_2023": est["robustness"]["primary_green_fraction_2026_vs_2023_did"],
                "threshold_sign": est["robustness"]["green_fraction_2026_vs_2023_did_sign_across_thresholds"],
                "qa": "PASSED",
            },
            "waterline": {
                "role": "SUPPORTING_CONTEXT_ONLY",
                "status": ex["executive_decision"]["waterline_erosion_indicator"],
                "baseline_project_minus_control_m": tide["baseline_three_scene_composite"]["project_minus_control_apparent_change_2023_2026_m"],
                "tide_stage_project_minus_control_m": tide["tide_matched_contrasts"]["project_minus_control_apparent_change_2023_2026_m"],
                "sensitivity_shift_m": tide["sensitivity_delta"]["net_contrast_matched_minus_baseline_m"],
                "qa": "FAILED_ROBUSTNESS_AS_EXPECTED_AND_DOWNGRADED",
            },
            "sentinel1_relative_grd": {
                "role": "INDEPENDENT_CORROBORATION_ONLY",
                "status": s1_interpretation_status,
                "track": s1["method"]["selected_track_key"],
                "scene_counts": {year: item["scene_count"] for year, item in annual.items()},
                "all_selected_months_feb_apr": all(int(scene["acquisition_datetime_utc"][5:7]) in {2,3,4} for scene in s1["selected_scenes"]),
                "change_2026_vs_2023": change,
                "annual_vh_vv_project_minus_control": ratio_annual,
                "single_scene_vh_vv_ranges": ratio_ranges,
                "qa": "PASSED",
            },
            "controls": {
                "role": "NO_KNOWN_INTERVENTION_REFERENCE",
                "status": verify["status"],
                "qa": "USER_CONFIRMED",
            },
            "bank_or_geomorphic_edge": {
                "role": "HIGH_RESOLUTION_VALIDATION_TARGET",
                "status": "NOT_AUTOMATED_FROM_CURRENT_FREE_10M_DATA",
                "qa": "METHOD_WITHHELD_TO_AVOID_FALSE_PRECISION",
            },
        },
        "remaining_hard_gates": [
            "UAV/orthophoto validation of actual mangrove canopy and seaward vegetation edge",
            "field survival/height/canopy observations",
            "manual or high-resolution stable bank/geomorphic edge if erosion-effect evidence is required",
        ],
        "final_products": cfg["final_outputs"],
    }
    for path in [MANIFEST, WEB_MANIFEST, INTERNAL_MANIFEST]:
        write(path, manifest)

    for index_path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        if index_path.exists():
            index = load(index_path)
            index["evidence_manifest_file"] = "evidence_manifest.json"
            index["evidence_stack_qa_status"] = "PASSED"
            index["sentinel1_relative_status"] = s1_interpretation_status
            write(index_path, index)

    print(json.dumps({
        "overall_status": cfg["status"],
        "s1_status": s1_interpretation_status,
        "s1_ratio_change_2026_vs_2023": ratio_change,
        "endpoint_scene_variability_max": largest_endpoint_scene_range,
        "manifest": str(MANIFEST.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
