#!/usr/bin/env python3
"""Run cloud-masked MNDWI water extraction for selected Sentinel-2 catalog scenes.

Krabi uses Earth Search Sentinel-2 Collection 1 L2A so the archive is consistently
reprocessed across years. Radiometric scale/offset are read from each STAC item's
`raster:bands` metadata and passed explicitly to the extractor. A calibration
audit records STAC values beside source-GeoTIFF header values captured during
download so every classification remains reproducible.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import rasterio
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
EXTRACTOR = SCRIPT_DIR / "extract_water_mask.py"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
SENTINEL2_COLLECTION = "sentinel-2-c1-l2a"


def asset_calibration(item: dict, key: str) -> tuple[float, float, str]:
    asset = item.get("assets", {}).get(key, {})
    bands = asset.get("raster:bands") or []
    band = bands[0] if bands else {}
    scale = band.get("scale")
    offset = band.get("offset")
    if scale is None:
        scale = 1.0
    if offset is None:
        offset = 0.0
    return float(scale), float(offset), "earth_search_stac_raster_bands"


def fetch_item(scene_id: str) -> dict:
    url = f"{EARTH_SEARCH}/collections/{SENTINEL2_COLLECTION}/items/{scene_id}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    item = response.json()
    if item.get("id") != scene_id:
        raise ValueError(f"Earth Search returned unexpected item for {scene_id}")
    return item


def local_calibration(path: Path) -> dict[str, object]:
    with rasterio.open(path) as src:
        tags = src.tags()
        return {
            "source_geotiff_scale": float(
                tags.get("source_band_scale", src.scales[0] if src.scales else 1.0)
            ),
            "source_geotiff_offset": float(
                tags.get("source_band_offset", src.offsets[0] if src.offsets else 0.0)
            ),
            "source_geotiff_calibration_source": tags.get(
                "calibration_source", "raster_band_metadata"
            ),
            "stac_collection_tag": tags.get("stac_collection", ""),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process Sentinel-2 Collection 1 scene catalog into water masks"
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--satellite-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument(
        "--tide-status", choices=["verified", "unverified"], default="unverified"
    )
    args = parser.parse_args()

    with args.catalog.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    processed_dates: set[str] = set()
    processed = 0
    audit: list[dict[str, object]] = []
    for row in sorted(
        rows, key=lambda item: (item["acquisition_datetime_utc"], item["scene_id"])
    ):
        date = row["acquisition_datetime_utc"][:10]
        scene_id = row["scene_id"]
        if date in processed_dates:
            # The current Krabi corridor fits one tile. A future multi-tile AOI must
            # mosaic by acquisition date rather than double-counting catalog rows.
            print(f"skip duplicate acquisition date {date}: {scene_id}")
            continue

        year = date[:4]
        scene_dir = args.satellite_root / year / scene_id
        green = scene_dir / "B3_10m.tif"
        swir = scene_dir / "B11_20m.tif"
        scl = scene_dir / "SCL_20m.tif"
        missing = [path for path in (green, swir, scl) if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f"Selected scene {scene_id} is missing required bands: "
                + ", ".join(str(path) for path in missing)
            )

        item = fetch_item(scene_id)
        g_scale, g_offset, g_source = asset_calibration(item, "green")
        s_scale, s_offset, s_source = asset_calibration(item, "swir16")
        green_local = local_calibration(green)
        swir_local = local_calibration(swir)
        collection_tags_match = (
            green_local["stac_collection_tag"] in {"", SENTINEL2_COLLECTION}
            and swir_local["stac_collection_tag"] in {"", SENTINEL2_COLLECTION}
        )
        audit.append(
            {
                "scene_id": scene_id,
                "date": date,
                "collection": SENTINEL2_COLLECTION,
                "green_stac_scale": g_scale,
                "green_stac_offset": g_offset,
                "swir_stac_scale": s_scale,
                "swir_stac_offset": s_offset,
                "stac_calibration_source": g_source,
                "green_local": green_local,
                "swir_local": swir_local,
                "stac_vs_local_match": (
                    abs(g_scale - float(green_local["source_geotiff_scale"])) < 1e-12
                    and abs(
                        g_offset - float(green_local["source_geotiff_offset"])
                    )
                    < 1e-12
                    and abs(s_scale - float(swir_local["source_geotiff_scale"]))
                    < 1e-12
                    and abs(
                        s_offset - float(swir_local["source_geotiff_offset"])
                    )
                    < 1e-12
                    and collection_tags_match
                ),
            }
        )

        out_dir = args.out_root / date
        cmd = [
            sys.executable,
            str(EXTRACTOR),
            "--green",
            str(green),
            "--swir",
            str(swir),
            "--quality-mask",
            str(scl),
            "--sensor",
            "sentinel2",
            "--date",
            date,
            "--out-dir",
            str(out_dir),
            "--tide-status",
            args.tide_status,
            "--green-scale",
            str(g_scale),
            "--green-offset",
            str(g_offset),
            "--swir-scale",
            str(s_scale),
            "--swir-offset",
            str(s_offset),
        ]
        print("run:", " ".join(cmd))
        subprocess.run(cmd, check=True)
        processed_dates.add(date)
        processed += 1

    if processed == 0:
        raise SystemExit("No Sentinel-2 Collection 1 scenes were processed")

    audit_path = args.out_root.parent / "sentinel2_calibration_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "provider": "Element 84 Earth Search",
                "collection": SENTINEL2_COLLECTION,
                "policy": (
                    "Use Collection 1 reprocessed L2A only; apply each item's STAC "
                    "raster:bands scale/offset explicitly during index calculation"
                ),
                "scene_count": len(audit),
                "mismatch_count": sum(
                    not bool(record["stac_vs_local_match"]) for record in audit
                ),
                "scenes": audit,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"processed_dates={processed}")
    print(f"calibration_audit={audit_path}")


if __name__ == "__main__":
    main()
