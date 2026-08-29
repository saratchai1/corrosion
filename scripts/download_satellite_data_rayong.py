#!/usr/bin/env python3
"""Rayong runner for the tested satellite workflow.

Reuses download_satellite_data.py while supplying Rayong-specific AOI validation,
default catalogs, and acquisition density. This keeps the Samut Songkhram core
workflow unchanged and makes the province pilot reproducible on its own branch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import download_satellite_data as core

DEFAULT_AOI = "data/aoi/rayong_coastal_analysis_aoi.geojson"
PER_YEAR = {"sentinel2": 4, "landsat": 6, "sentinel1": 20}


def load_rayong_aoi(path: Path) -> tuple[dict[str, Any], Any]:
    from shapely.geometry import shape
    from shapely.validation import explain_validity

    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("type") != "FeatureCollection" or not obj.get("features"):
        raise ValueError(f"AOI must be a non-empty GeoJSON FeatureCollection: {path}")
    geom = obj["features"][0]["geometry"]
    shp = shape(geom)
    if shp.is_empty or shp.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI must contain a non-empty Polygon or MultiPolygon")
    if not shp.is_valid:
        raise ValueError(f"Invalid AOI geometry: {explain_validity(shp)}")
    minx, miny, maxx, maxy = shp.bounds
    if not (-180 <= minx < maxx <= 180 and -90 <= miny < maxy <= 90):
        raise ValueError(f"AOI coordinates are not valid lon/lat bounds: {shp.bounds}")
    # Safety guard: this branch is intentionally scoped to the Rayong pilot.
    if maxx < 101.45 or minx > 102.05 or maxy < 12.45 or miny > 13.00:
        raise ValueError(f"AOI does not intersect the Rayong pilot region: {shp.bounds}")
    return geom, shp


def inject_defaults(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] not in core.PROVIDERS:
        return
    dataset = argv[1]
    if "--aoi" not in argv:
        argv.extend(["--aoi", DEFAULT_AOI])
    if "--catalog" not in argv:
        argv.extend(["--catalog", f"data/catalog/rayong_{dataset}_scenes.csv"])
    if "--per-year" not in argv:
        argv.extend(["--per-year", str(PER_YEAR[dataset])])


def main() -> None:
    core.load_aoi = load_rayong_aoi
    inject_defaults(sys.argv)
    core.main()


if __name__ == "__main__":
    main()
