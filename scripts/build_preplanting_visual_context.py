#!/usr/bin/env python3
"""Build clean contextual multispectral imagery plus web SVG map overlays.

The selected Sentinel-2 analysis rasters are composited onto the wider annual
same-season Sentinel-2 context so the slider has geographic context instead of
black NoData.  Raster outputs intentionally contain *no* baked text, plot
labels, plot boundaries, analysis-window outlines, north arrows, or scale bars.
Those presentation elements belong to the web layer.

Five spectral views are exported for every selected year:

* true colour RGB
* vegetation false colour NIR / Red / Green
* NDVI
* MNDWI
* SWIR / NIR / Red moisture-wet-soil composite

For each year and map view, a transparent SVG is exported separately.  The SVG
contains the project plot boundaries/IDs and the exact selected-scene analysis
window.  The React app overlays those SVGs at runtime, so fonts and boundaries
remain sharp, accessible, switchable, and independent from the satellite
pixels.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from scripts.build_coastal_change_mvp import build_composite

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = Path("data/processed/project_preplanting_history/summary.json")
DEFAULT_WEB_SUMMARY = Path("web/public/data/project_preplanting_history/summary.json")
DEFAULT_CATALOG = Path("data/catalog/project_samut_songkhram_sentinel2_history_2017_2026.csv")
DEFAULT_IMAGERY_INDEX = Path("web/public/data/imagery_index.json")
DEFAULT_CONTEXT_DIR = Path("web/public/data/imagery")
DEFAULT_PLOTS = Path("data/aoi/samut_songkhram_project_plots.geojson")
DEFAULT_OUTPUT = Path("data/processed/project_preplanting_history/visuals")
DEFAULT_WEB_OUTPUT = Path("web/public/data/project_preplanting_history/visuals")

MODES: dict[str, dict[str, str]] = {
    "rgb": {
        "label_th": "สีจริง RGB",
        "short_th": "สีจริง",
        "description_th": "สีใกล้เคียงที่ตาเห็น ใช้ดูตำแหน่ง เมือง คลอง และรูปทรงชายฝั่ง",
        "evidence_role": "ORIENTATION",
    },
    "false_vegetation": {
        "label_th": "สีเทียมพืช NIR–R–G",
        "short_th": "พืชสีแดง",
        "description_th": "พืชแข็งแรงสะท้อน NIR สูงและปรากฏเป็นสีแดง เหมาะกับการดูขอบพืชชายฝั่ง",
        "evidence_role": "MANGROVE_EDGE_SUPPORT",
    },
    "ndvi": {
        "label_th": "NDVI ความเขียว",
        "short_th": "NDVI",
        "description_th": "น้ำและพื้นเปลือยเป็นสีน้ำเงิน–น้ำตาล พืชหนาแน่นเป็นสีเขียวเข้ม",
        "evidence_role": "MANGROVE_EDGE_PRIMARY_SCREENING",
    },
    "mndwi": {
        "label_th": "MNDWI น้ำ–แผ่นดิน",
        "short_th": "MNDWI",
        "description_th": "น้ำที่ตอบสนองสูงเป็นสีน้ำเงิน ใช้สนับสนุนการสกัดขอบน้ำจาก Green และ SWIR1",
        "evidence_role": "WATERLINE_PRIMARY_SPECTRAL_VIEW",
    },
    "swir": {
        "label_th": "SWIR–NIR–Red ความชื้น",
        "short_th": "SWIR",
        "description_th": "ช่วยแยกน้ำ พื้นชื้น ดินเปิด และพืช โดยไม่ตีความเป็นปริมาณตะกอน",
        "evidence_role": "MOISTURE_AND_WET_SOIL_SUPPORT",
    },
}

VIEWS: dict[str, dict[str, Any]] = {
    "focus": {
        "label_th": "โฟกัส 91–98 STC",
        "description_th": "ขยายแนวชายฝั่งด้านหน้าแปลงที่ใช้คำนวณ 294 transects",
        "plot_ids": [f"{value}-STC" for value in range(91, 99)],
        "margin_fraction": 0.42,
    },
    "full": {
        "label_th": "เต็มพื้นที่ 9 แปลง",
        "description_th": "แสดงตำแหน่ง 87-VSD เทียบกับกลุ่มแปลงชายฝั่ง 91–98 STC",
        "plot_ids": [f"{value}-STC" for value in range(91, 99)] + ["87-VSD"],
        "margin_fraction": 0.22,
    },
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_catalog(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return {row["scene_id"]: row for row in rows if row.get("scene_id")}


def finite_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    output = np.full_like(numerator, np.nan, dtype="float32")
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (np.abs(denominator) > 1e-6)
    output[valid] = numerator[valid] / denominator[valid]
    return output


def stretch_channel(values: np.ndarray, valid: np.ndarray, gamma: float = 0.85) -> np.ndarray:
    sample = values[valid & np.isfinite(values)]
    low, high = np.percentile(sample, [2, 98]) if sample.size else (0.0, 1.0)
    scaled = np.clip((values - low) / max(float(high - low), 1e-6), 0.0, 1.0)
    return np.nan_to_num(scaled ** gamma * 255.0).astype("uint8")


def rgba_composite(channels: list[np.ndarray], valid: np.ndarray, gamma: float = 0.85) -> Image.Image:
    output = np.zeros((valid.shape[0], valid.shape[1], 4), dtype="uint8")
    for index, channel in enumerate(channels[:3]):
        output[:, :, index] = stretch_channel(channel, valid, gamma=gamma)
    output[:, :, 3] = np.where(valid, 245, 0).astype("uint8")
    return Image.fromarray(output, mode="RGBA")


def colourize(
    index: np.ndarray,
    valid: np.ndarray,
    stops: list[float],
    colours: list[tuple[int, int, int]],
) -> Image.Image:
    clipped = np.clip(index, stops[0], stops[-1])
    output = np.zeros((index.shape[0], index.shape[1], 4), dtype="uint8")
    for channel in range(3):
        output[:, :, channel] = np.nan_to_num(
            np.interp(clipped, stops, [colour[channel] for colour in colours])
        ).astype("uint8")
    output[:, :, 3] = np.where(valid & np.isfinite(index), 242, 0).astype("uint8")
    return Image.fromarray(output, mode="RGBA")


def render_modes(composite: np.ndarray, valid: np.ndarray) -> dict[str, Image.Image]:
    blue, green, red, nir, swir1 = composite
    ndvi = finite_ratio(nir - red, nir + red)
    mndwi = finite_ratio(green - swir1, green + swir1)
    return {
        "rgb": rgba_composite([red, green, blue], valid),
        "false_vegetation": rgba_composite([nir, red, green], valid, gamma=0.78),
        "ndvi": colourize(
            ndvi,
            valid,
            [-1.0, -0.2, 0.0, 0.2, 0.4, 0.65, 1.0],
            [
                (28, 62, 115),
                (70, 105, 145),
                (166, 140, 101),
                (218, 196, 112),
                (133, 181, 93),
                (47, 130, 73),
                (8, 69, 42),
            ],
        ),
        "mndwi": colourize(
            mndwi,
            valid,
            [-1.0, -0.35, 0.0, 0.15, 0.35, 0.65, 1.0],
            [
                (108, 68, 39),
                (179, 135, 85),
                (202, 199, 177),
                (151, 211, 214),
                (71, 166, 202),
                (24, 95, 171),
                (8, 45, 104),
            ],
        ),
        "swir": rgba_composite([swir1, nir, red], valid, gamma=0.78),
    }


def image_coordinates_by_year(path: Path) -> dict[int, dict[str, Any]]:
    value = read_json(path)
    return {int(item["targetYear"]): item for item in value["epochs"]}


def global_pixel_mapper(corners_wgs84: list[list[float]], width: int, height: int, crs: Any):
    to_grid = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    tl, tr, _br, bl = [np.array(to_grid.transform(*point), dtype="float64") for point in corners_wgs84]
    matrix = np.column_stack((tr - tl, bl - tl))
    inverse = np.linalg.inv(matrix)

    def mapper(x: float, y: float) -> tuple[float, float]:
        u, v = inverse @ (np.array([x, y], dtype="float64") - tl)
        return float(u * width), float(v * height)

    return mapper


def geometry_pixel_points(geometry: Any, mapper: Any) -> list[list[tuple[float, float]]]:
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(getattr(geometry, "geoms", []))
    output: list[list[tuple[float, float]]] = []
    for polygon in polygons:
        if polygon.geom_type != "Polygon":
            continue
        output.append([mapper(float(x), float(y)) for x, y in polygon.exterior.coords])
    return output


def load_plots(path: Path, crs: Any) -> list[dict[str, Any]]:
    value = read_json(path)
    to_grid = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    plots: list[dict[str, Any]] = []
    for feature in value["features"]:
        props = feature.get("properties", {})
        plot_id = props.get("plot_id") or props.get("id") or props.get("name")
        if not plot_id:
            continue
        geometry = transform(to_grid.transform, shape(feature["geometry"]))
        plots.append({"plot_id": str(plot_id), "geometry": geometry})
    return plots


def bounds_from_plots(
    plots: list[dict[str, Any]],
    plot_ids: set[str],
    mapper: Any,
) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    for plot in plots:
        if plot["plot_id"] not in plot_ids:
            continue
        for ring in geometry_pixel_points(plot["geometry"], mapper):
            points.extend(ring)
    if not points:
        raise ValueError(f"no plot geometry for {sorted(plot_ids)}")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def expand_to_aspect(
    bounds: tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
    margin_fraction: float,
    aspect: float = 16 / 10,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds
    width = max(right - left, 1.0)
    height = max(bottom - top, 1.0)
    left -= width * margin_fraction
    right += width * margin_fraction
    top -= height * margin_fraction
    bottom += height * margin_fraction
    width = right - left
    height = bottom - top
    centre_x = (left + right) / 2
    centre_y = (top + bottom) / 2
    if width / height < aspect:
        width = height * aspect
    else:
        height = width / aspect
    left, right = centre_x - width / 2, centre_x + width / 2
    top, bottom = centre_y - height / 2, centre_y + height / 2

    if left < 0:
        right -= left
        left = 0
    if right > image_width:
        left -= right - image_width
        right = image_width
    if top < 0:
        bottom -= top
        top = 0
    if bottom > image_height:
        top -= bottom - image_height
        bottom = image_height
    return (
        int(round(max(0, left))),
        int(round(max(0, top))),
        int(round(min(image_width, right))),
        int(round(min(image_height, bottom))),
    )


def local_point(
    point: tuple[float, float],
    crop: tuple[int, int, int, int],
    target_width: int,
    target_height: int,
) -> tuple[float, float]:
    left, top, right, bottom = crop
    scale_x = target_width / max(right - left, 1)
    scale_y = target_height / max(bottom - top, 1)
    return (
        round((point[0] - left) * scale_x, 2),
        round((point[1] - top) * scale_y, 2),
    )


def build_web_overlay_svg(
    *,
    plots: list[dict[str, Any]],
    plot_ids: set[str],
    mapper: Any,
    crop: tuple[int, int, int, int],
    overlay_box: tuple[int, int, int, int],
    target_width: int,
    target_height: int,
) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {target_width} {target_height}" '
            'preserveAspectRatio="none" aria-hidden="true">'
        ),
        '<g fill="none" stroke-linejoin="round" stroke-linecap="round">',
    ]

    analysis_tl = local_point((overlay_box[0], overlay_box[1]), crop, target_width, target_height)
    analysis_br = local_point((overlay_box[2], overlay_box[3]), crop, target_width, target_height)
    parts.append(
        (
            f'<rect x="{analysis_tl[0]:.2f}" y="{analysis_tl[1]:.2f}" '
            f'width="{analysis_br[0] - analysis_tl[0]:.2f}" '
            f'height="{analysis_br[1] - analysis_tl[1]:.2f}" '
            'stroke="#74ead6" stroke-width="2" stroke-dasharray="10 7" '
            'vector-effect="non-scaling-stroke" opacity="0.9"/>'
        )
    )

    for plot in plots:
        plot_id = plot["plot_id"]
        if plot_id not in plot_ids:
            continue
        rings = geometry_pixel_points(plot["geometry"], mapper)
        for ring in rings:
            local_ring = [local_point(point, crop, target_width, target_height) for point in ring]
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in local_ring)
            parts.append(
                f'<polyline points="{points}" stroke="#ffe45e" stroke-width="3" '
                'vector-effect="non-scaling-stroke" opacity="0.98"/>'
            )
        centroid = local_point(
            mapper(plot["geometry"].centroid.x, plot["geometry"].centroid.y),
            crop,
            target_width,
            target_height,
        )
        parts.append(
            (
                f'<text x="{centroid[0]:.2f}" y="{centroid[1]:.2f}" '
                'fill="#fff4ad" stroke="#061719" stroke-width="5" '
                'paint-order="stroke fill" text-anchor="middle" dominant-baseline="central" '
                'font-family="Noto Sans Thai, IBM Plex Sans Thai, Arial, sans-serif" '
                f'font-size="18" font-weight="700">{plot_id}</text>'
            )
        )

    parts.extend(['</g>', '</svg>'])
    return "\n".join(parts) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--web-summary", type=Path, default=DEFAULT_WEB_SUMMARY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--imagery-index", type=Path, default=DEFAULT_IMAGERY_INDEX)
    parser.add_argument("--context-dir", type=Path, default=DEFAULT_CONTEXT_DIR)
    parser.add_argument("--plots", type=Path, default=DEFAULT_PLOTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output", type=Path, default=DEFAULT_WEB_OUTPUT)
    parser.add_argument("--target-width", type=int, default=1400)
    parser.add_argument("--target-height", type=int, default=875)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary_path = ROOT / args.summary
    web_summary_path = ROOT / args.web_summary
    summary = read_json(summary_path)
    catalog = load_catalog(ROOT / args.catalog)
    imagery_index = image_coordinates_by_year(ROOT / args.imagery_index)
    output_dir = ROOT / args.output
    web_output_dir = ROOT / args.web_output
    output_dir.mkdir(parents=True, exist_ok=True)
    web_output_dir.mkdir(parents=True, exist_ok=True)

    scene_visuals: dict[int, dict[str, dict[str, str]]] = {}
    scene_overlays: dict[int, dict[str, str]] = {}
    view_manifest: dict[str, Any] = {}

    for scene in summary["scene_selection"]["display_scenes"]:
        year = int(scene["year"])
        row = catalog.get(scene["scene_id"])
        if row is None:
            raise KeyError(f"selected scene missing from catalog: {scene['scene_id']}")
        composite, valid_count, grid = build_composite([row], "sentinel2")
        valid = valid_count > 0
        if not np.any(valid):
            raise RuntimeError(f"selected scene has no valid pixels: {scene['scene_id']}")
        rendered = render_modes(composite, valid)

        context_path = ROOT / args.context_dir / f"{year}.webp"
        if not context_path.exists():
            raise FileNotFoundError(f"annual context image missing: {context_path}")
        context = Image.open(context_path).convert("RGB")
        context_width, context_height = context.size
        index_item = imagery_index.get(year)
        if index_item is None:
            raise KeyError(f"imagery index has no {year}")
        mapper = global_pixel_mapper(
            index_item["imageCoordinates"],
            context_width,
            context_height,
            grid["crs"],
        )
        plots = load_plots(ROOT / args.plots, grid["crs"])

        left, bottom, right, top = grid["bounds"]
        overlay_corners = [
            mapper(left, top),
            mapper(right, top),
            mapper(right, bottom),
            mapper(left, bottom),
        ]
        overlay_box = (
            int(round(min(point[0] for point in overlay_corners))),
            int(round(min(point[1] for point in overlay_corners))),
            int(round(max(point[0] for point in overlay_corners))),
            int(round(max(point[1] for point in overlay_corners))),
        )
        overlay_width = max(1, overlay_box[2] - overlay_box[0])
        overlay_height = max(1, overlay_box[3] - overlay_box[1])

        scene_visuals[year] = {}
        scene_overlays[year] = {}
        for view_name, view_info in VIEWS.items():
            plot_ids = set(view_info["plot_ids"])
            crop = expand_to_aspect(
                bounds_from_plots(plots, plot_ids, mapper),
                image_width=context_width,
                image_height=context_height,
                margin_fraction=float(view_info["margin_fraction"]),
            )
            scene_visuals[year][view_name] = {}

            overlay_relative = Path(view_name) / "overlay" / f"{year}.svg"
            overlay_svg = build_web_overlay_svg(
                plots=plots,
                plot_ids=plot_ids,
                mapper=mapper,
                crop=crop,
                overlay_box=overlay_box,
                target_width=args.target_width,
                target_height=args.target_height,
            )
            for destination_root in (output_dir, web_output_dir):
                destination = destination_root / overlay_relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(overlay_svg, encoding="utf-8")
            scene_overlays[year][view_name] = (
                f"data/project_preplanting_history/visuals/{overlay_relative.as_posix()}"
            )

            for mode_name in MODES:
                if mode_name == "rgb":
                    base = context.copy()
                else:
                    base = ImageEnhance.Color(context).enhance(0.30)
                    base = ImageEnhance.Brightness(base).enhance(0.48)
                overlay = rendered[mode_name].resize(
                    (overlay_width, overlay_height),
                    Image.Resampling.BILINEAR,
                )
                base_rgba = base.convert("RGBA")
                base_rgba.alpha_composite(overlay, dest=(overlay_box[0], overlay_box[1]))
                cropped = base_rgba.crop(crop).convert("RGB").resize(
                    (args.target_width, args.target_height),
                    Image.Resampling.LANCZOS,
                )
                relative = Path(view_name) / mode_name / f"{year}.webp"
                for destination_root in (output_dir, web_output_dir):
                    destination = destination_root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    cropped.save(destination, "WEBP", quality=82, method=6)
                scene_visuals[year][view_name][mode_name] = (
                    f"data/project_preplanting_history/visuals/{relative.as_posix()}"
                )

            view_manifest.setdefault(
                view_name,
                {
                    "label_th": view_info["label_th"],
                    "description_th": view_info["description_th"],
                },
            )

    for scene in summary["scene_selection"]["display_scenes"]:
        year = int(scene["year"])
        scene["visuals"] = scene_visuals[year]
        scene["plot_overlays"] = scene_overlays[year]
        scene["context_image"] = f"data/imagery/{year}.webp"

    summary["visualization"] = {
        "default_view": "focus",
        "default_mode": "rgb",
        "views": view_manifest,
        "modes": MODES,
        "image_count": len(scene_visuals) * len(VIEWS) * len(MODES),
        "overlay_count": len(scene_overlays) * len(VIEWS),
        "raster_presentation": "CLEAN_NO_BAKED_LABELS_OR_BOUNDARIES",
        "map_overlay_model": "WEB_SVG_LAYER",
        "background_source": (
            "Annual January-April Sentinel-2 context composite used only for geographic orientation."
        ),
        "analysis_overlay_source": (
            "Exact selected Sentinel-2 scene used by the pre-planting evidence catalog; transparent outside valid project-AOI pixels."
        ),
        "scientific_guard_th": (
            "สี RGB/False colour/NDVI/MNDWI/SWIR ช่วยอ่านรูปแบบเชิงสเปกตรัม แต่ไม่เพิ่มระดับข้อสรุปเชิงเหตุ–ผล และไม่ใช่ข้อมูลตะกอนหรือคลื่น"
        ),
    }
    write_json(summary_path, summary)
    write_json(web_summary_path, summary)
    write_json(output_dir / "manifest.json", summary["visualization"])
    write_json(web_output_dir / "manifest.json", summary["visualization"])
    print(json.dumps(summary["visualization"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
