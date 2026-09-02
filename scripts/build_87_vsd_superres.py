#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio as rio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.windows import Window

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
LON = 99.8642117
LAT = 13.2632254
PLOT_ID = "87-vsd"
LABEL = "87-VSD"
PATCH_SIZE = 128
SAMPLING_STEPS = 20
BANDS = [("red", "B04"), ("green", "B03"), ("blue", "B02"), ("nir", "B08")]
OUT_DIR = Path("generated/87-VSD")
WORK_DIR = Path("outputs/87-VSD")


def search_items(start: str, end: str) -> list[dict]:
    payload = {
        "collections": [COLLECTION],
        "intersects": {"type": "Point", "coordinates": [LON, LAT]},
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": 100,
    }
    response = requests.post(f"{EARTH_SEARCH}/search", json=payload, timeout=120)
    response.raise_for_status()
    items = response.json().get("features", [])
    return sorted(items, key=lambda item: float(item.get("properties", {}).get("eo:cloud_cover", 100.0)))


def patch_window(src, lon: float, lat: float) -> Window | None:
    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    x, y = transformer.transform(lon, lat)
    left, bottom, right, top = src.bounds
    if not (left <= x <= right and bottom <= y <= top):
        return None
    row, col = src.index(x, y)
    half = PATCH_SIZE // 2
    return Window(col - half, row - half, PATCH_SIZE, PATCH_SIZE)


def candidate_is_valid(item: dict) -> bool:
    href = item.get("assets", {}).get("red", {}).get("href")
    if not href:
        return False
    try:
        with rio.open(href) as src:
            window = patch_window(src, LON, LAT)
            if window is None:
                return False
            raw = src.read(1, window=window, boundless=True, fill_value=0)
        return float(np.count_nonzero(raw) / raw.size) > 0.90
    except Exception as exc:
        print("candidate check failed", item.get("id"), repr(exc))
        return False


def choose_item() -> dict:
    windows = [
        ("2025-01-01", "2025-02-28"),
        ("2024-12-01", "2025-04-30"),
    ]
    seen: set[str] = set()
    for start, end in windows:
        for item in search_items(start, end):
            item_id = str(item.get("id"))
            if item_id in seen:
                continue
            seen.add(item_id)
            cloud = float(item.get("properties", {}).get("eo:cloud_cover", 100.0))
            if cloud > 20.0:
                continue
            if candidate_is_valid(item):
                print("selected", item_id, "cloud", cloud)
                return item
    raise RuntimeError("No usable Sentinel-2 scene found for 87-VSD")


def read_patch(item: dict) -> tuple[np.ndarray, object, object]:
    arrays: list[np.ndarray] = []
    transform = None
    crs = None
    window = None
    for asset_key, _ in BANDS:
        asset = item.get("assets", {}).get(asset_key)
        if not asset:
            raise RuntimeError(f"Missing asset {asset_key} in {item.get('id')}")
        with rio.open(asset["href"]) as src:
            if crs is None:
                crs = src.crs
                window = patch_window(src, LON, LAT)
                if window is None:
                    raise RuntimeError("Selected item does not cover 87-VSD")
                transform = src.window_transform(window)
            raw = src.read(1, window=window, boundless=True, fill_value=0).astype(np.float32)
        arrays.append(np.clip(np.rint(raw), 0, 10000).astype(np.uint16))
    return np.stack(arrays), transform, crs


def write_stack(path: Path, stack: np.ndarray, transform, crs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rio.open(
        path, "w", driver="GTiff", width=stack.shape[2], height=stack.shape[1],
        count=stack.shape[0], dtype="uint16", crs=crs, transform=transform,
        tiled=True, compress="deflate",
    ) as dst:
        dst.write(stack)
        for index, (_, name) in enumerate(BANDS, start=1):
            dst.set_band_description(index, name)


def rgb_limits(native: np.ndarray) -> list[tuple[float, float]]:
    result = []
    for band in native[:3].astype(np.float32):
        valid = band[np.isfinite(band) & (band > 0)]
        if valid.size == 0:
            result.append((0.0, 3000.0))
        else:
            lo, hi = np.percentile(valid, [1.0, 99.0])
            result.append((float(lo), float(max(hi, lo + 1.0))))
    return result


def to_rgb(stack: np.ndarray, limits: list[tuple[float, float]]) -> np.ndarray:
    data = stack[:3].astype(np.float32)
    if np.nanmax(data) <= 2.0:
        data *= 10000.0
    rgb = data.transpose(1, 2, 0)
    for channel, (lo, hi) in enumerate(limits):
        rgb[:, :, channel] = (rgb[:, :, channel] - lo) / (hi - lo)
    rgb = np.clip(rgb, 0.0, 1.0)
    rgb = np.power(rgb, 0.9)
    return np.rint(rgb * 255.0).astype(np.uint8)


def save_webp(path: Path, rgb: np.ndarray, resize: bool = False) -> None:
    image = Image.fromarray(rgb, mode="RGB")
    if resize and image.size != (512, 512):
        image = image.resize((512, 512), Image.Resampling.BILINEAR)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="WEBP", quality=94, method=6)


def main() -> None:
    import geoai

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    item = choose_item()
    native, transform, crs = read_patch(item)
    nonzero = float(np.count_nonzero(native[:3]) / native[:3].size)
    if nonzero < 0.90:
        raise RuntimeError(f"Unexpected low valid-pixel fraction: {nonzero}")

    native_tif = WORK_DIR / "native_rgbnir.tif"
    sr_tif = WORK_DIR / "ldsr_rgbnir.tif"
    write_stack(native_tif, native, transform, crs)
    geoai.super_resolution(
        input_lr_path=str(native_tif), output_sr_path=str(sr_tif),
        rgb_nir_bands=[1, 2, 3, 4], sampling_steps=SAMPLING_STEPS,
        scale=4, compute_uncertainty=False, scale_factor=10000.0,
        patch_size=PATCH_SIZE, overlap=16,
    )
    with rio.open(sr_tif) as src:
        sr = src.read().astype(np.float32)

    limits = rgb_limits(native)
    original = OUT_DIR / f"{PLOT_ID}-10m.webp"
    refined = OUT_DIR / f"{PLOT_ID}-2p5m.webp"
    save_webp(original, to_rgb(native, limits), resize=True)
    save_webp(refined, to_rgb(sr, limits))

    properties = item.get("properties", {})
    acquired = str(properties.get("datetime") or properties.get("start_datetime"))
    date = datetime.fromisoformat(acquired.replace("Z", "+00:00")).date().isoformat()
    entry = {
        "id": PLOT_ID,
        "label": LABEL,
        "lon": LON,
        "lat": LAT,
        "scene_id": item.get("id"),
        "date": date,
        "original": f"data/superres25/{original.name}",
        "superres": f"data/superres25/{refined.name}",
        "stats": {
            "native_rgb_nonzero_fraction": nonzero,
            "cloud_cover_scene": float(properties.get("eo:cloud_cover", 100.0)),
            "sr_min": float(np.nanmin(sr)),
            "sr_max": float(np.nanmax(sr)),
        },
    }
    (OUT_DIR / f"{PLOT_ID}.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
