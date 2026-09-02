#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator

import numpy as np
import rasterio as rio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.windows import Window

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
SCENE_ID = "S2A_47PPQ_20250115_0_L2A"
SCENE_DATE = "2025-01-15"
PATCH_SIZE = 128
DEFAULT_SAMPLING_STEPS = 20
BANDS = [("red", "B04"), ("green", "B03"), ("blue", "B02"), ("nir", "B08")]
PLOTS_PATH = Path("web/public/data/project/plots.geojson")
DEFAULT_OUT_DIR = Path("web/public/data/superres25")
DEFAULT_WORK_DIR = Path("outputs/samut_songkhram_superres25")
PLOT_ORDER = ["91-STC", "92-STC", "93-STC", "94-STC", "95-STC", "96-STC", "97-STC", "98-STC", "87-VSD"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot-id", help="Generate one plot only, e.g. 92-STC")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--sampling-steps", type=int, default=DEFAULT_SAMPLING_STEPS)
    return parser.parse_args()


def iter_points(value) -> Iterator[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_points(child)


def load_locations(plot_id: str | None = None) -> list[dict]:
    obj = json.loads(PLOTS_PATH.read_text(encoding="utf-8"))
    locations: list[dict] = []
    for feature in obj.get("features", []):
        label = str(feature.get("properties", {}).get("plot_id", "")).strip()
        if label not in PLOT_ORDER:
            continue
        points = list(iter_points(feature.get("geometry", {}).get("coordinates", [])))
        if not points:
            raise RuntimeError(f"No coordinates for {label}")
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        locations.append(
            {
                "id": label.lower(),
                "label": label,
                "lon": (minx + maxx) / 2.0,
                "lat": (miny + maxy) / 2.0,
                "bbox": [minx, miny, maxx, maxy],
            }
        )

    order = {label: i for i, label in enumerate(PLOT_ORDER)}
    locations.sort(key=lambda item: order[item["label"]])
    if plot_id:
        wanted = plot_id.strip().upper()
        locations = [item for item in locations if item["label"].upper() == wanted]
        if not locations:
            raise SystemExit(f"Plot not found: {plot_id}")
    if not locations:
        raise RuntimeError("No Samut Songkhram plots found")
    return locations


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

        # Earth Search Sentinel-2 L2A COG values are already stored in the
        # 0..10000 BOA convention used by the OpenSR/GeoAI pipeline.
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
    rgb = np.power(rgb, 0.9)
    return np.rint(rgb * 255.0).astype(np.uint8)


def save_webp(path: Path, rgb: np.ndarray, target_size: tuple[int, int] | None = None) -> None:
    image = Image.fromarray(rgb, mode="RGB")
    if target_size is not None and image.size != target_size:
        image = image.resize(target_size, Image.Resampling.BILINEAR)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="WEBP", quality=94, method=6)


def process_location(item: dict, location: dict, out_dir: Path, work_dir: Path, sampling_steps: int) -> dict:
    import geoai

    native, transform, crs = read_patch(item, location["lon"], location["lat"])
    location_work = work_dir / location["id"]
    location_work.mkdir(parents=True, exist_ok=True)
    native_tif = location_work / "native_rgbnir_10m.tif"
    sr_tif = location_work / "ldsr_rgbnir_2p5m.tif"
    write_stack(native_tif, native, transform, crs)

    geoai.super_resolution(
        input_lr_path=str(native_tif),
        output_sr_path=str(sr_tif),
        rgb_nir_bands=[1, 2, 3, 4],
        sampling_steps=sampling_steps,
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

    original_path = out_dir / f"{location['id']}-10m.webp"
    sr_path = out_dir / f"{location['id']}-2p5m.webp"
    save_webp(original_path, native_rgb, target_size=(512, 512))
    save_webp(sr_path, sr_rgb)

    entry = {
        **location,
        "scene_id": SCENE_ID,
        "date": SCENE_DATE,
        "original": f"data/superres25/{original_path.name}",
        "superres": f"data/superres25/{sr_path.name}",
        "stats": {
            "native_rgb_nonzero_fraction": float(np.count_nonzero(native[:3]) / native[:3].size),
            "native_rgb_percentiles": [
                [float(v) for v in np.percentile(band[band > 0], [1, 50, 99])] if np.any(band > 0) else []
                for band in native[:3]
            ],
            "sr_min": float(np.nanmin(sr)),
            "sr_max": float(np.nanmax(sr)),
        },
    }
    (out_dir / f"{location['id']}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return entry


def run() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    locations = load_locations(args.plot_id)
    item = get_item()
    entries = [
        process_location(item, location, args.out_dir, args.work_dir, args.sampling_steps)
        for location in locations
    ]

    if not args.plot_id:
        summary = {"scene_id": SCENE_ID, "date": SCENE_DATE, "locations": entries}
        (args.out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(entries[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
