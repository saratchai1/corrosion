#!/usr/bin/env python3
"""Inspect the Surat Thani 37-STC raw drone GeoTIFF conservatively.

The script reads GeoTIFF metadata directly and computes both raster-rectangle
validity and project-boundary imagery coverage block-by-block, so the 3.33 GB
raster is never loaded into RAM. The project polygon is used only as a QA mask;
its CRS is not assigned to the raw TIFF.

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
from rasterio.features import bounds as geometry_bounds
from rasterio.features import rasterize
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import bounds as window_bounds


EXPECTED_PROJECT_CRS = "EPSG:32647"
PROJECT_GEOJSON_CRS = "EPSG:4326"
PLOT_ID = "37-STC"
DEFAULT_PROJECT_GEOJSON = Path(
    "web-surat-thani/public/data/surat_thani/project_boundary.geojson"
)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
        return value if math.isfinite(value) else None
    return value


def _colorinterp_name(item: Any) -> str:
    name = getattr(item, "name", None)
    return str(name if name is not None else item).lower()


def _load_project_geometries(project_geojson: Path, dst_crs: Any) -> list[dict[str, Any]]:
    if not project_geojson.is_file() or dst_crs is None:
        return []
    payload = json.loads(project_geojson.read_text(encoding="utf-8"))
    features = payload.get("features", []) if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if geometry:
            out.append(
                transform_geom(
                    PROJECT_GEOJSON_CRS,
                    dst_crs,
                    geometry,
                    antimeridian_cutting=False,
                    precision=-1,
                )
            )
    return out


def _merged_bounds(geometries: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    if not geometries:
        return None
    values = [geometry_bounds(geometry) for geometry in geometries]
    return (
        min(value[0] for value in values),
        min(value[1] for value in values),
        max(value[2] for value in values),
        max(value[3] for value in values),
    )


def _bbox_intersects(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _coverage_metrics(
    src: rasterio.io.DatasetReader,
    project_geometries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute raster and project-polygon validity block-by-block."""
    raster_valid = 0
    raster_total = 0
    project_valid = 0
    project_total = 0
    project_bbox = _merged_bounds(project_geometries)

    for _, window in src.block_windows(1):
        data_mask = src.dataset_mask(window=window)
        raster_valid += int(np.count_nonzero(data_mask))
        raster_total += int(data_mask.size)

        if not project_geometries or project_bbox is None:
            continue
        wb = window_bounds(window, src.transform)
        if not _bbox_intersects(wb, project_bbox):
            continue

        plot_mask = rasterize(
            [(geometry, 1) for geometry in project_geometries],
            out_shape=(int(window.height), int(window.width)),
            transform=src.window_transform(window),
            fill=0,
            default_value=1,
            dtype="uint8",
            all_touched=False,
        ).astype(bool)
        plot_pixels = int(np.count_nonzero(plot_mask))
        if not plot_pixels:
            continue
        project_total += plot_pixels
        project_valid += int(np.count_nonzero(data_mask[plot_mask]))

    raster_fraction = raster_valid / raster_total if raster_total else float("nan")
    project_fraction = project_valid / project_total if project_total else float("nan")
    return {
        "raster_rectangle_valid_pixels": raster_valid,
        "raster_rectangle_total_pixels": raster_total,
        "raster_rectangle_valid_fraction": raster_fraction,
        "project_polygon_valid_pixels": project_valid,
        "project_polygon_total_pixels": project_total,
        "project_polygon_valid_fraction": project_fraction,
    }


def _nir_status(src: rasterio.io.DatasetReader) -> tuple[bool | None, str]:
    color = [_colorinterp_name(item) for item in src.colorinterp]
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


def _coverage_status(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "UNAVAILABLE"
    if value >= 0.95:
        return "PASS_GE_95PCT"
    if value >= 0.90:
        return "PARTIAL_USABLE_90_TO_95PCT"
    return "INSUFFICIENT_LT_90PCT"


def inspect(
    path: Path,
    skip_coverage: bool,
    project_geojson: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    with rasterio.open(path) as src:
        crs_text = src.crs.to_string() if src.crs else None
        epsg = src.crs.to_epsg() if src.crs else None
        projected = bool(src.crs and src.crs.is_projected)

        xres = abs(float(src.transform.a))
        yres = abs(float(src.transform.e))
        mean_gsd_m = (xres + yres) / 2 if projected else None
        mean_gsd_cm = mean_gsd_m * 100 if mean_gsd_m is not None else None

        project_geometries = _load_project_geometries(project_geojson, src.crs)
        coverage_metrics: dict[str, Any] | None = None
        if not skip_coverage:
            coverage_metrics = _coverage_metrics(src, project_geometries)
            for key, value in list(coverage_metrics.items()):
                if isinstance(value, float) and not math.isfinite(value):
                    coverage_metrics[key] = None

        project_fraction = (
            coverage_metrics.get("project_polygon_valid_fraction")
            if coverage_metrics is not None
            else None
        )
        raster_fraction = (
            coverage_metrics.get("raster_rectangle_valid_fraction")
            if coverage_metrics is not None
            else None
        )

        nir_present, nir_basis = _nir_status(src)
        colorinterp = [_colorinterp_name(item) for item in src.colorinterp]
        base_tags = {str(k): str(v) for k, v in src.tags().items()}
        image_structure_tags = {
            str(k): str(v) for k, v in src.tags(ns="IMAGE_STRUCTURE").items()
        }
        timestamp_tags = {
            key: value
            for key, value in base_tags.items()
            if any(token in key.upper() for token in ("DATE", "TIME", "ACQUIS"))
        }
        flight_date_status = (
            "RAW_TIMESTAMP_TAGS_PRESENT_NOT_ASSUMED_FLIGHT_DATE"
            if timestamp_tags
            else "UNVERIFIED_NOT_INFERRED_FROM_FOLDER_LABEL"
        )

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
                            "project_polygon_valid_fraction": project_fraction,
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

        project_coverage_status = "NOT_RUN" if skip_coverage else _coverage_status(project_fraction)

        result = {
            "plot_id": PLOT_ID,
            "source_file": str(path),
            "source_file_size_bytes": path.stat().st_size,
            "flight_date_status": flight_date_status,
            "raw_timestamp_tags": timestamp_tags,
            "raster": {
                "driver": src.driver,
                "width_px": src.width,
                "height_px": src.height,
                "band_count": src.count,
                "dtypes": list(src.dtypes),
                "nodata": [_json_scalar(item) for item in src.nodatavals],
                "colorinterp": colorinterp,
                "band_descriptions": list(src.descriptions),
                "image_structure_tags": image_structure_tags,
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
                "project_boundary_source": str(project_geojson),
                "project_boundary_source_crs": PROJECT_GEOJSON_CRS,
                "project_polygon_valid_fraction": project_fraction,
                "raster_rectangle_valid_fraction": raster_fraction,
                "metrics": coverage_metrics,
                "calculation": (
                    "rasterio dataset mask intersected with rasterized project polygon, block-by-block"
                    if not skip_coverage
                    else "SKIPPED"
                ),
                "qa_status": project_coverage_status,
                "interpretation_guard": "QA status is based on valid imagery inside the 37-STC project polygon; raster-rectangle validity is context only because the orthomosaic has large transparent/NoData margins.",
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
        "--project-geojson",
        type=Path,
        default=DEFAULT_PROJECT_GEOJSON,
        help="WGS84 GeoJSON used only to measure valid imagery coverage inside 37-STC.",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Inspect metadata only; definition-of-done still requires a later project coverage scan.",
    )
    args = parser.parse_args()

    if not args.geotiff.is_file():
        parser.error(f"GeoTIFF not found: {args.geotiff}")
    if not args.skip_coverage and not args.project_geojson.is_file():
        parser.error(f"Project GeoJSON not found: {args.project_geojson}")

    result, footprint = inspect(args.geotiff, args.skip_coverage, args.project_geojson)
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
        "colorinterp": result["raster"]["colorinterp"],
        "project_polygon_valid_fraction": result["coverage"]["project_polygon_valid_fraction"],
        "raster_rectangle_valid_fraction": result["coverage"]["raster_rectangle_valid_fraction"],
        "nir_band_present": result["spectral"]["nir_band_present"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
