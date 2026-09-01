#!/usr/bin/env python3
"""Publish conservative same-extent Drone ↔ Sentinel-2 web assets for Surat Thani 37-STC.

This script is designed to run on an ephemeral CI runner after the raw 3.33 GB
orthomosaic has passed GeoTIFF QA. It never commits the source TIFF. Instead it:

1. Reprojects/downsamples the confirmed RGB+alpha orthomosaic to EPSG:4326.
2. Uses the raw GeoTIFF envelope as the common visual extent.
3. Resamples the existing 2026 Sentinel-2 web image to that same extent/size.
4. Updates the web drone manifest with the measured QA values and comparison metadata.

The resulting comparison is a georeferenced visual cross-sensor check. It is not
used to infer a drone-derived erosion/accretion rate from a single epoch.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject


TARGET_CRS = "EPSG:4326"
TARGET_YEAR = 2026
DEFAULT_WIDTH = 1800


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _physical_aspect(bounds: dict[str, float]) -> float:
    mid_lat = (bounds["top"] + bounds["bottom"]) / 2
    lon_m = (bounds["right"] - bounds["left"]) * math.cos(math.radians(mid_lat))
    lat_m = bounds["top"] - bounds["bottom"]
    return max(0.1, lon_m / max(lat_m, 1e-12))


def _render_drone(
    raw_path: Path,
    qa: dict[str, Any],
    out_path: Path,
    width: int,
) -> tuple[int, int, dict[str, float]]:
    bounds = qa["georeference"]["bounds_wgs84"]
    aspect = _physical_aspect(bounds)
    height = max(480, int(round(width / aspect)))
    dst_transform = from_bounds(
        bounds["left"], bounds["bottom"], bounds["right"], bounds["top"], width, height
    )

    with rasterio.open(raw_path) as src:
        color = [getattr(item, "name", str(item)).lower() for item in src.colorinterp]
        if src.count != 4 or color[:4] != ["red", "green", "blue", "alpha"]:
            raise RuntimeError(f"Expected confirmed RGB+alpha GeoTIFF, got count={src.count}, colorinterp={color}")
        if src.crs is None:
            raise RuntimeError("Raw GeoTIFF has no CRS; refusing to publish aligned web imagery")

        rgba = np.zeros((4, height, width), dtype=np.uint8)
        for band_index in (1, 2, 3):
            reproject(
                source=rasterio.band(src, band_index),
                destination=rgba[band_index - 1],
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=TARGET_CRS,
                resampling=Resampling.bilinear,
                src_nodata=None,
                dst_nodata=0,
            )
        reproject(
            source=rasterio.band(src, 4),
            destination=rgba[3],
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=TARGET_CRS,
            resampling=Resampling.nearest,
            src_nodata=None,
            dst_nodata=0,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(rgba, 0, -1), mode="RGBA").save(
        out_path, format="WEBP", quality=88, method=6
    )
    return width, height, bounds


def _find_epoch(index: dict[str, Any], year: int) -> dict[str, Any]:
    for epoch in index.get("epochs", []):
        if int(epoch.get("targetYear", -1)) == year:
            return epoch
    raise RuntimeError(f"No imagery epoch found for targetYear={year}")


def _render_satellite_same_extent(
    source_path: Path,
    epoch: dict[str, Any],
    target_bounds: dict[str, float],
    out_path: Path,
    size: tuple[int, int],
) -> None:
    coords = epoch["imageCoordinates"]
    xs = [float(item[0]) for item in coords]
    ys = [float(item[1]) for item in coords]
    src_left, src_right = min(xs), max(xs)
    src_bottom, src_top = min(ys), max(ys)

    if not (
        target_bounds["left"] >= src_left
        and target_bounds["right"] <= src_right
        and target_bounds["bottom"] >= src_bottom
        and target_bounds["top"] <= src_top
    ):
        raise RuntimeError("Drone extent is not fully contained by the selected Sentinel-2 web image")

    with Image.open(source_path) as image:
        image = image.convert("RGB")
        src_w, src_h = image.size
        x0 = (target_bounds["left"] - src_left) / (src_right - src_left) * src_w
        x1 = (target_bounds["right"] - src_left) / (src_right - src_left) * src_w
        y0 = (src_top - target_bounds["top"]) / (src_top - src_bottom) * src_h
        y1 = (src_top - target_bounds["bottom"]) / (src_top - src_bottom) * src_h
        sampled = image.transform(
            size,
            Image.Transform.EXTENT,
            (x0, y0, x1, y1),
            resample=Image.Resampling.BILINEAR,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sampled.save(out_path, format="WEBP", quality=90, method=6)


def _update_manifest(
    manifest_path: Path,
    qa: dict[str, Any],
    epoch: dict[str, Any],
    bounds: dict[str, float],
    width: int,
    height: int,
    drone_asset_rel: str,
    satellite_asset_rel: str,
) -> None:
    manifest = _load_json(manifest_path)
    project_valid = qa["coverage"]["project_polygon_valid_fraction"]

    manifest["status"] = "GEOREFERENCE_QA_PASSED_SAME_EXTENT_COMPARE_AVAILABLE"
    manifest["evidence_level"] = "GEOREFERENCED_HIGH_RESOLUTION_BASELINE"
    manifest["project_geometry_reference"]["raw_tiff_crs_assumed_from_project_geometry"] = False
    manifest["project_geometry_reference"]["guard"] = (
        "Project geometry and raw GeoTIFF independently resolve to EPSG:32647; the raw TIFF CRS was read directly, not assumed."
    )
    manifest["web_preview"] = {
        "asset": drone_asset_rel,
        "width_px": width,
        "height_px": height,
        "derivation": "Generated directly from the raw GeoTIFF after CRS/transform QA; reprojected to EPSG:4326 and downsampled for web display.",
    }
    manifest["same_extent_compare"] = {
        "status": "AVAILABLE",
        "role": "GEOREFERENCED_VISUAL_CROSS_SENSOR_COMPARISON",
        "bounds_wgs84": bounds,
        "width_px": width,
        "height_px": height,
        "drone_asset": drone_asset_rel,
        "sentinel2_asset": satellite_asset_rel,
        "sentinel2_target_year": int(epoch["targetYear"]),
        "sentinel2_actual_year": int(epoch["actualYear"]),
        "sentinel2_dates": epoch.get("dates", []),
        "sentinel2_resolution_m": epoch.get("resolutionM"),
        "registration_note": (
            "Both web images are rendered to the same WGS84 envelope and pixel dimensions. The Sentinel-2 side is derived from the existing georeferenced 2026 web image; use for visual context, not sub-pixel quantitative registration."
        ),
    }

    manifest["qa"] = {
        "raw_download_status": "DOWNLOADED_EPHEMERALLY_BY_GITHUB_ACTIONS",
        "connected_drive_download_limit_bytes": manifest.get("qa", {}).get(
            "connected_drive_download_limit_bytes", 268435456
        ),
        "raw_geotiff_size_bytes": qa["source_file_size_bytes"],
        "georeference_status": qa["georeference"]["qa_status"],
        "imagery_coverage_status": qa["coverage"]["qa_status"],
        "cross_sensor_alignment_status": "PASS_GEOREFERENCE_QA_SAME_EXTENT_VISUAL_COMPARE",
        "crs": qa["georeference"]["crs"],
        "mean_gsd_cm": qa["georeference"]["mean_gsd_cm"],
        "band_count": qa["raster"]["band_count"],
        "valid_imagery_fraction": project_valid,
        "nir_band_present": qa["spectral"]["nir_band_present"],
        "drone_ndvi_supported": qa["spectral"]["drone_ndvi_supported"],
        "inspection_script": "scripts/inspect_surat_thani_37_stc_geotiff.py",
        "publish_script": "scripts/publish_surat_thani_37_stc_drone_compare.py",
        "raw_metadata_reason": (
            "The raw 3.33 GB GeoTIFF was downloaded to ephemeral GitHub Actions storage and inspected directly. CRS, transform, GSD, RGB+alpha band configuration and project-polygon imagery coverage are now verified. The raw TIFF itself is not committed or served."
        ),
    }

    manifest["scientific_guard"] = [
        "Do not derive an erosion/accretion rate from one drone epoch.",
        "Do not call folder label 20-05-2569 a verified flight date until acquisition metadata confirms it.",
        "The raw GeoTIFF CRS is confirmed directly as EPSG:32647; it was not inferred from the project boundary.",
        "The raw raster is RGB+alpha, not multispectral NIR, so drone NDVI is not supported.",
        "Use Drone ↔ Sentinel-2 same-extent imagery as visual cross-sensor context; do not interpret pixel-level differences as a quantitative change rate.",
        "Do not use the rejected legacy placeholder as Drone-to-Sentinel alignment evidence.",
    ]

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_geotiff", type=Path)
    parser.add_argument(
        "--qa-json", type=Path,
        default=Path("data/analysis/surat_thani/drone_37_stc_geotiff_qa.json"),
    )
    parser.add_argument(
        "--imagery-index", type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/imagery_index.json"),
    )
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/drone/drone_manifest.json"),
    )
    parser.add_argument(
        "--imagery-dir", type=Path,
        default=Path("web-surat-thani/public/data/surat_thani"),
    )
    parser.add_argument(
        "--out-drone", type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/drone/orthor_37_stc_same_extent.webp"),
    )
    parser.add_argument(
        "--out-satellite", type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/drone/sentinel2_2026_same_extent.webp"),
    )
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    args = parser.parse_args()

    qa = _load_json(args.qa_json)
    if qa["georeference"]["qa_status"] != "PASS_EXPECTED_PROJECT_CRS":
        raise RuntimeError("GeoTIFF georeference QA has not passed")
    if qa["coverage"]["qa_status"] != "PASS_GE_95PCT":
        raise RuntimeError("Project-polygon imagery coverage QA has not passed")
    if qa["spectral"]["nir_detection_basis"] != "RGB_PLUS_ALPHA_COLORINTERP":
        raise RuntimeError("Expected confirmed RGB+alpha band configuration")

    imagery_index = _load_json(args.imagery_index)
    epoch = _find_epoch(imagery_index, TARGET_YEAR)
    satellite_source = args.imagery_dir / epoch["image"]
    if not satellite_source.is_file():
        raise RuntimeError(f"Missing satellite source image: {satellite_source}")

    width, height, bounds = _render_drone(args.raw_geotiff, qa, args.out_drone, args.width)
    _render_satellite_same_extent(
        satellite_source, epoch, bounds, args.out_satellite, (width, height)
    )

    data_prefix = Path("web-surat-thani/public")
    drone_asset_rel = str(args.out_drone.relative_to(data_prefix)).replace("\\", "/")
    satellite_asset_rel = str(args.out_satellite.relative_to(data_prefix)).replace("\\", "/")
    _update_manifest(
        args.manifest,
        qa,
        epoch,
        bounds,
        width,
        height,
        drone_asset_rel,
        satellite_asset_rel,
    )

    print(json.dumps({
        "status": "PASS",
        "width_px": width,
        "height_px": height,
        "bounds_wgs84": bounds,
        "drone_asset": str(args.out_drone),
        "sentinel2_asset": str(args.out_satellite),
        "manifest": str(args.manifest),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
