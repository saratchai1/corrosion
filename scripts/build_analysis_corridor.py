#!/usr/bin/env python3
"""Build a reproducible metric buffer around project polygons for shoreline analysis.

The output is an analysis corridor only. It does not change the legal/project AOI.
All buffering is performed in EPSG:32647 and transformed back to EPSG:4326.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
TO_WGS84 = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True).transform


def main() -> None:
    parser = argparse.ArgumentParser(description="Create metric shoreline-analysis buffer around project polygons")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--buffer-m", type=float, default=500.0)
    args = parser.parse_args()

    if args.buffer_m <= 0:
        parser.error("--buffer-m must be > 0")

    obj = json.loads(args.input.read_text(encoding="utf-8"))
    if obj.get("type") != "FeatureCollection" or not obj.get("features"):
        raise ValueError("input must be a non-empty GeoJSON FeatureCollection")

    source_geoms = []
    source_codes = []
    for feature in obj["features"]:
        geom = shape(feature["geometry"])
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("all source features must be non-empty polygons")
        source_geoms.append(geom)
        code = feature.get("properties", {}).get("plot_code")
        if code:
            source_codes.append(str(code))

    core_utm = unary_union([transform(TO_UTM, geom) for geom in source_geoms])
    corridor_utm = core_utm.buffer(args.buffer_m)
    corridor_wgs84 = transform(TO_WGS84, corridor_utm)

    output = {
        "type": "FeatureCollection",
        "name": f"shoreline_analysis_corridor_{int(args.buffer_m)}m",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "layer_role": "derived_analysis_corridor",
                    "buffer_m": args.buffer_m,
                    "analysis_crs": "EPSG:32647",
                    "source_crs": "EPSG:4326",
                    "derived_from": str(args.input),
                    "source_plot_codes": source_codes,
                    "core_area_m2": round(core_utm.area, 2),
                    "corridor_area_m2": round(corridor_utm.area, 2),
                    "note": "Derived buffer for shoreline/water-edge analysis; not a project/legal boundary.",
                },
                "geometry": mapping(corridor_wgs84),
            }
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "buffer_m": args.buffer_m,
                "source_plot_count": len(source_geoms),
                "core_area_m2": round(core_utm.area, 2),
                "corridor_area_m2": round(corridor_utm.area, 2),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
