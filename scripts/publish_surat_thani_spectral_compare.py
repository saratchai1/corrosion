#!/usr/bin/env python3
"""Publish real multispectral same-extent products for Surat Thani 37-STC.

This mirrors the Samut Songkhram visual stack with actual satellite bands:
RGB, False Color (NIR-Red-Green), NDVI, MNDWI and SWIR (SWIR1-NIR-Red).
It never derives spectral indices from RGB preview images.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "web-surat-thani/public/data/surat_thani"
INDEX_PATH = DATA_ROOT / "imagery_index.json"
CATALOG_PATH = DATA_ROOT / "drone/compare_catalog.json"
OUT_DIR = DATA_ROOT / "drone/multiyear"
PLANETARY_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
MODES = ("rgb", "false_vegetation", "ndvi", "mndwi", "swir")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finite_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    output = np.full_like(numerator, np.nan, dtype="float32")
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (np.abs(denominator) > 1e-6)
    output[valid] = numerator[valid] / denominator[valid]
    return output


def stretch_channel(channel: np.ndarray, valid: np.ndarray, gamma: float = 0.85) -> np.ndarray:
    output = np.zeros(channel.shape, dtype=np.uint8)
    sample = channel[valid & np.isfinite(channel)]
    if sample.size == 0:
        return output
    lo, hi = np.nanpercentile(sample, [2.0, 98.0])
    if not math.isfinite(float(lo)) or not math.isfinite(float(hi)) or hi <= lo:
        lo = float(np.nanmin(sample))
        hi = float(np.nanmax(sample))
    if hi <= lo:
        return output
    scaled = np.clip((channel - lo) / (hi - lo), 0.0, 1.0)
    scaled = np.power(scaled, gamma)
    output[valid] = np.clip(np.rint(scaled[valid] * 255.0), 0, 255).astype(np.uint8)
    return output


def rgba_composite(channels: list[np.ndarray], valid: np.ndarray, gamma: float = 0.85) -> np.ndarray:
    rgb = np.stack([stretch_channel(channel, valid, gamma=gamma) for channel in channels], axis=-1)
    alpha = np.where(valid, 245, 0).astype(np.uint8)
    return np.dstack([rgb, alpha])


def colourize(values: np.ndarray, valid: np.ndarray, stops: list[float], colours: list[tuple[int, int, int]]) -> np.ndarray:
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if not np.any(valid):
        return rgba
    clipped = np.clip(values, stops[0], stops[-1])
    xp = np.asarray(stops, dtype=np.float32)
    for channel in range(3):
        fp = np.asarray([colour[channel] for colour in colours], dtype=np.float32)
        rgba[..., channel] = np.clip(np.rint(np.interp(clipped, xp, fp)), 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 242, 0).astype(np.uint8)
    return rgba


def render_modes(bands: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    blue, green, red, nir, swir1 = (bands[key] for key in ("blue", "green", "red", "nir", "swir1"))
    valid = np.isfinite(blue) & np.isfinite(green) & np.isfinite(red) & np.isfinite(nir) & np.isfinite(swir1)
    ndvi = finite_ratio(nir - red, nir + red)
    mndwi = finite_ratio(green - swir1, green + swir1)
    return {
        "rgb": rgba_composite([red, green, blue], valid),
        "false_vegetation": rgba_composite([nir, red, green], valid, gamma=0.78),
        "ndvi": colourize(
            ndvi,
            valid & np.isfinite(ndvi),
            [-1.0, -0.2, 0.0, 0.2, 0.4, 0.65, 1.0],
            [(28, 62, 115), (70, 105, 145), (166, 140, 101), (218, 196, 112), (133, 181, 93), (47, 130, 73), (8, 69, 42)],
        ),
        "mndwi": colourize(
            mndwi,
            valid & np.isfinite(mndwi),
            [-1.0, -0.35, 0.0, 0.15, 0.35, 0.65, 1.0],
            [(108, 68, 39), (179, 135, 85), (202, 199, 177), (151, 211, 214), (71, 166, 202), (24, 95, 171), (8, 45, 104)],
        ),
        "swir": rgba_composite([swir1, nir, red], valid, gamma=0.78),
    }


def asset_scale_offset(asset: Any) -> tuple[float, float]:
    raster_bands = asset.extra_fields.get("raster:bands") or []
    if raster_bands:
        meta = raster_bands[0] or {}
        return float(meta.get("scale", 1.0) or 1.0), float(meta.get("offset", 0.0) or 0.0)
    return 1.0, 0.0


def read_asset(asset: Any, bbox: tuple[float, float, float, float], width: int, height: int, *, nearest: bool = False, apply_scale: bool = True) -> np.ndarray:
    destination = np.full((height, width), np.nan, dtype=np.float32)
    dst_transform = from_bounds(*bbox, width, height)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    ):
        with rasterio.open(asset.href) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=dst_transform,
                dst_crs="EPSG:4326",
                dst_nodata=np.nan,
                resampling=Resampling.nearest if nearest else Resampling.bilinear,
                num_threads=2,
            )
    if apply_scale:
        scale, offset = asset_scale_offset(asset)
        finite = np.isfinite(destination)
        destination[finite] = destination[finite] * scale + offset
    return destination


def asset_key(item: Any, candidates: list[str], common_names: list[str]) -> str:
    for key in candidates:
        if key in item.assets:
            return key
    wanted = set(common_names)
    for key, asset in item.assets.items():
        for band in asset.extra_fields.get("eo:bands") or []:
            if band.get("common_name") in wanted:
                return key
    raise KeyError(f"No asset for {candidates}; available={sorted(item.assets)}")


def platform_family(item: Any) -> str:
    platform = str(item.properties.get("platform") or item.collection_id or "").lower()
    return "sentinel" if "sentinel" in platform or str(item.collection_id).startswith("sentinel") else "landsat"


def mapping_for(item: Any) -> dict[str, str]:
    family = platform_family(item)
    if family == "sentinel":
        return {
            "blue": asset_key(item, ["B02"], ["blue"]),
            "green": asset_key(item, ["B03"], ["green"]),
            "red": asset_key(item, ["B04"], ["red"]),
            "nir": asset_key(item, ["B08"], ["nir"]),
            "swir1": asset_key(item, ["B11"], ["swir16"]),
            "quality": asset_key(item, ["SCL"], []),
        }
    return {
        "blue": asset_key(item, ["blue"], ["blue"]),
        "green": asset_key(item, ["green"], ["green"]),
        "red": asset_key(item, ["red"], ["red"]),
        "nir": asset_key(item, ["nir08", "nir"], ["nir", "nir08"]),
        "swir1": asset_key(item, ["swir16", "swir1"], ["swir16"]),
        "quality": asset_key(item, ["qa_pixel"], []),
    }


def quality_mask(item: Any, mapping: dict[str, str], bbox: tuple[float, float, float, float], width: int, height: int) -> np.ndarray:
    qa = read_asset(item.assets[mapping["quality"]], bbox, width, height, nearest=True, apply_scale=False)
    finite = np.isfinite(qa)
    if platform_family(item) == "sentinel":
        values = np.where(finite, np.rint(qa), -999).astype(np.int16)
        # SCL: 0 no data, 1 saturated, 3 shadow, 8/9 cloud, 10 cirrus, 11 snow/ice.
        return finite & ~np.isin(values, [0, 1, 3, 8, 9, 10, 11])
    values = np.where(finite, np.rint(qa), 0).astype(np.uint32)
    # Landsat QA_PIXEL bits: fill, dilated cloud, cirrus, cloud, shadow, snow.
    bad = ((values & (1 << 0)) != 0) | ((values & (1 << 1)) != 0) | ((values & (1 << 2)) != 0) | ((values & (1 << 3)) != 0) | ((values & (1 << 4)) != 0) | ((values & (1 << 5)) != 0)
    return finite & ~bad


def search_item(client: Any, date: str, bbox: tuple[float, float, float, float], family: str) -> Any:
    collection = "sentinel-2-l2a" if family == "sentinel" else "landsat-c2-l2"
    search = client.search(collections=[collection], bbox=list(bbox), datetime=f"{date}T00:00:00Z/{date}T23:59:59Z")
    items = list(search.items())
    if not items:
        raise RuntimeError(f"No {collection} item intersects 37-STC on {date}")
    items.sort(key=lambda item: (float(item.properties.get("eo:cloud_cover", 9999) or 9999), item.id))
    return planetary_computer.sign(items[0])


def family_for_choice(choice: dict[str, Any]) -> str:
    return "sentinel" if int(choice["actualYear"]) >= 2015 else "landsat"


def build_choice(client: Any, choice: dict[str, Any], bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[dict[str, str], list[str], list[str]]:
    scene_bands: dict[str, list[np.ndarray]] = {key: [] for key in ("blue", "green", "red", "nir", "swir1")}
    used_dates: list[str] = []
    used_items: list[str] = []
    family = family_for_choice(choice)
    for date in choice.get("dates", []):
        try:
            item = search_item(client, date, bbox, family)
            mapping = mapping_for(item)
            mask = quality_mask(item, mapping, bbox, width, height)
            arrays: dict[str, np.ndarray] = {}
            for key in scene_bands:
                array = read_asset(item.assets[mapping[key]], bbox, width, height)
                array[~mask] = np.nan
                arrays[key] = array
            if sum(np.isfinite(arrays["red"]).ravel()) < 100:
                print(f"WARN {choice['targetYear']} {date}: too few valid pixels; skipped")
                continue
            for key in scene_bands:
                scene_bands[key].append(arrays[key])
            used_dates.append(date)
            used_items.append(item.id)
            print(f"OK {choice['targetYear']} {date}: {item.id}")
        except Exception as exc:  # keep annual product if one selected scene fails
            print(f"WARN {choice['targetYear']} {date}: {exc}")
    if not used_dates:
        raise RuntimeError(f"No valid multispectral scene for target year {choice['targetYear']}")
    composite: dict[str, np.ndarray] = {}
    for key, arrays in scene_bands.items():
        with np.errstate(all="ignore"):
            composite[key] = np.nanmedian(np.stack(arrays, axis=0), axis=0).astype(np.float32)
    rendered = render_modes(composite)
    target_year = int(choice["targetYear"])
    visuals: dict[str, str] = {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for mode, rgba in rendered.items():
        filename = f"satellite_{target_year}_{mode}_same_extent.webp"
        output = OUT_DIR / filename
        Image.fromarray(rgba, mode="RGBA").save(output, format="WEBP", quality=88, method=6)
        visuals[mode] = f"data/surat_thani/drone/multiyear/{filename}"
    return visuals, used_dates, used_items


def main() -> int:
    index = load_json(INDEX_PATH)
    catalog = load_json(CATALOG_PATH)
    bounds = catalog["bounds_wgs84"]
    bbox = (float(bounds["left"]), float(bounds["bottom"]), float(bounds["right"]), float(bounds["top"]))
    width, height = int(catalog["width_px"]), int(catalog["height_px"])
    client = pystac_client.Client.open(PLANETARY_STAC)

    failures: list[str] = []
    for choice in catalog["leftChoices"]:
        try:
            visuals, used_dates, used_items = build_choice(client, choice, bbox, width, height)
            choice["visuals"] = visuals
            choice["spectralStatus"] = "ACTUAL_MULTISPECTRAL_BANDS"
            choice["spectralDatesUsed"] = used_dates
            choice["spectralItemIds"] = used_items
        except Exception as exc:
            failures.append(f"{choice['targetYear']}: {exc}")
            print(f"ERROR {failures[-1]}")

    if failures:
        raise RuntimeError("Spectral generation incomplete: " + " | ".join(failures))

    by_id = {choice["id"]: choice for choice in catalog["leftChoices"]}
    for right in catalog["rightChoices"]:
        if right["id"] == "drone":
            right["visuals"] = {"rgb": right["asset"]}
            right["supportedModes"] = ["rgb"]
            right["spectralStatus"] = "RGB_ONLY_NO_NIR_SWIR"
        elif right["id"] in by_id:
            source = by_id[right["id"]]
            right["visuals"] = source["visuals"]
            right["supportedModes"] = list(MODES)
            right["spectralStatus"] = "ACTUAL_MULTISPECTRAL_BANDS"

    catalog["spectralModes"] = [
        {"id": "rgb", "label": "RGB", "description": "สีจริง Red–Green–Blue"},
        {"id": "false_vegetation", "label": "False Color", "description": "NIR–Red–Green; พืชเด่นเป็นสีแดง"},
        {"id": "ndvi", "label": "NDVI", "description": "(NIR − Red) / (NIR + Red); ความเขียวของพืช"},
        {"id": "mndwi", "label": "MNDWI", "description": "(Green − SWIR1) / (Green + SWIR1); น้ำ–แผ่นดิน"},
        {"id": "swir", "label": "SWIR", "description": "SWIR1–NIR–Red; ความชื้น/ดินเปิด/น้ำ"},
    ]
    catalog["visual_mode_guard"] = "RGB/False Color/NDVI/MNDWI/SWIR are rendered from actual multispectral satellite bands. Drone HR remains RGB-only because its orthomosaic has no NIR/SWIR bands."
    catalog["spectral_generation"] = {
        "script": "scripts/publish_surat_thani_spectral_compare.py",
        "provider": "Microsoft Planetary Computer STAC",
        "sentinel_collection": "sentinel-2-l2a",
        "landsat_collection": "landsat-c2-l2",
        "sentinel_bands": {"blue": "B02", "green": "B03", "red": "B04", "nir": "B08", "swir1": "B11"},
        "landsat_common_assets": {"blue": "blue", "green": "green", "red": "red", "nir": "nir08", "swir1": "swir16"},
        "cloud_mask": "Sentinel SCL / Landsat QA_PIXEL",
        "composite": "median across the selected annual scene dates after QA masking",
        "same_extent": "verified raw-drone WGS84 envelope; 1800 × 1015 web pixels",
    }
    save_json(CATALOG_PATH, catalog)
    print(json.dumps({"status": "PASS", "years": len(catalog["leftChoices"]), "modes": list(MODES)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
