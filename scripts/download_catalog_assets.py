#!/usr/bin/env python3
"""Download the exact Sentinel-2 assets listed in a versioned scene catalog.

This utility does not re-run scene discovery or ranking. It fetches each STAC item
identified by ``source_url`` in the catalog and clips the requested assets to the
project AOI using the same COG writer as ``download_satellite_data.py``. This
keeps analysis inputs reproducible even when provider search rankings change.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import requests

from scripts.download_satellite_data import (
    ASSETS,
    LICENSES,
    clip_asset,
    load_aoi,
    sha256,
    sign_item,
)


DEFAULT_CATALOG = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
)
DEFAULT_AOI = Path("data/aoi/samut_songkhram_project_analysis_aoi.geojson")
DEFAULT_BANDS = ("B2", "B3", "B4", "B8", "B11", "SCL")


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"catalog is empty: {path}")
    return rows


def output_paths(row: dict[str, str]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in row.get("local_path", "").split(";"):
        if not raw:
            continue
        path = Path(raw)
        band = path.name.split("_")[0].upper()
        paths[band] = path
    return paths


def fetch_item(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    item = response.json()
    if not isinstance(item, dict) or not item.get("id"):
        raise ValueError(f"STAC item response is invalid: {url}")
    return item


def download_catalog(
    *,
    catalog: Path,
    aoi: Path,
    bands: tuple[str, ...],
    overwrite: bool,
    manifest: Path | None,
) -> dict[str, Any]:
    rows = load_rows(catalog)
    geom4326, _ = load_aoi(aoi)
    available = {spec[0].upper(): spec for spec in ASSETS["sentinel2"]}
    unknown = [band for band in bands if band not in available]
    if unknown:
        raise ValueError(f"unknown Sentinel-2 band(s): {unknown}")

    session = requests.Session()
    session.headers["User-Agent"] = (
        "corrosion-tide-aware-analysis/1.0 "
        "(https://github.com/saratchai1/corrosion)"
    )

    files: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if row.get("dataset") != "sentinel2":
            continue
        scene_id = row.get("scene_id", "")
        if not scene_id or scene_id in seen_ids:
            continue
        seen_ids.add(scene_id)
        item = fetch_item(session, row["source_url"])
        if item["id"] != scene_id:
            raise ValueError(
                f"catalog/STAC scene mismatch: catalog={scene_id}, item={item['id']}"
            )
        signed = sign_item(item, "sentinel2")
        expected_paths = output_paths(row)
        print(f"[{index}/{len(rows)}] {scene_id}", flush=True)
        for band in bands:
            band_name, asset_key, resolution, categorical = available[band]
            asset = signed.get("assets", {}).get(asset_key)
            if not asset:
                raise KeyError(f"{scene_id} has no asset {asset_key!r}")
            expected = expected_paths.get(band_name.upper())
            if expected is None:
                raise ValueError(
                    f"{scene_id}: catalog local_path has no target for {band_name}"
                )
            if expected.exists() and expected.stat().st_size > 0 and not overwrite:
                print(f"  reuse {expected}", flush=True)
            else:
                print(f"  clip {band_name} -> {expected}", flush=True)
                clip_asset(
                    asset["href"],
                    geom4326,
                    expected,
                    resolution=resolution,
                    categorical=categorical,
                    tags={
                        "dataset": "sentinel2",
                        "scene_id": scene_id,
                        "band": band_name,
                        "acquisition_datetime_utc": row[
                            "acquisition_datetime_utc"
                        ],
                        "native_resolution_m": str(int(resolution)),
                        "source_url": row["source_url"],
                        "source_license": row.get(
                            "source_license", LICENSES["sentinel2"]
                        ),
                        "tide_station": row.get("tide_station", ""),
                        "tide_level_m_msl": row.get("tide_level", ""),
                        "tide_datum": row.get("tide_datum", ""),
                        "tide_status": row.get("tide_status", ""),
                    },
                )
            digest = sha256(expected)
            files.append(
                {
                    "scene_id": scene_id,
                    "band": band_name,
                    "path": str(expected),
                    "size_bytes": expected.stat().st_size,
                    "sha256": digest,
                }
            )

    expected_scene_count = len(
        {row["scene_id"] for row in rows if row.get("dataset") == "sentinel2"}
    )
    if len(seen_ids) != expected_scene_count:
        raise RuntimeError(
            f"downloaded scene count mismatch: {len(seen_ids)} vs {expected_scene_count}"
        )
    result = {
        "catalog": str(catalog),
        "aoi": str(aoi),
        "scene_count": len(seen_ids),
        "bands": list(bands),
        "file_count": len(files),
        "files": files,
    }
    if manifest is not None:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument(
        "--bands",
        default=",".join(DEFAULT_BANDS),
        help="Comma-separated catalog band names",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--manifest", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bands = tuple(
        value.strip().upper()
        for value in args.bands.split(",")
        if value.strip()
    )
    result = download_catalog(
        catalog=args.catalog,
        aoi=args.aoi,
        bands=bands,
        overwrite=args.overwrite,
        manifest=args.manifest,
    )
    print(
        json.dumps(
            {
                "scene_count": result["scene_count"],
                "file_count": result["file_count"],
                "bands": result["bands"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
