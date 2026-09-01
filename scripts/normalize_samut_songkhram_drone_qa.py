#!/usr/bin/env python3
"""Separate georeference QA from orthomosaic imagery-coverage QA.

The first inspection run intentionally used a strict combined gate.  That
revealed one useful edge case: 91-STC is correctly georeferenced and its raster
bounding box covers 99.90% of the project polygon, but transparent/nodata gaps
leave 92.68% valid imagery inside the polygon.  That is a coverage limitation,
not a georeferencing failure.

This normalization keeps those two concepts separate:
- georeference PASS requires CRS/transform/metric units/plot-bbox alignment;
- imagery coverage COMPLETE >=95%, PARTIAL_USABLE >=90%, INSUFFICIENT <90%.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data/processed/samut_songkhram_drone/raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def coverage_status(fraction: float) -> str:
    if fraction >= 0.95:
        return "COMPLETE_GE_95PCT"
    if fraction >= 0.90:
        return "PARTIAL_USABLE_90_TO_95PCT"
    return "INSUFFICIENT_LT_90PCT"


def main() -> int:
    args = parse_args()
    raw_dir = resolve(args.raw_dir)
    paths = sorted(raw_dir.glob("*.json"))
    if len(paths) != 9:
        raise SystemExit(f"expected 9 raw metadata JSON files, found {len(paths)}")

    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        qa = value["qa"]
        alignment = value["plot_alignment"]
        valid_fraction = float(alignment["plot_valid_image_fraction"])

        georef_ok = all(
            bool(qa[key])
            for key in (
                "crs_present",
                "transform_non_identity",
                "pixel_size_positive",
                "projected_metric_crs",
                "plot_coverage_ge_98pct",
                "drive_size_match",
            )
        )
        status = coverage_status(valid_fraction)
        usable = status != "INSUFFICIENT_LT_90PCT"

        qa["georeference_status"] = "PASS" if georef_ok else "REVIEW"
        qa["imagery_coverage_status"] = status
        qa["imagery_coverage_fraction"] = round(valid_fraction, 6)
        qa["imagery_coverage_usable_ge_90pct"] = usable
        qa["analysis_readiness"] = (
            "READY_WITH_PARTIAL_COVERAGE_CAVEAT"
            if georef_ok and status == "PARTIAL_USABLE_90_TO_95PCT"
            else "READY_FOR_ORTHOMOSAIC_BASELINE_AND_SATELLITE_ALIGNMENT"
            if georef_ok and usable
            else "MANUAL_REVIEW_REQUIRED"
        )
        qa["qa_note"] = (
            "Georeferencing and imagery coverage are evaluated separately. "
            "Transparent/nodata gaps do not invalidate CRS or spatial alignment."
        )
        alignment["plot_has_valid_imagery"] = usable
        alignment["plot_valid_imagery_ge_95pct"] = valid_fraction >= 0.95
        alignment["plot_valid_imagery_ge_90pct"] = valid_fraction >= 0.90

        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        footprint_path = path.with_name(path.stem + ".footprint.geojson")
        if footprint_path.exists():
            footprint = json.loads(footprint_path.read_text(encoding="utf-8"))
            for feature in footprint.get("features", []):
                feature.setdefault("properties", {})["georeference_status"] = qa[
                    "georeference_status"
                ]
                feature["properties"]["imagery_coverage_status"] = status
                feature["properties"]["plot_valid_image_fraction"] = round(
                    valid_fraction, 6
                )
            footprint_path.write_text(
                json.dumps(footprint, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        print(
            f"{value['plot_id']}: georef={qa['georeference_status']} "
            f"coverage={valid_fraction:.4%} ({status})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
