#!/usr/bin/env python3
"""Build the verified Samut Songkhram project-plot AOI from the dashboard data.

The source TypeScript was generated from ``kmz/STC_VSD_EVR.kmz`` in
``saratchai1/mangrove-drone-dashboard``.  Official participating areas come
from that repository's ``areaTable.csv`` and are deliberately kept separate
from geometry-calculated areas.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPOSITORY = "https://github.com/saratchai1/mangrove-drone-dashboard"
SOURCE_COMMIT = "825d91b8d6d9f3c0e224e71266d7d2ced7cf4dc9"
SOURCE_RAW = (
    "https://raw.githubusercontent.com/saratchai1/"
    f"mangrove-drone-dashboard/{SOURCE_COMMIT}"
)
PLOT_CODES = [
    "91-STC",
    "92-STC",
    "93-STC",
    "94-STC",
    "95-STC",
    "96-STC",
    "97-STC",
    "98-STC",
    "87-VSD",
]
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True)
TO_WEB = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True)


def read_source(path: str | None, relative_url: str) -> tuple[str, str]:
    if path:
        source = Path(path).resolve()
        return source.read_text(encoding="utf-8-sig"), str(source)
    url = f"{SOURCE_RAW}/{relative_url}"
    try:
        with urlopen(url, timeout=120) as response:  # nosec B310 - pinned GitHub source
            return response.read().decode("utf-8-sig"), url
    except HTTPError as exc:
        if exc.code != 404:
            raise
        # Private repositories return 404 for unauthenticated raw URLs. Use
        # the user's existing GitHub CLI session without persisting a token.
        api_path = (
            "repos/saratchai1/mangrove-drone-dashboard/contents/"
            f"{relative_url}?ref={SOURCE_COMMIT}"
        )
        payload = json.loads(
            subprocess.check_output(["gh", "api", api_path], text=True)
        )
        content = base64.b64decode(payload["content"]).decode("utf-8-sig")
        return content, url


def parse_areas(text: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = (row.get("AREA CODE") or "").strip().upper()
        if code not in PLOT_CODES:
            continue
        records[code] = {
            "province": (row.get("PROVINCE") or "").strip(),
            "official_participating_area_rai": float(
                (row.get(" PPD AREA") or "").strip().replace(",", "")
            ),
        }
    missing = set(PLOT_CODES) - set(records)
    if missing:
        raise ValueError(f"areaTable.csv is missing requested plots: {sorted(missing)}")
    return records


def parse_plot_geometry(text: str, code: str) -> tuple[Any, int]:
    pattern = (
        rf'^\s*"{re.escape(code)}": \{{ code: "[^"]+", rings: '
        r"(\[.*\]) \},$"
    )
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"plotBoundaries.ts is missing {code}")
    rings = json.loads(match.group(1))
    polygons = []
    for coordinates in rings:
        polygon = Polygon(coordinates)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        raise ValueError(f"{code} contains no usable polygon rings")
    # The generated source can contain overlapping representations of the same
    # plot. Spatial union prevents those overlaps from being counted twice.
    geometry = unary_union(polygons).buffer(0)
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"{code} did not produce a valid unioned geometry")
    return geometry, len(rings)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--area-table", help="Optional local areaTable.csv")
    parser.add_argument(
        "--plot-boundaries", help="Optional local web/src/data/plotBoundaries.ts"
    )
    parser.add_argument(
        "--buffer-m",
        type=float,
        default=2500.0,
        help="Context buffer around project plots for satellite analysis",
    )
    parser.add_argument(
        "--plots-output",
        default="data/aoi/samut_songkhram_project_plots.geojson",
    )
    parser.add_argument(
        "--analysis-output",
        default="data/aoi/samut_songkhram_project_analysis_aoi.geojson",
    )
    args = parser.parse_args()
    if args.buffer_m <= 0:
        parser.error("--buffer-m must be positive")

    area_text, area_source = read_source(args.area_table, "areaTable.csv")
    boundary_text, boundary_source = read_source(
        args.plot_boundaries, "web/src/data/plotBoundaries.ts"
    )
    official = parse_areas(area_text)
    features = []
    projected_geometries = []
    for sequence, code in enumerate(PLOT_CODES, start=1):
        geometry, source_ring_count = parse_plot_geometry(boundary_text, code)
        projected = transform(TO_UTM.transform, geometry)
        projected_geometries.append(projected)
        geometry_area_rai = projected.area / 1600.0
        official_area_rai = official[code]["official_participating_area_rai"]
        difference_rai = geometry_area_rai - official_area_rai
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "sequence": sequence,
                    "plot_id": code,
                    "province": official[code]["province"],
                    "official_participating_area_rai": round(official_area_rai, 6),
                    "geometry_area_rai": round(geometry_area_rai, 6),
                    "area_difference_rai": round(difference_rai, 6),
                    "area_difference_percent": round(
                        difference_rai / official_area_rai * 100.0, 4
                    ),
                    "source_crs": "EPSG:4326",
                    "analysis_crs": "EPSG:32647",
                    "source_ring_count": source_ring_count,
                    "geometry_operation": "valid polygon rings unioned to remove overlap",
                    "geometry_source": "web/src/data/plotBoundaries.ts",
                    "upstream_original": "kmz/STC_VSD_EVR.kmz",
                },
                "geometry": mapping(geometry),
            }
        )

    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    official_total = sum(
        item["properties"]["official_participating_area_rai"] for item in features
    )
    geometry_total = sum(item["properties"]["geometry_area_rai"] for item in features)
    plots = {
        "type": "FeatureCollection",
        "name": "samut_songkhram_verified_project_plots",
        "metadata": {
            "status": "verified plot selection; geometry inherited from generated dashboard source",
            "plot_count": len(features),
            "plot_ids": PLOT_CODES,
            "province": "สมุทรสงคราม",
            "official_participating_area_rai": round(official_total, 6),
            "geometry_area_rai": round(geometry_total, 6),
            "geometry_area_difference_rai": round(geometry_total - official_total, 6),
            "source_repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "area_source": f"{SOURCE_REPOSITORY}/blob/{SOURCE_COMMIT}/areaTable.csv",
            "geometry_source": f"{SOURCE_REPOSITORY}/blob/{SOURCE_COMMIT}/web/src/data/plotBoundaries.ts",
            "source_access": {
                "area_table": area_source,
                "plot_boundaries": boundary_source,
            },
            "upstream_original": "kmz/STC_VSD_EVR.kmz",
            "generated_at_utc": generated,
        },
        "features": features,
    }

    context_utm = unary_union(projected_geometries).buffer(args.buffer_m).buffer(0)
    context_web = transform(TO_WEB.transform, context_utm)
    analysis_aoi = {
        "type": "FeatureCollection",
        "name": "samut_songkhram_project_analysis_aoi",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Samut Songkhram 9-plot buffered analysis AOI",
                    "status": "analytical_buffer_not_official_boundary",
                    "project_plot_count": len(features),
                    "plot_ids": PLOT_CODES,
                    "buffer_m": args.buffer_m,
                    "purpose": "satellite context and matched-control search around verified plots",
                    "source_plot_file": args.plots_output,
                    "analysis_crs": "EPSG:32647",
                    "generated_at_utc": generated,
                },
                "geometry": mapping(context_web),
            }
        ],
    }
    write_json(ROOT / args.plots_output, plots)
    write_json(ROOT / args.analysis_output, analysis_aoi)
    print(
        f"wrote {len(features)} plots; official={official_total:.3f} rai "
        f"geometry={geometry_total:.3f} rai; buffer={args.buffer_m:.0f} m"
    )


if __name__ == "__main__":
    main()
