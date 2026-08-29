#!/usr/bin/env python3
"""Extract a georeferenced water mask from GREEN + SWIR COGs using MNDWI.

The output is suitable for *screening* water-edge change. It does not by itself
prove coastal erosion because tide, turbidity, waves and classification error can
move the apparent water line.

Radiometric scale/offset are read from source-calibration tags persisted by the
Krabi downloader. Raster band metadata is the next fallback, followed by a
sensor default. Optional Sentinel-2 SCL or Landsat QA_PIXEL masks remove
cloud/shadow pixels.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import shapes
from rasterio.warp import Resampling, reproject
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

SENSOR_FALLBACK = {
    "sentinel2": {"scale": 0.0001, "offset": 0.0},
    "landsat": {"scale": 0.0000275, "offset": -0.2},
}


def reflectance(arr: np.ndarray, scale: float, offset: float) -> np.ndarray:
    return arr.astype("float32") * scale + offset


def masked_to_float(raw: np.ma.MaskedArray) -> np.ndarray:
    """Cast integer masked rasters before filling with NaN."""
    return np.asarray(raw.astype("float32").filled(np.nan), dtype="float32")


def dataset_calibration(src: rasterio.io.DatasetReader, sensor: str) -> tuple[float, float, str]:
    tags = src.tags()
    if "source_band_scale" in tags and "source_band_offset" in tags:
        try:
            return (
                float(tags["source_band_scale"]),
                float(tags["source_band_offset"]),
                tags.get("calibration_source", "source_calibration_tags"),
            )
        except ValueError:
            pass

    scale = float(src.scales[0]) if src.scales and src.scales[0] is not None else 1.0
    offset = float(src.offsets[0]) if src.offsets and src.offsets[0] is not None else 0.0
    if scale != 1.0 or offset != 0.0:
        return scale, offset, "raster_band_metadata"

    fallback = SENSOR_FALLBACK[sensor]
    return float(fallback["scale"]), float(fallback["offset"]), "sensor_fallback"


def regrid_band(
    src_path: Path, reference: rasterio.io.DatasetReader, sensor: str
) -> tuple[np.ndarray, np.ndarray, float, float, str]:
    with rasterio.open(src_path) as src:
        raw = src.read(1, masked=True)
        dst = np.full((reference.height, reference.width), np.nan, dtype="float32")
        valid = np.zeros((reference.height, reference.width), dtype="uint8")
        reproject(
            source=masked_to_float(raw),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=np.nan,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        reproject(
            source=(~np.ma.getmaskarray(raw)).astype("uint8"),
            destination=valid,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=0,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        scale, offset, source = dataset_calibration(src, sensor)
        return dst, valid.astype(bool), scale, offset, source


def regrid_categorical(src_path: Path, reference: rasterio.io.DatasetReader) -> tuple[np.ndarray, np.ndarray]:
    with rasterio.open(src_path) as src:
        raw = src.read(1, masked=True)
        fill = int(src.nodata) if src.nodata is not None else 0
        dst = np.full((reference.height, reference.width), fill, dtype=src.dtypes[0])
        valid = np.zeros((reference.height, reference.width), dtype="uint8")
        reproject(
            source=np.asarray(raw.filled(fill)),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=fill,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=fill,
            resampling=Resampling.nearest,
        )
        reproject(
            source=(~np.ma.getmaskarray(raw)).astype("uint8"),
            destination=valid,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=0,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        return dst, valid.astype(bool)


def quality_valid_mask(sensor: str, values: np.ndarray, available: np.ndarray) -> np.ndarray:
    if sensor == "sentinel2":
        # SCL: remove nodata/saturated, cloud shadow, medium/high cloud, cirrus, snow/ice.
        bad_classes = np.array([0, 1, 3, 8, 9, 10, 11], dtype=values.dtype)
        return available & ~np.isin(values, bad_classes)

    # Landsat Collection 2 QA_PIXEL bits:
    # 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow, 5 snow.
    qa = values.astype("uint32")
    bad_bits = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5))
    return available & ((qa & bad_bits) == 0)


def write_cog(path: Path, data: np.ndarray, reference: rasterio.io.DatasetReader, *, dtype: str, nodata, tags: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "COG",
        "height": reference.height,
        "width": reference.width,
        "count": 1,
        "dtype": dtype,
        "crs": reference.crs,
        "transform": reference.transform,
        "nodata": nodata,
        "compress": "DEFLATE",
        "blocksize": 512,
        "overview_resampling": "nearest" if dtype == "uint8" else "average",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)
        dst.update_tags(**tags)


def water_geojson(mask: np.ndarray, reference: rasterio.io.DatasetReader, min_area_m2: float, properties: dict[str, object]) -> dict:
    crs = CRS.from_user_input(reference.crs)
    if not crs.is_projected:
        raise ValueError("Water polygon area filtering requires a projected raster CRS (expected EPSG:32647)")

    polygons = []
    for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=reference.transform):
        if value != 1:
            continue
        poly = shape(geom)
        if poly.area >= min_area_m2:
            polygons.append(poly)
    merged = unary_union(polygons) if polygons else None
    to4326 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    features = []
    if merged and not merged.is_empty:
        parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        for i, poly in enumerate(parts, 1):
            features.append({
                "type": "Feature",
                "properties": {**properties, "part": i, "area_m2_projected": round(poly.area, 2)},
                "geometry": mapping(transform(to4326, poly)),
            })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract MNDWI water mask from georeferenced COG bands")
    parser.add_argument("--green", type=Path, required=True)
    parser.add_argument("--swir", type=Path, required=True)
    parser.add_argument("--quality-mask", type=Path, help="Sentinel-2 SCL or Landsat QA_PIXEL raster")
    parser.add_argument("--sensor", choices=SENSOR_FALLBACK, required=True)
    parser.add_argument("--date", required=True, help="Acquisition date YYYY-MM-DD")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--min-area-m2", type=float, default=100.0)
    parser.add_argument("--tide-status", choices=["verified", "unverified"], default="unverified")
    parser.add_argument("--tide-level-m", type=float)
    parser.add_argument("--tide-datum")
    parser.add_argument("--green-scale", type=float)
    parser.add_argument("--green-offset", type=float)
    parser.add_argument("--swir-scale", type=float)
    parser.add_argument("--swir-offset", type=float)
    args = parser.parse_args()

    with rasterio.open(args.green) as green_src:
        if not green_src.crs:
            raise ValueError("GREEN raster has no CRS")
        green_raw = green_src.read(1, masked=True)
        green_valid = ~np.ma.getmaskarray(green_raw)
        green_meta_scale, green_meta_offset, green_cal_source = dataset_calibration(green_src, args.sensor)
        swir_raw, swir_valid, swir_meta_scale, swir_meta_offset, swir_cal_source = regrid_band(
            args.swir, green_src, args.sensor
        )

        g_scale = green_meta_scale if args.green_scale is None else args.green_scale
        g_offset = green_meta_offset if args.green_offset is None else args.green_offset
        s_scale = swir_meta_scale if args.swir_scale is None else args.swir_scale
        s_offset = swir_meta_offset if args.swir_offset is None else args.swir_offset

        green = reflectance(masked_to_float(green_raw), g_scale, g_offset)
        swir = reflectance(swir_raw, s_scale, s_offset)
        denom = green + swir
        valid = green_valid & swir_valid & np.isfinite(green) & np.isfinite(swir) & (np.abs(denom) > 1e-8)

        if args.quality_mask:
            quality_values, quality_available = regrid_categorical(args.quality_mask, green_src)
            valid &= quality_valid_mask(args.sensor, quality_values, quality_available)

        mndwi = np.full(green.shape, -9999.0, dtype="float32")
        mndwi[valid] = (green[valid] - swir[valid]) / denom[valid]
        water = valid & (mndwi > args.threshold)

        # 0 = valid non-water, 1 = valid water, 255 = invalid/no-data.
        water_class = np.full(green.shape, 255, dtype="uint8")
        water_class[valid] = 0
        water_class[water] = 1

        tags = {
            "sensor": args.sensor,
            "acquisition_date": args.date,
            "mndwi_threshold": str(args.threshold),
            "class_0": "valid_non_water",
            "class_1": "valid_water",
            "class_255": "invalid_nodata",
            "green_scale": str(g_scale),
            "green_offset": str(g_offset),
            "swir_scale": str(s_scale),
            "swir_offset": str(s_offset),
            "green_calibration_source": "cli_override" if args.green_scale is not None or args.green_offset is not None else green_cal_source,
            "swir_calibration_source": "cli_override" if args.swir_scale is not None or args.swir_offset is not None else swir_cal_source,
            "quality_mask": "" if args.quality_mask is None else str(args.quality_mask),
            "tide_status": args.tide_status,
            "tide_level_m": "" if args.tide_level_m is None else str(args.tide_level_m),
            "tide_datum": args.tide_datum or "",
            "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        write_cog(args.out_dir / "mndwi.tif", mndwi, green_src, dtype="float32", nodata=-9999.0, tags=tags)
        write_cog(args.out_dir / "water_mask.tif", water_class, green_src, dtype="uint8", nodata=255, tags=tags)
        vector = water_geojson(
            water,
            green_src,
            args.min_area_m2,
            {
                "sensor": args.sensor,
                "acquisition_date": args.date,
                "threshold": args.threshold,
                "tide_status": args.tide_status,
                "tide_level_m": args.tide_level_m,
                "tide_datum": args.tide_datum,
                "analysis_status": "SCREENING" if args.tide_status == "verified" else "TIDE_UNVERIFIED_SCREENING",
            },
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "water_polygons.geojson").write_text(json.dumps(vector, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "sensor": args.sensor,
        "date": args.date,
        "threshold": args.threshold,
        "valid_pixel_count": int(valid.sum()),
        "water_pixel_count": int(water.sum()),
        "water_fraction_valid": round(float(water.sum() / valid.sum()), 6) if valid.any() else None,
        "green_scale": g_scale,
        "green_offset": g_offset,
        "swir_scale": s_scale,
        "swir_offset": s_offset,
        "green_calibration_source": green_cal_source if args.green_scale is None and args.green_offset is None else "cli_override",
        "swir_calibration_source": swir_cal_source if args.swir_scale is None and args.swir_offset is None else "cli_override",
        "quality_mask_used": args.quality_mask is not None,
        "tide_status": args.tide_status,
        "analysis_status": "SCREENING" if args.tide_status == "verified" else "TIDE_UNVERIFIED_SCREENING",
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
