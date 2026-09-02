#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio as rio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.windows import Window

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
SCENE_ID = "S2A_47PPQ_20250115_0_L2A"
PATCH_SIZE = 128
SAMPLING_STEPS = 25
BANDS = [("red", "B04"), ("green", "B03"), ("blue", "B02"), ("nir", "B08")]
LOCATIONS = [
    {
        "id": "91-stc",
        "label": "91-STC",
        "lon": 99.9622,
        "lat": 13.3082,
    }
]

OUT_DIR = Path("web/public/data/superres25")
WORK_DIR = Path("outputs/samut_songkhram_superres25")


def get_item() -> dict:
    url = f"{EARTH_SEARCH}/collections/{COLLECTION}/items/{SCENE_ID}"
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def read_patch(item: dict, lon: float, lat: float) -> tuple[np.ndarray, object, object]:
    arrays: list[np.ndarray] = []
    transform = None
    crs = None
    window = None

    for asset_key, _ in BANDS:
        href = item["assets"][asset_key]["href"]
        with rio.open(href) as src:
            if crs is None:
                crs = src.crs
                transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
                x, y = transformer.transform(lon, lat)
                row, col = src.index(x, y)
                half = PATCH_SIZE // 2
                window = Window(col - half, row - half, PATCH_SIZE, PATCH_SIZE)
                transform = src.window_transform(window)
            raw = src.read(1, window=window, boundless=True, fill_value=0).astype(np.float32)

        # Element 84 Sentinel-2 L2A COG pixels are already stored in the
        # 0..10000 BOA convention expected by GeoAI/OpenSR. Do not apply the
        # STAC raster offset again here; doing so clips coastal RGB values.
        arrays.append(np.clip(np.rint(raw), 0, 10000).astype(np.uint16))

    return np.stack(arrays), transform, crs


def write_stack(path: Path, stack: np.ndarray, transform, crs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rio.open(
        path,
        "w",
        driver="GTiff",
        width=stack.shape[2],
        height=stack.shape[1],
        count=stack.shape[0],
        dtype="uint16",
        crs=crs,
        transform=transform,
        tiled=True,
        compress="deflate",
    ) as dst:
        dst.write(stack)
        for index, (_, name) in enumerate(BANDS, start=1):
            dst.set_band_description(index, name)


def rgb_stretch_limits(native: np.ndarray) -> list[tuple[float, float]]:
    limits: list[tuple[float, float]] = []
    for band in native[:3].astype(np.float32):
        valid = band[np.isfinite(band) & (band > 0)]
        if valid.size == 0:
            limits.append((0.0, 3000.0))
            continue
        lo, hi = np.percentile(valid, [1.0, 99.0])
        if hi <= lo:
            hi = lo + 1.0
        limits.append((float(lo), float(hi)))
    return limits


def to_rgb_u8(stack: np.ndarray, limits: list[tuple[float, float]]) -> np.ndarray:
    data = stack[:3].astype(np.float32)
    if np.nanmax(data) <= 2.0:
        data = data * 10000.0
    rgb = data.transpose(1, 2, 0)
    for channel, (lo, hi) in enumerate(limits):
        rgb[:, :, channel] = (rgb[:, :, channel] - lo) / (hi - lo)
    rgb = np.clip(rgb, 0.0, 1.0)
    # Mild display gamma only; both LR and SR use exactly the same transform.
    rgb = np.power(rgb, 0.9)
    return np.rint(rgb * 255.0).astype(np.uint8)


def save_webp(path: Path, rgb: np.ndarray, target_size: tuple[int, int] | None = None) -> None:
    image = Image.fromarray(rgb, mode="RGB")
    if target_size is not None and image.size != target_size:
        image = image.resize(target_size, Image.Resampling.BILINEAR)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="WEBP", quality=94, method=6)


def run() -> None:
    import geoai

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    item = get_item()
    entries = []

    for location in LOCATIONS:
        native, transform, crs = read_patch(item, location["lon"], location["lat"])
        location_work = WORK_DIR / location["id"]
        location_work.mkdir(parents=True, exist_ok=True)
        native_tif = location_work / "native_rgbnir_10m.tif"
        sr_tif = location_work / "ldsr_rgbnir_2p5m.tif"
        write_stack(native_tif, native, transform, crs)

        geoai.super_resolution(
            input_lr_path=str(native_tif),
            output_sr_path=str(sr_tif),
            rgb_nir_bands=[1, 2, 3, 4],
            sampling_steps=SAMPLING_STEPS,
            scale=4,
            compute_uncertainty=False,
            scale_factor=10000.0,
            patch_size=PATCH_SIZE,
            overlap=16,
        )

        with rio.open(sr_tif) as src:
            sr = src.read().astype(np.float32)

        limits = rgb_stretch_limits(native)
        native_rgb = to_rgb_u8(native, limits)
        sr_rgb = to_rgb_u8(sr, limits)

        original_path = OUT_DIR / f"{location['id']}-10m.webp"
        sr_path = OUT_DIR / f"{location['id']}-2p5m.webp"
        save_webp(original_path, native_rgb, target_size=(512, 512))
        save_webp(sr_path, sr_rgb)

        stats = {
            "native_rgb_nonzero_fraction": float(np.count_nonzero(native[:3]) / native[:3].size),
            "native_rgb_percentiles": [
                [float(v) for v in np.percentile(band[band > 0], [1, 50, 99])] if np.any(band > 0) else []
                for band in native[:3]
            ],
            "sr_min": float(np.nanmin(sr)),
            "sr_max": float(np.nanmax(sr)),
        }
        entries.append(
            {
                **location,
                "scene_id": SCENE_ID,
                "date": "2025-01-15",
                "original": f"data/superres25/{original_path.name}",
                "superres": f"data/superres25/{sr_path.name}",
                "stats": stats,
            }
        )

    summary = {
        "scene_id": SCENE_ID,
        "date": "2025-01-15",
        "locations": entries,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
