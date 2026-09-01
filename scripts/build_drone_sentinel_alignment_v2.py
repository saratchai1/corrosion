#!/usr/bin/env python3
"""Build plot-by-plot drone/Sentinel-2 spatial comparison products.

Sentinel-2 RGB is reprojected onto the exact geographic extent and display
canvas of each drone orthomosaic preview. Project boundaries and the accepted
2025 satellite WATERLINE/MANGROVE_EDGE_PROXY are emitted as a separate SVG so
the browser renders vector evidence rather than baking it into the raster.

This is a spatial baseline cross-check only. The drone folder date is not yet a
verified flight date, and a single drone epoch cannot yield an erosion rate.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject
from shapely.geometry import box, shape
from shapely.ops import transform as shapely_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRONE = ROOT / "data/processed/samut_songkhram_drone"
DEFAULT_CATALOG = ROOT / "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
DEFAULT_TIDE_SUMMARY = ROOT / "data/processed/project_tide_aware/summary.json"
DEFAULT_PLOTS = ROOT / "data/aoi/samut_songkhram_project_plots.geojson"
DEFAULT_WATERLINE = ROOT / "data/processed/project_preplanting_history/waterline/2025.geojson"
DEFAULT_MANGROVE_EDGE = ROOT / "data/processed/project_preplanting_history/mangrove_proxy/2025_seaward_edge.geojson"
DEFAULT_WEB = ROOT / "web/public/data/project_drone_orthomosaic"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drone-dir", type=Path, default=DEFAULT_DRONE)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--tide-summary", type=Path, default=DEFAULT_TIDE_SUMMARY)
    parser.add_argument("--plots", type=Path, default=DEFAULT_PLOTS)
    parser.add_argument("--waterline", type=Path, default=DEFAULT_WATERLINE)
    parser.add_argument("--mangrove-edge", type=Path, default=DEFAULT_MANGROVE_EDGE)
    parser.add_argument("--web-output", type=Path, default=DEFAULT_WEB)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def transform_geom(geom: Any, source: str | CRS, target: str | CRS) -> Any:
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def selected_2025_scene(tide_summary: dict[str, Any]) -> str:
    for row in tide_summary["waterline_scene_selection"]["selected_scenes"]:
        if int(row["year"]) == 2025:
            return str(row["scene_id"])
    raise KeyError("2025 selected WATERLINE scene not found")


def band_paths(row: dict[str, str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in row["local_path"].split(";"):
        path = Path(raw)
        result[path.name.split("_")[0].upper()] = ROOT / path
    return result


def stretch_band(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    values = data[valid]
    output = np.zeros(data.shape, dtype=np.uint8)
    if values.size == 0:
        return output
    low, high = np.percentile(values, [2.0, 98.0])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = float(values.min()), float(values.max())
    if high <= low:
        return output
    scaled = (data.astype(np.float32) - float(low)) / (float(high) - float(low))
    output[:] = np.clip(scaled * 255.0, 0, 255).astype(np.uint8)
    return output


def build_sentinel_canvas(
    paths: dict[str, Path],
    bounds: list[float],
    width: int,
    height: int,
    output: Path,
) -> dict[str, Any]:
    left, bottom, right, top = map(float, bounds)
    destination_transform = from_bounds(left, bottom, right, top, width, height)
    rgb = np.zeros((3, height, width), dtype=np.float32)
    valid = np.ones((height, width), dtype=bool)

    for target_index, band in enumerate(("B4", "B3", "B2")):
        source_path = paths.get(band)
        if source_path is None or not source_path.exists():
            raise FileNotFoundError(f"missing downloaded {band}: {source_path}")
        with rasterio.open(source_path) as source:
            destination = np.zeros((height, width), dtype=np.float32)
            reproject(
                source=source.read(1),
                destination=destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=destination_transform,
                dst_crs="EPSG:32647",
                dst_nodata=0,
                resampling=Resampling.bilinear,
            )
            rgb[target_index] = destination
            valid &= np.isfinite(destination) & (destination > 0)

    rendered = np.zeros((height, width, 4), dtype=np.uint8)
    for index in range(3):
        rendered[..., index] = stretch_band(rgb[index], valid)
    rendered[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rendered, mode="RGBA").save(output, "WEBP", quality=84, method=6)
    return {
        "valid_fraction": round(float(valid.mean()), 6),
        "width": width,
        "height": height,
    }


def collection_union(path: Path) -> Any:
    collection = read_json(path)
    geometries = [
        shape(feature["geometry"]).buffer(0)
        for feature in collection.get("features", [])
        if feature.get("geometry")
    ]
    return unary_union(geometries) if geometries else unary_union([])


def svg_path_for_geometry(geom: Any, bounds: list[float], width: int, height: int) -> str:
    left, bottom, right, top = map(float, bounds)
    dx = max(right - left, 1e-9)
    dy = max(top - bottom, 1e-9)

    def xy(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return ((x - left) / dx * width, (top - y) / dy * height)

    parts: list[str] = []

    def line_path(coords: Iterable[tuple[float, float]], close: bool = False) -> str:
        points = [xy((float(point[0]), float(point[1]))) for point in coords]
        if not points:
            return ""
        commands = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
        commands.extend(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
        if close:
            commands.append("Z")
        return " ".join(commands)

    def visit(item: Any) -> None:
        if item.is_empty:
            return
        if item.geom_type == "Polygon":
            parts.append(line_path(item.exterior.coords, close=True))
            for ring in item.interiors:
                parts.append(line_path(ring.coords, close=True))
        elif item.geom_type in {"LineString", "LinearRing"}:
            parts.append(line_path(item.coords))
        elif item.geom_type.startswith("Multi") or item.geom_type == "GeometryCollection":
            for child in item.geoms:
                visit(child)

    visit(geom)
    return " ".join(part for part in parts if part)


def write_overlay_svg(
    output: Path,
    *,
    plot: Any,
    waterline: Any,
    mangrove_edge: Any,
    bounds: list[float],
    width: int,
    height: int,
    plot_id: str,
) -> None:
    crop = box(*map(float, bounds))
    plot_crop = plot.intersection(crop)
    water_crop = waterline.intersection(crop)
    mangrove_crop = mangrove_edge.intersection(crop)
    plot_path = svg_path_for_geometry(plot_crop, bounds, width, height)
    water_path = svg_path_for_geometry(water_crop, bounds, width, height)
    mangrove_path = svg_path_for_geometry(mangrove_crop, bounds, width, height)
    centroid = plot_crop.centroid if not plot_crop.is_empty else crop.centroid
    left, bottom, right, top = map(float, bounds)
    cx = (centroid.x - left) / max(right - left, 1e-9) * width
    cy = (top - centroid.y) / max(top - bottom, 1e-9) * height

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none">
  <g fill="none">
    <path d="{plot_path}" stroke="#ffe35a" stroke-width="3" fill="#ffe35a" fill-opacity="0.05" vector-effect="non-scaling-stroke"/>
    <path d="{water_path}" stroke="#5ee7ff" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
    <path d="{mangrove_path}" stroke="#ff74d4" stroke-width="2.5" stroke-dasharray="8 5" vector-effect="non-scaling-stroke"/>
  </g>
  <g font-family="system-ui, sans-serif" font-size="20" font-weight="700" text-anchor="middle">
    <text x="{cx:.2f}" y="{cy:.2f}" fill="#071b1d" stroke="#fff3a0" stroke-width="5" paint-order="stroke">{plot_id}</text>
    <text x="{cx:.2f}" y="{cy:.2f}" fill="#fff3a0">{plot_id}</text>
  </g>
</svg>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def main() -> int:
    args = parse_args()
    drone_dir = resolve(args.drone_dir)
    web_dir = resolve(args.web_output)
    tide_summary = read_json(resolve(args.tide_summary))
    scene_id = selected_2025_scene(tide_summary)
    catalog_rows = read_csv(resolve(args.catalog))
    scene_row = next(row for row in catalog_rows if row["scene_id"] == scene_id)
    paths = band_paths(scene_row)

    plots_collection = read_json(resolve(args.plots))
    plots = {
        feature["properties"]["plot_id"]: transform_geom(
            shape(feature["geometry"]), "EPSG:4326", "EPSG:32647"
        )
        for feature in plots_collection["features"]
    }
    waterline = transform_geom(
        collection_union(resolve(args.waterline)), "EPSG:4326", "EPSG:32647"
    )
    mangrove_edge = transform_geom(
        collection_union(resolve(args.mangrove_edge)), "EPSG:4326", "EPSG:32647"
    )

    summary = read_json(drone_dir / "summary.json")
    raw_by_plot = {
        path.stem: read_json(path)
        for path in sorted((drone_dir / "raw").glob("*.json"))
    }
    provisional_date = date.fromisoformat(summary["date_evidence"]["folder_labels"][0])
    satellite_date = date.fromisoformat(scene_row["acquisition_datetime_bangkok"][:10])
    provisional_gap = (satellite_date - provisional_date).days

    alignments: list[dict[str, Any]] = []
    for plot_row in summary["plots"]:
        plot_id = plot_row["plot_id"]
        raw = raw_by_plot[plot_id]
        bounds = raw["raster"]["bounds_native"]
        preview = raw["preview"]
        width = int(preview["preview_width"])
        height = int(preview["preview_height"])
        satellite_output = web_dir / "sentinel2_2025_aligned" / f"{plot_id}.webp"
        rendered = build_sentinel_canvas(paths, bounds, width, height, satellite_output)
        overlay_output = web_dir / "alignment_overlay" / f"{plot_id}.svg"
        write_overlay_svg(
            overlay_output,
            plot=plots[plot_id],
            waterline=waterline,
            mangrove_edge=mangrove_edge,
            bounds=bounds,
            width=width,
            height=height,
            plot_id=plot_id,
        )
        drone_gsd_m = float(raw["raster"]["pixel_size_x"])
        alignments.append(
            {
                "plot_id": plot_id,
                "drone_preview": f"data/project_drone_orthomosaic/previews/{plot_id}.webp",
                "sentinel2_preview": f"data/project_drone_orthomosaic/sentinel2_2025_aligned/{plot_id}.webp",
                "overlay_svg": f"data/project_drone_orthomosaic/alignment_overlay/{plot_id}.svg",
                "drone_gsd_cm": raw["raster"]["mean_gsd_cm"],
                "sentinel2_native_resolution_m": 10,
                "linear_resolution_ratio_sentinel_to_drone": round(10.0 / drone_gsd_m, 1),
                "drone_extent_epsg32647": bounds,
                "canvas_width": width,
                "canvas_height": height,
                "sentinel2_valid_fraction_on_drone_extent": rendered["valid_fraction"],
                "imagery_coverage_status": raw["qa"]["imagery_coverage_status"],
            }
        )

    alignment_summary = {
        "title": "Drone orthomosaic vs Sentinel-2 spatial alignment",
        "purpose": "HIGH_RESOLUTION_BASELINE_CROSS_CHECK",
        "plot_count": len(alignments),
        "drone_source_date": provisional_date.isoformat(),
        "drone_source_date_status": summary["date_evidence"]["status"],
        "sentinel2_scene_id": scene_id,
        "sentinel2_scene_date": satellite_date.isoformat(),
        "sentinel2_tide_level_m_msl": float(scene_row["tide_level"]),
        "provisional_day_gap": provisional_gap,
        "overlay_layers": {
            "plot_boundary": "yellow solid",
            "sentinel2_2025_waterline": "cyan solid",
            "sentinel2_2025_mangrove_edge_proxy": "magenta dashed",
        },
        "scientific_guard": (
            f"The drone folder date is not verified as acquisition time. Sentinel-2 "
            f"is {provisional_gap} days after that provisional date. This alignment "
            "is for spatial/geometric validation only, not a same-day before/after "
            "comparison or a drone-derived erosion-rate estimate."
        ),
        "plots": alignments,
    }
    (drone_dir / "sentinel_alignment.json").write_text(
        json.dumps(alignment_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (web_dir / "sentinel_alignment.json").write_text(
        json.dumps(alignment_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary["sentinel2_alignment"] = alignment_summary
    for path in (drone_dir / "summary.json", web_dir / "summary.json"):
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(alignment_summary, ensure_ascii=False, indent=2))
    if len(alignments) != 9:
        raise SystemExit(f"expected 9 aligned plots, found {len(alignments)}")
    if any(float(row["sentinel2_valid_fraction_on_drone_extent"]) < 0.95 for row in alignments):
        raise SystemExit("one or more drone extents have <95% valid Sentinel-2 RGB coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
