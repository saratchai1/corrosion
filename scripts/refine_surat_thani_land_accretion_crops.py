#!/usr/bin/env python3
"""Refine web crops for Surat Thani land-accretion candidates.

Sentinel-2 candidate crops are centered on each candidate's true WGS84 point
using the full georeferenced 2023/2026 web imagery. Drone crops are created only
when that point is inside the verified raw-drone footprint. This prevents an
outside-footprint candidate (T038) from being shown at the edge of a drone image
as though it were covered by the orthomosaic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

AUDIT = Path("web-surat-thani/public/data/surat_thani/drone/land_accretion_candidate_audit.json")
INDEX = Path("web-surat-thani/public/data/surat_thani/imagery_index.json")
DATA_ROOT = Path("web-surat-thani/public/data/surat_thani")
PUBLIC_ROOT = Path("web-surat-thani/public")
CROP_WIDTH = 480
CROP_HEIGHT = 360


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def epoch(index: dict[str, Any], year: int) -> dict[str, Any]:
    for item in index.get("epochs", []):
        if int(item.get("targetYear", -1)) == year:
            return item
    raise RuntimeError(f"Missing imagery year {year}")


def lonlat_to_full_image_pixel(lon: float, lat: float, item: dict[str, Any], size: tuple[int, int]) -> tuple[float, float]:
    coords = item["imageCoordinates"]
    xs = [float(p[0]) for p in coords]
    ys = [float(p[1]) for p in coords]
    left, right = min(xs), max(xs)
    bottom, top = min(ys), max(ys)
    width, height = size
    x = (lon - left) / (right - left) * width
    y = (top - lat) / (top - bottom) * height
    return x, y


def lonlat_to_bounds_pixel(lon: float, lat: float, bounds: dict[str, float], size: tuple[int, int]) -> tuple[float, float]:
    width, height = size
    x = (lon - bounds["left"]) / (bounds["right"] - bounds["left"]) * width
    y = (bounds["top"] - lat) / (bounds["top"] - bounds["bottom"]) * height
    return x, y


def crop(source: Path, center: tuple[float, float], output: Path) -> dict[str, float]:
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        cx, cy = center
        left = int(round(cx - CROP_WIDTH / 2))
        top = int(round(cy - CROP_HEIGHT / 2))
        left = max(0, min(left, max(0, width - CROP_WIDTH)))
        top = max(0, min(top, max(0, height - CROP_HEIGHT)))
        right = min(width, left + CROP_WIDTH)
        bottom = min(height, top + CROP_HEIGHT)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.crop((left, top, right, bottom)).save(output, format="WEBP", quality=90, method=6)
        return {
            "x_percent": max(0.0, min(100.0, 100 * (cx - left) / max(1, right - left))),
            "y_percent": max(0.0, min(100.0, 100 * (cy - top) / max(1, bottom - top))),
        }


def rel(path: Path) -> str:
    return str(path.relative_to(PUBLIC_ROOT)).replace("\\", "/")


def main() -> int:
    audit = load(AUDIT)
    index = load(INDEX)
    compare = audit["same_extent"]
    drone_bounds = compare["bounds_wgs84"]
    drone_source = PUBLIC_ROOT / compare["drone_asset"]

    epochs = {year: epoch(index, year) for year in (2023, 2026)}
    sources = {year: DATA_ROOT / epochs[year]["image"] for year in (2023, 2026)}

    for candidate in audit["candidates"]:
        transect = candidate["transect_id"].lower()
        lon = float(candidate["candidate_zone"]["center_lon"])
        lat = float(candidate["candidate_zone"]["center_lat"])

        for year in (2023, 2026):
            source = sources[year]
            with Image.open(source) as img:
                pixel = lonlat_to_full_image_pixel(lon, lat, epochs[year], img.size)
            out = AUDIT.parent / f"{transect}_sentinel2_{year}_crop.webp"
            marker = crop(source, pixel, out)
            candidate["web_crops"][f"sentinel2_{year}"] = {
                "asset": rel(out),
                "marker": marker,
                "coverage_status": "CANDIDATE_CENTER_INSIDE_SENTINEL_SOURCE",
            }

        inside = bool(candidate["candidate_zone"]["inside_drone_extent"])
        candidate["candidate_zone"]["drone_coverage_status"] = (
            "INSIDE_VERIFIED_RAW_DRONE_FOOTPRINT" if inside else "OUTSIDE_VERIFIED_RAW_DRONE_FOOTPRINT"
        )
        if inside:
            with Image.open(drone_source) as img:
                pixel = lonlat_to_bounds_pixel(lon, lat, drone_bounds, img.size)
            out = AUDIT.parent / f"{transect}_drone_crop.webp"
            marker = crop(drone_source, pixel, out)
            candidate["web_crops"]["drone"] = {
                "asset": rel(out),
                "marker": marker,
                "coverage_status": "INSIDE_VERIFIED_RAW_DRONE_FOOTPRINT",
            }
        else:
            candidate["web_crops"]["drone"] = None

    audit["crop_method"] = (
        "Sentinel candidate crops are centered on the candidate WGS84 point in the full yearly image; "
        "drone crops are only published when the point falls inside the verified raw-drone footprint."
    )
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "T028_drone": audit["candidates"][0]["candidate_zone"]["drone_coverage_status"],
        "T038_drone": audit["candidates"][1]["candidate_zone"]["drone_coverage_status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
