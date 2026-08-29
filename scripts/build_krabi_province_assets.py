#!/usr/bin/env python3
"""Build static, validated province-wide Krabi satellite imagery assets.

The purpose of this script is to eliminate fragile live COG rendering in the
public dashboard. It downloads annual Sentinel-2 cloudless mosaics, verifies
that each response is a real and non-blank image, proves that the comparison
images are not identical, and writes fixed-size assets that a simple HTML
before/after slider can display without any map-tile dependency.

The annual mosaics are visual context only. They are not tide-matched
shorelines and must not be interpreted as engineering erosion rates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps, ImageStat
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

PROVINCES_URL = (
    "https://raw.githubusercontent.com/chingchai/OpenGISData-Thailand/"
    "refs/heads/master/provinces.geojson"
)
EOX_WMS_URL = "https://tiles.maps.eox.at/wms"
YEARS = (2018, 2020, 2022, 2024)
WIDTH = 1900
USER_AGENT = "corrosion-krabi-province-builder/1.0"

# Approximate navigation markers only. These are deliberately points rather
# than polygons because official DMCR littoral-cell boundary geometries are
# not included in the repository. The source names A13-A19 come from DMCR.
SECTOR_MARKERS = [
    {"code": "A13", "name_th": "อ่าวพังงา", "lon": 98.78, "lat": 8.38},
    {"code": "A14", "name_th": "อ่าวลึก", "lon": 98.88, "lat": 8.27},
    {"code": "A15", "name_th": "ท่าเลน", "lon": 98.76, "lat": 8.13},
    {"code": "A16", "name_th": "อ่าวนาง", "lon": 98.80, "lat": 8.03},
    {"code": "A17", "name_th": "ปากน้ำกระบี่", "lon": 98.91, "lat": 8.00},
    {"code": "A18", "name_th": "คลองท่อม", "lon": 99.04, "lat": 7.84},
    {"code": "A19", "name_th": "คลองพน", "lon": 99.13, "lat": 7.55},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def get_json(url: str) -> dict:
    response = requests.get(
        url,
        timeout=180,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def find_krabi_boundary(collection: dict):
    for feature in collection.get("features", []):
        props = feature.get("properties", {})
        if str(props.get("pro_code")) == "81" or props.get("pro_en") == "Krabi":
            geom = shape(feature["geometry"])
            if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError("Krabi province geometry is missing or not polygonal")
            if not geom.is_valid:
                geom = geom.buffer(0)
            return feature, geom
    raise ValueError("Krabi province was not found in the province dataset")


def coastal_display_bbox(geom) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = geom.bounds
    # Include extra Andaman Sea to the west and a smaller inland margin.
    return (minx - 0.18, miny - 0.06, maxx + 0.05, maxy + 0.06)


def image_height(bbox: tuple[float, float, float, float]) -> int:
    minx, miny, maxx, maxy = bbox
    mid_lat = (miny + maxy) / 2
    lon_span_ground = (maxx - minx) * max(math.cos(math.radians(mid_lat)), 0.2)
    lat_span = maxy - miny
    return max(1150, min(2350, round(WIDTH * lat_span / lon_span_ground)))


def download_wms(year: int, bbox, width: int, height: int) -> tuple[Image.Image, dict]:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": f"s2cloudless-{year}",
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": ",".join(f"{value:.8f}" for value in bbox),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/jpeg",
        "TRANSPARENT": "false",
        "BGCOLOR": "0x000000",
    }
    response = requests.get(
        EOX_WMS_URL,
        params=params,
        timeout=240,
        headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/*"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "image" not in content_type.lower():
        snippet = response.content[:300].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"EOX {year} returned {content_type!r}, not an image: {snippet}"
        )
    from io import BytesIO

    image = Image.open(BytesIO(response.content)).convert("RGB")
    if image.size != (width, height):
        raise RuntimeError(
            f"EOX {year} image has unexpected size {image.size}; expected {(width, height)}"
        )
    stats = ImageStat.Stat(image.resize((256, 256)))
    mean = [round(value, 3) for value in stats.mean]
    stddev = [round(value, 3) for value in stats.stddev]
    if max(stddev) < 8 or max(mean) < 12:
        raise RuntimeError(
            f"EOX {year} image appears blank/flat: mean={mean}, stddev={stddev}"
        )
    return image, {
        "request_url": response.url,
        "content_type": content_type,
        "bytes": len(response.content),
        "mean_rgb": mean,
        "stddev_rgb": stddev,
    }


def lonlat_to_xy(lon: float, lat: float, bbox, size) -> tuple[int, int]:
    minx, miny, maxx, maxy = bbox
    width, height = size
    x = round((lon - minx) / (maxx - minx) * width)
    y = round((maxy - lat) / (maxy - miny) * height)
    return x, y


def ring_pixels(coords: Iterable, bbox, size) -> list[tuple[int, int]]:
    return [lonlat_to_xy(float(lon), float(lat), bbox, size) for lon, lat in coords]


def polygon_parts(geom):
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        yield from geom.geoms
    else:
        raise TypeError(geom.geom_type)


def load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_overlay(image: Image.Image, geom, bbox, year: int) -> Image.Image:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    for polygon in polygon_parts(geom):
        exterior = ring_pixels(polygon.exterior.coords, bbox, canvas.size)
        if len(exterior) >= 2:
            draw.line(exterior, fill=(255, 255, 255, 235), width=4, joint="curve")
            draw.line(exterior, fill=(7, 20, 14, 170), width=1, joint="curve")
    font = load_font(29, bold=True)
    small = load_font(21, bold=True)
    for marker in SECTOR_MARKERS:
        x, y = lonlat_to_xy(marker["lon"], marker["lat"], bbox, canvas.size)
        r = 13
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 193, 88, 235), outline=(20, 25, 20, 230), width=3)
        label = f'{marker["code"]} {marker["name_th"]}'
        box = draw.textbbox((0, 0), label, font=small)
        tw, th = box[2] - box[0], box[3] - box[1]
        px, py = x + 17, y - th - 7
        draw.rounded_rectangle(
            (px - 7, py - 5, px + tw + 7, py + th + 5),
            radius=7,
            fill=(4, 12, 8, 188),
            outline=(255, 255, 255, 70),
        )
        draw.text((px, py), label, font=small, fill=(255, 255, 255, 245))
    title = f"KRABI PROVINCE · SENTINEL-2 CLOUDLESS {year}"
    subtitle = "Province-wide visual context · DMCR cell markers are approximate navigation points"
    title_box = draw.textbbox((0, 0), title, font=font)
    subtitle_box = draw.textbbox((0, 0), subtitle, font=small)
    panel_w = max(title_box[2], subtitle_box[2]) + 44
    draw.rounded_rectangle((24, 24, 24 + panel_w, 116), radius=15, fill=(4, 12, 8, 195), outline=(255, 255, 255, 70))
    draw.text((45, 37), title, font=font, fill=(255, 255, 255, 250))
    draw.text((45, 78), subtitle, font=small, fill=(191, 209, 198, 250))
    return canvas


def save_jpeg(image: Image.Image, path: Path, quality: int = 91) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def visual_difference(before: Image.Image, after: Image.Image) -> dict:
    if before.size != after.size:
        raise ValueError("Comparison images do not share the same dimensions")
    sample_before = before.resize((512, 512))
    sample_after = after.resize((512, 512))
    diff = ImageChops.difference(sample_before, sample_after)
    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / 3
    rms = sum(stat.rms) / 3
    changed = sum(1 for px in diff.convert("L").getdata() if px >= 12)
    changed_fraction = changed / (512 * 512)
    if mean_abs < 1.0 or changed_fraction < 0.01:
        raise RuntimeError(
            "Before/after assets are too similar, suggesting an upstream or caching failure: "
            f"mean_abs={mean_abs:.3f}, changed_fraction={changed_fraction:.4f}"
        )
    return {
        "mean_absolute_rgb_difference": round(mean_abs, 4),
        "mean_rms_rgb_difference": round(rms, 4),
        "fraction_pixels_luma_difference_gte_12": round(changed_fraction, 6),
    }


def write_geojson(feature: dict, geom, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    props = dict(feature.get("properties", {}))
    props.update(
        {
            "source": "OpenGISData-Thailand/provinces.geojson",
            "source_url": PROVINCES_URL,
            "usage": "province-wide visualization and analysis AOI",
            "official_cadastral_boundary": False,
        }
    )
    obj = {
        "type": "FeatureCollection",
        "name": "krabi_province_boundary",
        "features": [{"type": "Feature", "properties": props, "geometry": mapping(geom)}],
    }
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_sector_geojson(path: Path) -> None:
    features = []
    for marker in SECTOR_MARKERS:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    **marker,
                    "geometry_status": "approximate_navigation_marker_not_official_cell_boundary",
                    "source_name": "DMCR littoral-cell names A13-A19",
                },
                "geometry": {"type": "Point", "coordinates": [marker["lon"], marker["lat"]]},
            }
        )
    path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "name": "krabi_dmcr_cell_markers", "features": features},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def contact_sheet(images: dict[int, Image.Image], output: Path) -> None:
    thumbs = []
    for year in YEARS:
        thumb = images[year].copy()
        thumb.thumbnail((900, 900))
        panel = Image.new("RGB", (thumb.width, thumb.height + 58), (6, 17, 12))
        panel.paste(thumb, (0, 58))
        draw = ImageDraw.Draw(panel)
        draw.text((18, 15), f"Sentinel-2 cloudless {year}", font=load_font(25, True), fill=(245, 250, 247))
        thumbs.append(panel)
    gap = 10
    sheet_w = max(im.width for im in thumbs) * 2 + gap
    sheet_h = max(im.height for im in thumbs) * 2 + gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), (3, 9, 6))
    for idx, thumb in enumerate(thumbs):
        x = (idx % 2) * (thumb.width + gap)
        y = (idx // 2) * (thumb.height + gap)
        sheet.paste(thumb, (x, y))
    save_jpeg(sheet, output, quality=88)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("regions/krabi/web/assets/province"),
    )
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    collection = get_json(PROVINCES_URL)
    feature, geom = find_krabi_boundary(collection)
    simplified = geom.simplify(0.0008, preserve_topology=True)
    bbox = coastal_display_bbox(geom)
    height = image_height(bbox)

    write_geojson(feature, simplified, out / "krabi_province_boundary.geojson")
    write_sector_geojson(out / "krabi_littoral_cell_markers.geojson")

    source_images: dict[int, Image.Image] = {}
    manifest_years: dict[str, dict] = {}
    for year in YEARS:
        image, response_meta = download_wms(year, bbox, WIDTH, height)
        source_images[year] = image
        plain_path = out / f"krabi_province_s2cloudless_{year}.jpg"
        labelled_path = out / f"krabi_province_s2cloudless_{year}_labelled.jpg"
        save_jpeg(image, plain_path)
        save_jpeg(draw_overlay(image, simplified, bbox, year), labelled_path)
        manifest_years[str(year)] = {
            **response_meta,
            "plain_path": plain_path.name,
            "plain_sha256": sha256(plain_path),
            "labelled_path": labelled_path.name,
            "labelled_sha256": sha256(labelled_path),
            "dimensions": [WIDTH, height],
        }

    difference = visual_difference(source_images[YEARS[0]], source_images[YEARS[-1]])
    contact_sheet(
        {year: draw_overlay(source_images[year], simplified, bbox, year) for year in YEARS},
        out / "krabi_province_contact_sheet.jpg",
    )

    manifest = {
        "generated_utc": utc_now(),
        "asset_status": "VALIDATED_STATIC_PROVINCE_IMAGERY",
        "province": "Krabi",
        "province_code": "81",
        "source_boundary": {
            "url": PROVINCES_URL,
            "properties": feature.get("properties", {}),
        },
        "display_bbox_wgs84": list(bbox),
        "years": manifest_years,
        "before_after_validation": {
            "before_year": YEARS[0],
            "after_year": YEARS[-1],
            **difference,
        },
        "interpretation": {
            "visual_use": "province-wide annual cloudless visual comparison",
            "not_valid_for": [
                "tide-matched shoreline position",
                "engineering erosion rate",
                "causal attribution",
            ],
            "next_analysis": "extract annual shorelines and calculate transect rates by coastal cell",
        },
        "attribution": (
            "Sentinel-2 cloudless by EOX IT Services GmbH; contains modified "
            "Copernicus Sentinel data. Boundary: OpenGISData-Thailand."
        ),
    }
    (out / "province_imagery_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Final self-contained validation.
    required = [
        out / "krabi_province_boundary.geojson",
        out / "krabi_littoral_cell_markers.geojson",
        out / "province_imagery_manifest.json",
        out / "krabi_province_contact_sheet.jpg",
    ]
    for year in YEARS:
        required.extend(
            [
                out / f"krabi_province_s2cloudless_{year}.jpg",
                out / f"krabi_province_s2cloudless_{year}_labelled.jpg",
            ]
        )
    missing = [str(path) for path in required if not path.exists() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError("Province imagery package is incomplete: " + ", ".join(missing))

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
