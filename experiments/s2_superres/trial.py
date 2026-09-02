#!/usr/bin/env python3
"""Small, auditable Sentinel-2 super-resolution trial for Samut Songkhram.

The experiment intentionally uses only a 128x128 Sentinel-2 patch (~1.28 km square)
so LDSR-S2 can be tested before attempting a large-area product.

Outputs:
- native_rgbnir_10m.tif       standardized BOA RGB+NIR, 10 m
- bicubic_rgbnir_2p5m.tif     interpolation baseline, 2.5 m grid
- ldsr_rgbnir_2p5m.tif        LDSR-S2 output, 2.5 m grid
- uncertainty.tif             optional diffusion uncertainty map
- comparison.png              native-nearest vs bicubic vs LDSR quicklook
- metrics.json                downsample-back radiometric consistency metrics

Important: a 2.5 m SR grid is model-reconstructed detail, not new 2.5 m sensor
measurements. The downsample-back test checks spectral consistency only; it does
not prove that reconstructed sub-10 m objects are spatially correct.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import requests
import rasterio as rio
from matplotlib import pyplot as plt
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.windows import Window
from rasterio.warp import reproject

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
DEFAULT_SCENE = "S2A_47PPQ_20250115_0_L2A"
# Mae Klong mouth / coastal test point inside the repository's provisional AOI.
DEFAULT_LON = 100.000
DEFAULT_LAT = 13.350
BANDS = [("red", "B04"), ("green", "B03"), ("blue", "B02"), ("nir", "B08")]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--scene-id", default=DEFAULT_SCENE)
    p.add_argument("--lon", type=float, default=DEFAULT_LON)
    p.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p.add_argument("--patch-size", type=int, default=128)
    p.add_argument("--out-dir", type=Path, default=Path("outputs/s2_superres_trial"))
    p.add_argument("--sampling-steps", type=int, default=20)
    p.add_argument("--uncertainty", action="store_true")
    p.add_argument("--n-variations", type=int, default=3)
    return p.parse_args()


def get_item(scene_id: str) -> dict:
    url = f"{EARTH_SEARCH}/collections/{COLLECTION}/items/{scene_id}"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.json()


def asset_scale_offset(asset: dict) -> tuple[float, float]:
    bands = asset.get("raster:bands") or []
    info = bands[0] if bands else {}
    scale = info.get("scale")
    offset = info.get("offset")
    # Sentinel-2 BOA reflectance convention if metadata is missing.
    return (0.0001 if scale is None else float(scale), 0.0 if offset is None else float(offset))


def read_standardized_patch(item: dict, lon: float, lat: float, size: int):
    arrays: list[np.ndarray] = []
    transform = None
    crs = None
    calibration = {}

    for asset_key, band_name in BANDS:
        asset = item["assets"][asset_key]
        href = asset["href"]
        scale, offset = asset_scale_offset(asset)
        calibration[band_name] = {"scale": scale, "offset": offset, "href": href}

        with rio.open(href) as src:
            if crs is None:
                crs = src.crs
                tx = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
                x, y = tx.transform(lon, lat)
                row, col = src.index(x, y)
                half = size // 2
                window = Window(col - half, row - half, size, size)
                transform = src.window_transform(window)
            raw = src.read(1, window=window, boundless=True, fill_value=0).astype(np.float32)

        # Standardize to uint16 BOA reflectance in the 0..10000 convention used
        # by the GeoAI/OpenSR example, honoring Earth Search raster scale/offset.
        reflectance = raw * scale + offset
        dn = np.clip(np.rint(reflectance * 10000.0), 0, 10000).astype(np.uint16)
        arrays.append(dn)

    return np.stack(arrays), transform, crs, calibration


def write_stack(path: Path, stack: np.ndarray, transform, crs, *, dtype=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    dtype = dtype or stack.dtype
    with rio.open(
        path,
        "w",
        driver="GTiff",
        width=stack.shape[2],
        height=stack.shape[1],
        count=stack.shape[0],
        dtype=dtype,
        crs=crs,
        transform=transform,
        tiled=True,
        compress="deflate",
    ) as dst:
        dst.write(stack.astype(dtype, copy=False))
        for i, (_, band_name) in enumerate(BANDS, start=1):
            if i <= stack.shape[0]:
                dst.set_band_description(i, band_name)


def resample_stack(stack: np.ndarray, src_transform, crs, factor: int, method: Resampling):
    out = np.zeros((stack.shape[0], stack.shape[1] * factor, stack.shape[2] * factor), dtype=np.float32)
    dst_transform = src_transform * Affine.scale(1 / factor, 1 / factor)
    for i in range(stack.shape[0]):
        reproject(
            source=stack[i].astype(np.float32),
            destination=out[i],
            src_transform=src_transform,
            src_crs=crs,
            dst_transform=dst_transform,
            dst_crs=crs,
            resampling=method,
        )
    return out, dst_transform


def downsample_to_native(sr_path: Path, native_shape, native_transform, native_crs):
    with rio.open(sr_path) as src:
        sr = src.read().astype(np.float32)
        out = np.zeros(native_shape, dtype=np.float32)
        for i in range(min(sr.shape[0], native_shape[0])):
            reproject(
                source=sr[i],
                destination=out[i],
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=native_transform,
                dst_crs=native_crs,
                resampling=Resampling.average,
            )
    return out


def per_band_metrics(native: np.ndarray, reconstructed: np.ndarray) -> dict:
    result = {}
    for i, (_, name) in enumerate(BANDS):
        a = native[i].astype(np.float32)
        b = reconstructed[i].astype(np.float32)
        valid = (a > 0) & np.isfinite(a) & np.isfinite(b)
        if not np.any(valid):
            result[name] = {"mae_dn": None, "rmse_dn": None, "bias_dn": None}
            continue
        d = b[valid] - a[valid]
        result[name] = {
            "mae_dn": float(np.mean(np.abs(d))),
            "rmse_dn": float(np.sqrt(np.mean(d * d))),
            "bias_dn": float(np.mean(d)),
            "n": int(valid.sum()),
        }
    return result


def stretch_rgb(stack: np.ndarray) -> np.ndarray:
    rgb = stack[:3].astype(np.float32).transpose(1, 2, 0)
    valid = np.isfinite(rgb)
    for c in range(3):
        vals = rgb[:, :, c][valid[:, :, c]]
        if vals.size:
            lo, hi = np.percentile(vals, [2, 98])
            rgb[:, :, c] = (rgb[:, :, c] - lo) / max(hi - lo, 1e-6)
    return np.clip(rgb, 0, 1)


def make_comparison(native: np.ndarray, bicubic: np.ndarray, sr_path: Path, out_path: Path):
    with rio.open(sr_path) as src:
        sr = src.read().astype(np.float32)

    nearest = np.repeat(np.repeat(native.astype(np.float32), 4, axis=1), 4, axis=2)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, data, title in zip(
        axes,
        [nearest, bicubic, sr],
        ["Sentinel-2 native 10 m (nearest display)", "Bicubic 2.5 m grid", "LDSR-S2 2.5 m grid"],
    ):
        ax.imshow(stretch_rgb(data))
        ax.set_title(title)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    item = get_item(args.scene_id)
    native, transform, crs, calibration = read_standardized_patch(
        item, args.lon, args.lat, args.patch_size
    )

    native_path = args.out_dir / "native_rgbnir_10m.tif"
    write_stack(native_path, native, transform, crs)

    bicubic, bicubic_transform = resample_stack(native, transform, crs, 4, Resampling.cubic)
    bicubic_path = args.out_dir / "bicubic_rgbnir_2p5m.tif"
    write_stack(bicubic_path, np.clip(np.rint(bicubic), 0, 10000).astype(np.uint16), bicubic_transform, crs)

    # Lazy import keeps data-prep usable without the heavy SR extra installed.
    import geoai

    sr_path = args.out_dir / "ldsr_rgbnir_2p5m.tif"
    unc_path = args.out_dir / "uncertainty.tif"
    geoai.super_resolution(
        input_lr_path=str(native_path),
        output_sr_path=str(sr_path),
        output_uncertainty_path=str(unc_path) if args.uncertainty else None,
        rgb_nir_bands=[1, 2, 3, 4],
        sampling_steps=args.sampling_steps,
        n_variations=args.n_variations,
        scale=4,
        compute_uncertainty=args.uncertainty,
        scale_factor=10000.0,
        patch_size=args.patch_size,
        overlap=16,
    )

    sr_back = downsample_to_native(sr_path, native.shape, transform, crs)
    bicubic_back = downsample_to_native(bicubic_path, native.shape, transform, crs)

    metrics = {
        "scene_id": args.scene_id,
        "target_lon_lat": [args.lon, args.lat],
        "patch_pixels_native": args.patch_size,
        "native_resolution_m": 10,
        "sr_grid_resolution_m": 2.5,
        "sampling_steps": args.sampling_steps,
        "uncertainty_enabled": args.uncertainty,
        "calibration": calibration,
        "bicubic_downsample_back": per_band_metrics(native, bicubic_back),
        "ldsr_downsample_back": per_band_metrics(native, sr_back),
        "interpretation": (
            "Downsample-back metrics test radiometric consistency only. They do not validate "
            "the truth of model-generated sub-10 m spatial detail."
        ),
    }
    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    make_comparison(native, bicubic, sr_path, args.out_dir / "comparison.png")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
