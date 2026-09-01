#!/usr/bin/env python3
"""Inspect one Samut Songkhram drone orthomosaic.

The script is intentionally read-only with respect to the source raster. It
extracts georeferencing metadata, verifies that the expected project polygon is
covered by valid imagery, creates a lightweight raw RGB preview (no labels or
vector overlays baked into the raster), and writes machine-readable metadata.

The folder label 25-12-2567 is preserved as provisional date evidence only. It
must not be promoted to a verified flight/acquisition date unless supported by
flight logs, EXIF, Pix4D/Metashape project metadata, or another project record.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shapely_transform

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLOTS = ROOT / "data/aoi/samut_songkhram_project_plots.geojson"
DEFAULT_OUTPUT = ROOT / "data/processed/samut_songkhram_drone/raw"
DEFAULT_WEB_OUTPUT = ROOT / "web/public/data/project_drone_orthomosaic"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--plot-id", required=True)
    parser.add_argument("--drive-file-id", required=True)
    parser.add_argument("--drive-title", required=True)
    parser.add_argument("--drive-size-bytes", type=int, required=True)
    parser.add_argument("--source-folder", required=True)
    parser.add_argument("--folder-date-iso", required=True)
    parser.add_argument("--folder-date-status", required=True)
    parser.add_argument("--plots", type=Path, default=DEFAULT_PLOTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output-dir", type=Path, default=DEFAULT_WEB_OUTPUT)
    parser.add_argument("--preview-max-dimension", type=int, default=1800)
    return parser.parse_args()


def read_plot(path: Path, plot_id: str) -> tuple[dict[str, Any], Any]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    for feature in collection.get("features", []):
        if feature.get("properties", {}).get("plot_id") == plot_id:
            return feature, shape(feature["geometry"]).buffer(0)
    raise KeyError(f"plot_id not found in {path}: {plot_id}")


def transform_geom(geom: Any, source_crs: str | CRS, target_crs: str | CRS) -> Any:
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator / denominator)


def colorinterp_names(dataset: rasterio.io.DatasetReader) -> list[str]:
    result: list[str] = []
    for item in dataset.colorinterp:
        name = getattr(item, "name", None)
        result.append(str(name or item))
    return result


def percentile_stretch(array: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    output = np.zeros_like(array, dtype=np.uint8)
    for index in range(array.shape[0]):
        band = array[index].astype(np.float32)
        valid = band[valid_mask]
        if valid.size == 0:
            continue
        if np.issubdtype(array.dtype, np.integer) and array.dtype.itemsize == 1:
            low, high = 0.0, 255.0
        else:
            low, high = np.nanpercentile(valid, [1, 99])
            if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high <= low:
                low = float(np.nanmin(valid))
                high = float(np.nanmax(valid))
        if high <= low:
            scaled = np.zeros_like(band)
        else:
            scaled = (band - low) / (high - low) * 255.0
        output[index] = np.clip(scaled, 0, 255).astype(np.uint8)
    return output


def build_preview(
    dataset: rasterio.io.DatasetReader,
    output_path: Path,
    *,
    max_dimension: int,
) -> dict[str, Any]:
    scale = min(1.0, max_dimension / max(dataset.width, dataset.height))
    out_width = max(1, int(round(dataset.width * scale)))
    out_height = max(1, int(round(dataset.height * scale)))

    band_indexes = [index for index in (1, 2, 3) if index <= dataset.count]
    if len(band_indexes) < 3:
        raise ValueError(f"RGB preview requires at least 3 bands, found {dataset.count}")

    data = dataset.read(
        band_indexes,
        out_shape=(len(band_indexes), out_height, out_width),
        resampling=rasterio.enums.Resampling.bilinear,
    )
    mask = dataset.dataset_mask(
        out_shape=(out_height, out_width),
        resampling=rasterio.enums.Resampling.nearest,
    )
    valid = mask > 0
    stretched = percentile_stretch(data, valid)
    rgba = np.zeros((out_height, out_width, 4), dtype=np.uint8)
    rgba[..., :3] = np.moveaxis(stretched, 0, -1)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path, "WEBP", quality=82, method=6)

    return {
        "preview_width": out_width,
        "preview_height": out_height,
        "preview_valid_fraction": round(float(valid.mean()), 6),
        "preview_path": str(output_path.relative_to(ROOT)),
    }


def plot_valid_coverage(
    dataset: rasterio.io.DatasetReader,
    plot_projected: Any,
    *,
    max_dimension: int = 1200,
) -> dict[str, Any]:
    scale = min(1.0, max_dimension / max(dataset.width, dataset.height))
    out_width = max(1, int(round(dataset.width * scale)))
    out_height = max(1, int(round(dataset.height * scale)))
    mask = dataset.dataset_mask(
        out_shape=(out_height, out_width),
        resampling=rasterio.enums.Resampling.nearest,
    )
    reduced_transform = dataset.transform * Affine.scale(
        dataset.width / out_width,
        dataset.height / out_height,
    )
    plot_mask = rasterize(
        [(mapping(plot_projected), 1)],
        out_shape=(out_height, out_width),
        transform=reduced_transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)
    pixels = int(plot_mask.sum())
    if pixels == 0:
        return {
            "plot_sample_pixel_count": 0,
            "plot_valid_image_fraction": 0.0,
            "plot_has_valid_imagery": False,
        }
    valid_fraction = float(((mask > 0) & plot_mask).sum() / pixels)
    return {
        "plot_sample_pixel_count": pixels,
        "plot_valid_image_fraction": round(valid_fraction, 6),
        "plot_has_valid_imagery": bool(valid_fraction >= 0.95),
    }


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    plots_path = args.plots if args.plots.is_absolute() else ROOT / args.plots
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    web_output_dir = args.web_output_dir if args.web_output_dir.is_absolute() else ROOT / args.web_output_dir

    feature, plot_wgs84 = read_plot(plots_path, args.plot_id)

    actual_size = input_path.stat().st_size
    size_matches = actual_size == args.drive_size_bytes

    with rasterio.open(input_path) as dataset:
        crs = dataset.crs
        if crs is None:
            raise ValueError(f"{args.plot_id}: raster has no CRS")
        crs_obj = CRS.from_user_input(crs)
        plot_projected = transform_geom(plot_wgs84, "EPSG:4326", crs_obj)
        raster_bounds_geom = box(*dataset.bounds)
        intersection_area = float(plot_projected.intersection(raster_bounds_geom).area)
        plot_area = float(plot_projected.area)
        bbox_coverage = safe_ratio(intersection_area, plot_area)

        footprint_wgs84 = transform_geom(raster_bounds_geom, crs_obj, "EPSG:4326")
        gsd_x = abs(float(dataset.res[0]))
        gsd_y = abs(float(dataset.res[1]))
        gsd_mean = (gsd_x + gsd_y) / 2.0
        projected_metre = bool(crs_obj.is_projected and any(axis.unit_name.lower().startswith("met") for axis in crs_obj.axis_info))
        gsd_cm = gsd_mean * 100.0 if projected_metre else None
        transform_tuple = tuple(float(value) for value in dataset.transform)
        has_rotation = abs(transform_tuple[1]) > 1e-12 or abs(transform_tuple[3]) > 1e-12
        identity_like = (
            abs(transform_tuple[0] - 1.0) < 1e-12
            and abs(transform_tuple[4] - 1.0) < 1e-12
            and abs(transform_tuple[2]) < 1e-12
            and abs(transform_tuple[5]) < 1e-12
        )

        preview_path = web_output_dir / "previews" / f"{args.plot_id}.webp"
        preview = build_preview(dataset, preview_path, max_dimension=args.preview_max_dimension)
        valid_coverage = plot_valid_coverage(dataset, plot_projected)

        overlap_ok = bbox_coverage is not None and bbox_coverage >= 0.98
        georef_ok = bool(
            crs is not None
            and not identity_like
            and projected_metre
            and gsd_mean > 0
            and overlap_ok
            and valid_coverage["plot_has_valid_imagery"]
        )

        metadata = {
            "plot_id": args.plot_id,
            "source": {
                "provider": "Google Drive shared folder",
                "drive_file_id": args.drive_file_id,
                "drive_title": args.drive_title,
                "expected_size_bytes": args.drive_size_bytes,
                "actual_size_bytes": actual_size,
                "size_matches_drive_manifest": size_matches,
                "source_folder": args.source_folder,
                "folder_date_iso": args.folder_date_iso,
                "folder_date_status": args.folder_date_status,
                "flight_date_verified": False,
                "flight_date_note": (
                    "The folder label is preserved as provisional date context only; "
                    "it is not treated as a verified flight date."
                ),
            },
            "raster": {
                "driver": dataset.driver,
                "width_px": dataset.width,
                "height_px": dataset.height,
                "band_count": dataset.count,
                "dtypes": list(dataset.dtypes),
                "color_interpretation": colorinterp_names(dataset),
                "crs": crs.to_string(),
                "crs_wkt": crs.to_wkt(),
                "projected_crs": bool(crs_obj.is_projected),
                "projected_units_metre": projected_metre,
                "pixel_size_x": gsd_x,
                "pixel_size_y": gsd_y,
                "mean_gsd_cm": None if gsd_cm is None else round(gsd_cm, 4),
                "transform": list(transform_tuple),
                "has_rotation": has_rotation,
                "bounds_native": [
                    float(dataset.bounds.left),
                    float(dataset.bounds.bottom),
                    float(dataset.bounds.right),
                    float(dataset.bounds.top),
                ],
                "bounds_wgs84": list(map(float, footprint_wgs84.bounds)),
                "nodata": dataset.nodata,
                "compression": dataset.tags(ns="IMAGE_STRUCTURE").get("COMPRESSION"),
                "interleave": dataset.tags(ns="IMAGE_STRUCTURE").get("INTERLEAVE"),
                "block_shapes": [list(map(int, value)) for value in dataset.block_shapes],
                "overviews": {str(index): list(map(int, dataset.overviews(index))) for index in range(1, dataset.count + 1)},
                "dataset_tags": dataset.tags(),
            },
            "plot_alignment": {
                "project_plot_area_native_crs": round(plot_area, 3),
                "plot_bbox_intersection_area_native_crs": round(intersection_area, 3),
                "plot_bbox_coverage_fraction": None if bbox_coverage is None else round(bbox_coverage, 6),
                **valid_coverage,
                "expected_plot_overlap_pass": overlap_ok,
            },
            "qa": {
                "georeference_status": "PASS" if georef_ok else "REVIEW",
                "crs_present": crs is not None,
                "transform_non_identity": not identity_like,
                "pixel_size_positive": bool(gsd_mean > 0),
                "projected_metric_crs": projected_metre,
                "plot_coverage_ge_98pct": overlap_ok,
                "plot_valid_imagery_ge_95pct": valid_coverage["plot_has_valid_imagery"],
                "drive_size_match": size_matches,
                "analysis_readiness": (
                    "READY_FOR_ORTHOMOSAIC_BASELINE_AND_SATELLITE_ALIGNMENT"
                    if georef_ok
                    else "MANUAL_REVIEW_REQUIRED"
                ),
            },
            "preview": preview,
            "project_plot_properties": feature.get("properties", {}),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.plot_id}.json"
    output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    footprint = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "plot_id": args.plot_id,
                    "drive_file_id": args.drive_file_id,
                    "drive_title": args.drive_title,
                    "georeference_status": metadata["qa"]["georeference_status"],
                    "mean_gsd_cm": metadata["raster"]["mean_gsd_cm"],
                    "preview": preview["preview_path"].replace("web/public/", ""),
                },
                "geometry": mapping(footprint_wgs84),
            }
        ],
    }
    (output_dir / f"{args.plot_id}.footprint.geojson").write_text(
        json.dumps(footprint, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
