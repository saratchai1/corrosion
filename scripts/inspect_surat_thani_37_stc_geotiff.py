#!/usr/bin/env python3
"""Inspect the Surat Thani 37-STC raw drone GeoTIFF conservatively.

The script reads GeoTIFF metadata directly and computes valid imagery coverage
block-by-block so the 3.33 GB raster does not need to be loaded into RAM.
It deliberately does not infer acquisition date from the Google Drive folder
label.

Outputs:
- machine-readable GeoTIFF metadata / QA JSON
- WGS84 raster footprint GeoJSON

Example:
    python scripts/inspect_surat_thani_37_stc_geotiff.py \
      "/path/to/orthor 37 stc.tif"
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform_bounds


EXPECTED_PROJECT_CRS = "EPSG:32647"
PLOT_ID = "37-STC"


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
        return value if math.isfinite(value) else None
    return value


def _valid_fraction(src: rasterio.io.DatasetReader) -> float:
    """Calculate valid coverage using raster masks without loading the full raster."""
    valid = 0
    total = 0
    for _, window in src.block_windows(1):
        mask = src.dataset_mask(window=window)
        valid += int(np.count_nonzero(mask))
        total += int(mask.size)
    return valid / total if total else float("nan")


def _nir_status(src: rasterio.io.DatasetReader) -> tuple[bool | None, str]:
    color = [str(item).split(".")[-1].lower() for item in src.colorinterp]
    descriptions = [(item or "").strip().lower() for item in src.descriptions]

    explicit_nir = any(
        "nir" in item or "near infrared" in item or "near-infrared" in item
        for item in descriptions
    )
    if explicit_nir:
        return True, "EXPLICIT_BAND_DESCRIPTION"

    rgb_alpha = (
        src.count == 4
        and len(color) >= 4
        and color[:3] == ["red", "green", "blue"]
        and color[3] == "alpha"
    )
    if rgb_alpha:
        return False, "RGB_PLUS_ALPHA_COLORINTERP"

    rgb_only = (
        src.count == 3
        and len(color) >= 3
        and color[:3] == ["red", "green", "blue"]
    )
    if rgb_only:
        return False, "RGB_COLORINTERP"

    return None, "NOT_DETERMINABLE_FROM_RASTER_TAGS"


def inspect(path: Path, skip_coverage: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    with rasterio.open(path) as src:
        crs_text = src.crs.to_string() if src.crs else None
        epsg = src.crs.to_epsg() if src.crs else None
        projected = bool(src.crs and src.crs.is_projected)

        xres = abs(float(src.transform.a))
        yres = abs(float(src.transform.e))
        mean_gsd_m = (xres + yres) / 2 if projected else None
        mean_gsd_cm = mean_gsd_m * 100 if mean_gsd_m is not None else None

        valid_fraction = None if skip_coverage else _valid_fraction(src)
        if valid_fraction is not None and not math.isfinite(valid_fraction):
            valid_fraction = None

        nir_present, nir_basis = _nir_status(src)

        bounds = {
            "left": float(src.bounds.left),
            "bottom": float(src.bounds.bottom),
            "right": float(src.bounds.right),
            "top": float(src.bounds.top),
        }

        bounds_wgs84 = None
        footprint = None
        if src.crs:
            left, bottom, right, top = transform_bounds(
                src.crs, "EPSG:4326", *src.bounds, densify_pts=21
            )
            bounds_wgs84 = {
                "left": float(left),
                "bottom": float(bottom),
                "right": float(right),
                "top": float(top),
            }
            footprint = {
                "type": "FeatureCollection",
                "name": "surat_thani_37_stc_drone_footprint",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "plot_id": PLOT_ID,
                            "source": path.name,
                            "source_crs": crs_text,
                            "qa_role": "RAW_GEOTIFF_FOOTPRINT",
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [left, top],
                                [right, top],
                                [right, bottom],
                                [left, bottom],
                                [left, top],
                            ]],
                        },
                    }
                ],
            }

        expected_match = epsg == 32647 if epsg is not None else None
        georef_status = (
            "PASS_EXPECTED_PROJECT_CRS"
            if expected_match
            else (
                "FAIL_MISSING_CRS"
                if src.crs is None
                else "REVIEW_CRS_DIFFERS_FROM_PROJECT_GEOMETRY"
            )
        )

        if skip_coverage:
            coverage_status = "NOT_RUN"
        elif valid_fraction is None:
            coverage_status = "UNAVAILABLE"
        elif valid_fraction >= 0.95:
            coverage_status = "PASS_GE_95PCT"
        elif valid_fraction >= 0.90:
            coverage_status = "PARTIAL_USABLE_90_TO_95PCT"
        else:
            coverage_status = "INSUFFICIENT_LT_90PCT"

        result = {
            "plot_id": PLOT_ID,
            "source_file": str(path),
            "source_file_size_bytes": path.stat().st_size,
            "flight_date_status": "UNVERIFIED_NOT_INFERRED_FROM_FOLDER_LABEL",
            "raster": {
                "driver": src.driver,
                "width_px": src.width,
                "height_px": src.height,
                "band_count": src.count,
                "dtypes": list(src.dtypes),
                "nodata": [_json_scalar(item) for item in src.nodatavals],
                "colorinterp": [str(item).split(".")[-1] for item in src.colorinterp],
                "band_descriptions": list(src.descriptions),
            },
            "georeference": {
                "crs": crs_text,
                "epsg": epsg,
                "project_geometry_crs_reference": EXPECTED_PROJECT_CRS,
                "project_geometry_crs_is_not_assumed_for_raw_tiff": True,
                "expected_crs_match": expected_match,
                "transform": [
                    float(src.transform.a),
                    float(src.transform.b),
                    float(src.transform.c),
                    float(src.transform.d),
                    float(src.transform.e),
                    float(src.transform.f),
                ],
                "bounds_source_crs": bounds,
                "bounds_wgs84": bounds_wgs84,
                "pixel_size_x_source_units": xres,
                "pixel_size_y_source_units": yres,
                "mean_gsd_m": mean_gsd_m,
                "mean_gsd_cm": mean_gsd_cm,
                "qa_status": georef_status,
            },
            "coverage": {
                "valid_imagery_fraction": valid_fraction,
                "calculation": (
                    "rasterio.dataset_mask block-by-block"
                    if not skip_coverage
                    else "SKIPPED"
                ),
                "qa_status": coverage_status,
                "thresholds": {
                    "PASS_GE_95PCT": 0.95,
                    "PARTIAL_USABLE_GE_90PCT": 0.90,
                },
            },
            "spectral": {
                "nir_band_present": nir_present,
                "nir_detection_basis": nir_basis,
                "drone_ndvi_supported": nir_present is True,
                "guard": "Do not compute drone NDVI unless a NIR band is explicitly confirmed.",
            },
            "claim_guard": [
                "ONE_EPOCH_ONLY_NO_DRONE_DERIVED_CHANGE_RATE",
                "DO_NOT_INFER_FLIGHT_DATE_FROM_FOLDER_LABEL",
                "DO_NOT_PROMOTE_CROSS_SENSOR_ALIGNMENT_UNTIL_GEOREFERENCE_QA_PASSES",
            ],
        }
        return result, footprint


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("geotiff", type=Path, help="Path to orthor 37 stc.tif")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/analysis/surat_thani/drone_37_stc_geotiff_qa.json"),
    )
    parser.add_argument(
        "--footprint-geojson",
        type=Path,
        default=Path("data/analysis/surat_thani/drone_37_stc_footprint.geojson"),
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Inspect metadata only; definition-of-done still requires a later full coverage scan.",
    )
    args = parser.parse_args()

    if not args.geotiff.is_file():
        parser.error(f"GeoTIFF not found: {args.geotiff}")

    result, footprint = inspect(args.geotiff, args.skip_coverage)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if footprint is not None:
        args.footprint_geojson.parent.mkdir(parents=True, exist_ok=True)
        args.footprint_geojson.write_text(
            json.dumps(footprint, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps({
        "qa_json": str(args.output_json),
        "footprint_geojson": str(args.footprint_geojson) if footprint else None,
        "georeference_status": result["georeference"]["qa_status"],
        "coverage_status": result["coverage"]["qa_status"],
        "crs": result["georeference"]["crs"],
        "mean_gsd_cm": result["georeference"]["mean_gsd_cm"],
        "band_count": result["raster"]["band_count"],
        "valid_imagery_fraction": result["coverage"]["valid_imagery_fraction"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
