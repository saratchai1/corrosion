#!/usr/bin/env python3
"""Run the existing satellite workflow for Krabi without mixing regional outputs.

This wrapper deliberately reuses scripts/download_satellite_data.py. It only:
1) accepts a multi-feature Krabi GeoJSON and unions the polygons for STAC search;
2) replaces the Samut Songkhram-only AOI guard with a Krabi working envelope;
3) changes the working directory so catalogs/rasters/previews/manifests are written
   under regions/krabi/data instead of the inherited Samut Songkhram data tree;
4) records source GeoTIFF band scale/offset in AOI-clipped COG tags so spectral
   indices can use scene-specific radiometric calibration without rewriting COGs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.validation import explain_validity

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
REGION_ROOT = REPO_ROOT / "regions" / "krabi"
DEFAULT_AOI = REGION_ROOT / "data" / "aoi" / "krabi_pdd_plots.geojson"

# Keep sibling imports (build_previews, etc.) working after chdir(REGION_ROOT).
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import download_satellite_data as core  # noqa: E402

ORIGINAL_CLIP_ASSET = core.clip_asset


def load_krabi_aoi(path: Path):
    """Load/validate all polygon features and return their union for STAC queries."""
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("type") != "FeatureCollection" or not obj.get("features"):
        raise ValueError(f"AOI must be a non-empty GeoJSON FeatureCollection: {path}")

    polygons = []
    for index, feature in enumerate(obj["features"], 1):
        geom = feature.get("geometry")
        if not geom:
            raise ValueError(f"AOI feature {index} has no geometry")
        shp = shape(geom)
        if shp.is_empty or shp.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(
                f"AOI feature {index} must be a Polygon/MultiPolygon, got {shp.geom_type}"
            )
        if not shp.is_valid:
            raise ValueError(
                f"Invalid AOI geometry in feature {index}: {explain_validity(shp)}"
            )
        polygons.append(shp)

    union = unary_union(polygons)
    if union.is_empty or union.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"AOI union is not polygonal: {union.geom_type}")
    if not union.is_valid:
        raise ValueError(f"Invalid AOI union: {explain_validity(union)}")

    minx, miny, maxx, maxy = union.bounds
    if not (-180 <= minx < maxx <= 180 and -90 <= miny < maxy <= 90):
        raise ValueError(f"AOI coordinates are not valid lon/lat bounds: {union.bounds}")

    # Broad safety envelope around coastal Krabi. This catches swapped CRS/coordinates
    # without pretending to be an administrative boundary.
    if maxx < 98.45 or minx > 99.45 or maxy < 7.45 or miny > 8.65:
        raise ValueError(
            "AOI does not intersect the Krabi coastal working envelope: "
            f"{union.bounds}"
        )

    return mapping(union), union


def source_calibration(href: str) -> tuple[float, float]:
    import rasterio

    with rasterio.Env(**core.raster_env()):
        with rasterio.open(href) as src:
            scale = float(src.scales[0]) if src.scales and src.scales[0] is not None else 1.0
            offset = float(src.offsets[0]) if src.offsets and src.offsets[0] is not None else 0.0
    return scale, offset


def clip_asset_with_calibration_tags(
    href: str,
    geom4326: dict[str, Any],
    outpath: Path,
    *,
    resolution: float,
    categorical: bool,
    tags: dict[str, str],
    dst_crs: str = core.ANALYSIS_CRS,
) -> Path:
    """Read source calibration first and persist it during the one COG write."""
    scale, offset = source_calibration(href)
    enriched_tags = {
        **tags,
        "source_band_scale": str(scale),
        "source_band_offset": str(offset),
        "calibration_source": "source_geotiff_band_metadata",
    }
    return ORIGINAL_CLIP_ASSET(
        href,
        geom4326,
        outpath,
        resolution=resolution,
        categorical=categorical,
        tags=enriched_tags,
        dst_crs=dst_crs,
    )


def main() -> None:
    REGION_ROOT.mkdir(parents=True, exist_ok=True)
    core.load_aoi = load_krabi_aoi
    core.clip_asset = clip_asset_with_calibration_tags

    argv = list(sys.argv[1:])
    if "--aoi" not in argv:
        argv.extend(["--aoi", str(DEFAULT_AOI)])

    # The reused core script writes relative paths under data/. Isolate them here.
    os.chdir(REGION_ROOT)
    sys.argv = [sys.argv[0], *argv]
    core.main()


if __name__ == "__main__":
    main()
