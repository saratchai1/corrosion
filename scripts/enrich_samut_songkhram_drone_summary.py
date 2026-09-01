#!/usr/bin/env python3
"""Enrich the aggregated drone summary with explicit coverage and band scope."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data/processed/samut_songkhram_drone/raw"
DEFAULT_OUTPUT = ROOT / "data/processed/samut_songkhram_drone"
DEFAULT_WEB = ROOT / "web/public/data/project_drone_orthomosaic"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output-dir", type=Path, default=DEFAULT_WEB)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    raw_dir = resolve(args.raw_dir)
    output_dir = resolve(args.output_dir)
    web_dir = resolve(args.web_output_dir)
    summary_path = output_dir / "summary.json"
    summary = read_json(summary_path)

    raw_by_plot = {
        value["plot_id"]: value
        for value in [read_json(path) for path in sorted(raw_dir.glob("*.json"))]
    }
    if len(raw_by_plot) != 9:
        raise SystemExit(f"expected 9 raw plot metadata files, found {len(raw_by_plot)}")

    coverage_counts = {
        "COMPLETE_GE_95PCT": 0,
        "PARTIAL_USABLE_90_TO_95PCT": 0,
        "INSUFFICIENT_LT_90PCT": 0,
    }
    partial: list[str] = []
    insufficient: list[str] = []
    georef_review: list[str] = []

    for row in summary["plots"]:
        raw = raw_by_plot[row["plot_id"]]
        qa = raw["qa"]
        row["georeference_status"] = qa["georeference_status"]
        row["imagery_coverage_status"] = qa["imagery_coverage_status"]
        row["plot_valid_image_fraction"] = qa["imagery_coverage_fraction"]
        row["analysis_readiness"] = qa["analysis_readiness"]
        status = qa["imagery_coverage_status"]
        coverage_counts[status] += 1
        if status == "PARTIAL_USABLE_90_TO_95PCT":
            partial.append(row["plot_id"])
        elif status == "INSUFFICIENT_LT_90PCT":
            insufficient.append(row["plot_id"])
        if qa["georeference_status"] != "PASS":
            georef_review.append(row["plot_id"])

    summary["qa"].update(
        {
            "all_georeference_pass": not georef_review,
            "georeference_pass_count": 9 - len(georef_review),
            "georeference_review_plot_ids": georef_review,
            "coverage_complete_count": coverage_counts["COMPLETE_GE_95PCT"],
            "coverage_partial_usable_count": coverage_counts[
                "PARTIAL_USABLE_90_TO_95PCT"
            ],
            "coverage_partial_usable_plot_ids": partial,
            "coverage_insufficient_count": coverage_counts["INSUFFICIENT_LT_90PCT"],
            "coverage_insufficient_plot_ids": insufficient,
            "all_plot_valid_imagery_ge_95pct": (
                coverage_counts["COMPLETE_GE_95PCT"] == 9
            ),
            "all_plot_valid_imagery_ge_90pct": not insufficient,
            "usable_plot_count": 9 - len(insufficient),
            "ready_plot_count": sum(
                str(row["analysis_readiness"]).startswith("READY")
                for row in summary["plots"]
            ),
            "interpretation": (
                "All nine GeoTIFFs have valid projected georeferencing and spatially "
                "overlap their project polygons. Eight plots have >=95% valid imagery "
                "inside the polygon; 91-STC has partial but usable coverage (92.6846%)."
            ),
        }
    )
    summary["raster_band_scope"] = {
        "band_count": 4,
        "interpretation": ["red", "green", "blue", "alpha"],
        "nir_band_present": False,
        "drone_ndvi_supported": False,
        "scientific_guard": (
            "These orthomosaics are RGB + alpha, not multispectral. NDVI cannot be "
            "computed from the drone GeoTIFFs. High-resolution vegetation/bank-edge "
            "review must use RGB-visible features or separate multispectral data."
        ),
    }
    summary["baseline_readiness"] = {
        "status": (
            "READY_FOR_HIGH_RESOLUTION_BASELINE_WITH_91_STC_PARTIAL_COVERAGE"
            if not georef_review and not insufficient
            else "MANUAL_REVIEW_REQUIRED"
        ),
        "usable_plot_count": 9 - len(insufficient),
        "partial_coverage_plot_ids": partial,
        "what_this_adds": (
            "A centimetre-scale spatial baseline for validating plot geometry and "
            "visually checking Sentinel-2 mangrove-edge/waterline screening."
        ),
        "what_it_does_not_add": (
            "A drone-derived erosion rate: only one orthomosaic epoch is registered."
        ),
    }

    write_json(summary_path, summary)
    write_json(web_dir / "summary.json", summary)

    catalog_path = output_dir / "orthomosaic_catalog.csv"
    with catalog_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        raw = raw_by_plot[row["plot_id"]]
        row["georeference_status"] = raw["qa"]["georeference_status"]
        row["imagery_coverage_status"] = raw["qa"]["imagery_coverage_status"]
        row["plot_valid_image_fraction"] = raw["qa"]["imagery_coverage_fraction"]
        row["analysis_readiness"] = raw["qa"]["analysis_readiness"]
    fields = list(rows[0].keys())
    with catalog_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (web_dir / "orthomosaic_catalog.csv").write_text(
        catalog_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    print(json.dumps({
        "qa": summary["qa"],
        "raster_band_scope": summary["raster_band_scope"],
        "baseline_readiness": summary["baseline_readiness"],
    }, ensure_ascii=False, indent=2))
    if georef_review or insufficient:
        raise SystemExit("drone inventory still contains a georeference or <90% coverage failure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
