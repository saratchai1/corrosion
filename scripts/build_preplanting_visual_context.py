#!/usr/bin/env python3
"""Build contextual, multispectral web images for the pre-planting slider.

The existing tide-aware analysis rasters are clipped to a multi-part project AOI,
so pixels outside that AOI appear black in a plain RGB preview.  This script
places each selected-scene analysis raster back onto the wider, georeferenced
annual Sentinel-2 context image, draws the project plots, and exports consistent
before/after images for five scientifically relevant views:

* true colour (RGB)
* vegetation false colour (NIR / red / green)
* NDVI
* MNDWI
* SWIR moisture / wet-soil composite (SWIR1 / NIR / red)

The wider background is an annual same-season context composite.  The coloured
analysis window is generated from the exact selected scene listed in the
pre-planting summary.  Therefore the context helps orientation but is not used
as a replacement for the tide-aware WATERLINE evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
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


def colourize(index: np.ndarray, valid: np.ndarray, stops: list[float], colours: list[tuple[int, int, int]]) -> Image.Image:
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


def bounds_from_plots(plots: list[dict[str, Any]], plot_ids: set[str], mapper: Any) -> tuple[float, float, float, float]:
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
    left = max(0, left)
    top = max(0, top)
    right = min(image_width, right)
    bottom = min(image_height, bottom)
    return tuple(int(round(value)) for value in (left, top, right, bottom))


def font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def draw_map_decorations(
    image: Image.Image,
    *,
    plot_lines: list[tuple[str, list[tuple[float, float]], tuple[float, float]]],
    crop: tuple[int, int, int, int],
    source_size: tuple[int, int],
    title: str,
    subtitle: str,
    metres_per_source_pixel: float,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    target_width, target_height = image.size
    crop_left, crop_top, crop_right, crop_bottom = crop
    scale_x = target_width / max(crop_right - crop_left, 1)
    scale_y = target_height / max(crop_bottom - crop_top, 1)

    def local(point: tuple[float, float]) -> tuple[float, float]:
        return (point[0] - crop_left) * scale_x, (point[1] - crop_top) * scale_y

    for plot_id, ring, centroid in plot_lines:
        local_ring = [local(point) for point in ring]
        draw.line(local_ring, fill=(255, 222, 89, 235), width=max(2, round(target_width / 600)), joint="curve")
        x, y = local(centroid)
        if -40 <= x <= target_width + 40 and -30 <= y <= target_height + 30:
            label = plot_id
            label_font = font(max(12, round(target_width / 85)))
            box = draw.textbbox((x, y), label, font=label_font, anchor="mm")
            draw.rounded_rectangle(
                (box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3),
                radius=4,
                fill=(5, 24, 26, 205),
                outline=(255, 222, 89, 210),
                width=1,
            )
            draw.text((x, y), label, font=label_font, fill=(255, 245, 205, 255), anchor="mm")

    panel_w = min(round(target_width * 0.48), 600)
    panel_h = max(70, round(target_height * 0.12))
    draw.rounded_rectangle((18, 18, 18 + panel_w, 18 + panel_h), radius=10, fill=(4, 22, 24, 205), outline=(170, 218, 198, 120), width=1)
    draw.text((34, 30), title, font=font(max(19, round(target_width / 55))), fill=(245, 244, 233, 255))
    draw.text((34, 58), subtitle, font=font(max(12, round(target_width / 90))), fill=(160, 203, 187, 255))

    # North arrow
    arrow_x = target_width - 48
    arrow_y = 42
    draw.polygon([(arrow_x, arrow_y - 18), (arrow_x - 8, arrow_y + 8), (arrow_x + 8, arrow_y + 8)], fill=(245, 244, 233, 235))
    draw.text((arrow_x, arrow_y + 13), "N", font=font(max(13, round(target_width / 85))), fill=(245, 244, 233, 255), anchor="ma")

    # Rounded scale bar.  Use a visually stable 1 km or 2 km length.
    crop_width_source = max(crop_right - crop_left, 1)
    metres_per_target_pixel = metres_per_source_pixel * crop_width_source / target_width
    scale_metres = 2000 if target_width * metres_per_target_pixel > 11000 else 1000
    scale_pixels = max(45, scale_metres / max(metres_per_target_pixel, 1e-6))
    x0 = 32
    y0 = target_height - 34
    draw.line((x0, y0, x0 + scale_pixels, y0), fill=(245, 244, 233, 245), width=4)
    draw.line((x0, y0 - 5, x0, y0 + 5), fill=(245, 244, 233, 245), width=2)
    draw.line((x0 + scale_pixels, y0 - 5, x0 + scale_pixels, y0 + 5), fill=(245, 244, 233, 245), width=2)
    draw.text((x0 + scale_pixels / 2, y0 - 11), f"{scale_metres / 1000:g} km", font=font(max(11, round(target_width / 100))), fill=(245, 244, 233, 255), anchor="ms")


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
        overlay_corners = [mapper(left, top), mapper(right, top), mapper(right, bottom), mapper(left, bottom)]
        overlay_left = min(point[0] for point in overlay_corners)
        overlay_right = max(point[0] for point in overlay_corners)
        overlay_top = min(point[1] for point in overlay_corners)
        overlay_bottom = max(point[1] for point in overlay_corners)
        overlay_box = (
            int(round(overlay_left)),
            int(round(overlay_top)),
            int(round(overlay_right)),
            int(round(overlay_bottom)),
        )
        overlay_width = max(1, overlay_box[2] - overlay_box[0])
        overlay_height = max(1, overlay_box[3] - overlay_box[1])

        plot_lines: list[tuple[str, list[tuple[float, float]], tuple[float, float]]] = []
        for plot in plots:
            rings = geometry_pixel_points(plot["geometry"], mapper)
            if not rings:
                continue
            centroid = mapper(plot["geometry"].centroid.x, plot["geometry"].centroid.y)
            for ring in rings:
                plot_lines.append((plot["plot_id"], ring, centroid))

        scene_visuals[year] = {}
        for view_name, view_info in VIEWS.items():
            crop = expand_to_aspect(
                bounds_from_plots(plots, set(view_info["plot_ids"]), mapper),
                image_width=context_width,
                image_height=context_height,
                margin_fraction=float(view_info["margin_fraction"]),
            )
            scene_visuals[year][view_name] = {}
            for mode_name, mode_info in MODES.items():
                if mode_name == "rgb":
                    base = context.copy()
                else:
                    base = ImageEnhance.Color(context).enhance(0.30)
                    base = ImageEnhance.Brightness(base).enhance(0.48)
                overlay = rendered[mode_name].resize((overlay_width, overlay_height), Image.Resampling.BILINEAR)
                base_rgba = base.convert("RGBA")
                base_rgba.alpha_composite(overlay, dest=(overlay_box[0], overlay_box[1]))
                draw = ImageDraw.Draw(base_rgba, "RGBA")
                draw.rounded_rectangle(
                    overlay_box,
                    radius=8,
                    outline=(255, 222, 89, 220),
                    width=max(2, round(context_width / 350)),
                )
                cropped = base_rgba.crop(crop).convert("RGB").resize(
                    (args.target_width, args.target_height),
                    Image.Resampling.LANCZOS,
                )
                metres_per_source_pixel = float(abs(grid["transform"].a)) * (grid["width"] / max(overlay_width, 1))
                filtered_lines = [line for line in plot_lines if line[0] in set(view_info["plot_ids"])]
                draw_map_decorations(
                    cropped,
                    plot_lines=filtered_lines,
                    crop=crop,
                    source_size=(context_width, context_height),
                    title=f"{year} · {mode_info['label_th']}",
                    subtitle=f"{view_info['label_th']} · กรอบสีเหลืองคือพื้นที่ภาพที่ใช้วิเคราะห์",
                    metres_per_source_pixel=metres_per_source_pixel,
                )
                relative = Path(view_name) / mode_name / f"{year}.webp"
                for destination_root in (output_dir, web_output_dir):
                    destination = destination_root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    cropped.save(destination, "WEBP", quality=82, method=6)
                public_path = f"data/project_preplanting_history/visuals/{relative.as_posix()}"
                scene_visuals[year][view_name][mode_name] = public_path
            view_manifest.setdefault(view_name, {
                "label_th": view_info["label_th"],
                "description_th": view_info["description_th"],
            })

    for scene in summary["scene_selection"]["display_scenes"]:
        year = int(scene["year"])
        scene["visuals"] = scene_visuals[year]
        scene["context_image"] = f"data/imagery/{year}.webp"

    summary["visualization"] = {
        "default_view": "focus",
        "default_mode": "rgb",
        "views": view_manifest,
        "modes": MODES,
        "image_count": len(scene_visuals) * len(VIEWS) * len(MODES),
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
