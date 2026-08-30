#!/usr/bin/env python3
"""Build a real Sentinel-2 L2A current-year image for the Krabi web map.

Historical annual images in the dashboard come from EOX Sentinel-2 cloudless.
The current calendar year is different: a complete annual cloudless product is
not available yet. This script therefore queries Element 84 Earth Search for
actual Sentinel-2 Collection 1 L2A scenes acquired during the current year and
builds a fixed-size, province-wide latest-clear-pixel composite.

The output remains visual screening evidence. It is not tide-matched shoreline
position and must not be used as an engineering erosion rate by itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import numpy as np
import rasterio
import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from shapely.geometry import MultiPolygon, Polygon, shape

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
USER_AGENT = "corrosion-krabi-current-year-builder/1.0"
CLEAR_SCL_CODES = (2, 4, 5, 6, 7)
RECENT_PER_TILE = 7
LOW_CLOUD_PER_TILE = 7
MAX_ITEMS_TOTAL = 72
MIN_CLEAR_FRACTION = 0.70
MAX_UNCOVERED_FRACTION = 0.12


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def item_datetime(item: dict[str, Any]) -> datetime:
    props = item.get("properties", {})
    raw = props.get("datetime") or props.get("start_datetime")
    if not raw:
        raise ValueError(f"STAC item has no datetime: {item.get('id')}")
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)


def cloud_cover(item: dict[str, Any]) -> float:
    raw = item.get("properties", {}).get("eo:cloud_cover")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 100.0


def tile_key(item: dict[str, Any]) -> str:
    props = item.get("properties", {})
    for key in ("grid:code", "s2:mgrs_tile", "mgrs:tile"):
        value = props.get(key)
        if value:
            return str(value).replace("MGRS-", "")
    zone = props.get("mgrs:utm_zone")
    band = props.get("mgrs:latitude_band")
    square = props.get("mgrs:grid_square")
    if zone and band and square:
        return f"{int(zone):02d}{band}{square}"
    match = re.search(r"_T(\d{2}[A-Z]{3})_", str(item.get("id", "")))
    if match:
        return match.group(1)
    return f"unknown:{item.get('id')}"


def asset_href(item: dict[str, Any], *keys: str) -> str:
    assets = item.get("assets", {})
    for key in keys:
        href = assets.get(key, {}).get("href")
        if href:
            return str(href)
    raise KeyError(f"Missing assets {keys} for {item.get('id')}")


def request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    response = requests.request(
        method,
        url,
        json=body if method.upper() == "POST" else None,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json,application/json"},
    )
    if not response.ok:
        raise RuntimeError(
            f"STAC request failed {response.status_code} {url}: {response.text[:600]}"
        )
    return response.json()


def search_items(geometry: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
    start_dt = datetime.combine(start, datetime_time.min, timezone.utc)
    end_dt = datetime.combine(end, datetime_time.max.replace(microsecond=0), timezone.utc)
    interval = f"{utc_iso(start_dt)}/{utc_iso(end_dt)}"
    body: dict[str, Any] = {
        "collections": [COLLECTION],
        "intersects": geometry,
        "datetime": interval,
        "limit": 200,
        "query": {"eo:cloud_cover": {"lt": 90}},
    }
    url = f"{EARTH_SEARCH}/search"
    method = "POST"
    items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    seen_pages: set[str] = set()

    while True:
        page_key = f"{method}:{url}:{json.dumps(body, sort_keys=True) if body else ''}"
        if page_key in seen_pages:
            raise RuntimeError("STAC pagination loop detected")
        seen_pages.add(page_key)
        page = request_json(method, url, body=body)
        for item in page.get("features", []):
            item_id = str(item.get("id"))
            if item_id in seen_items:
                continue
            try:
                asset_href(item, "visual")
                asset_href(item, "scl")
            except KeyError:
                continue
            seen_items.add(item_id)
            items.append(item)

        next_link = next(
            (link for link in page.get("links", []) if link.get("rel") == "next"),
            None,
        )
        if not next_link:
            break
        method = str(next_link.get("method", "GET")).upper()
        url = urljoin(url, str(next_link["href"]))
        body = next_link.get("body") if method == "POST" else None

    if not items:
        raise RuntimeError(f"No {COLLECTION} scenes found for {interval}")
    return items


def select_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[tile_key(item)].append(item)

    selected: dict[str, dict[str, Any]] = {}
    per_tile: dict[str, int] = {}
    for tile, tile_items in sorted(grouped.items()):
        recent = sorted(tile_items, key=item_datetime, reverse=True)[:RECENT_PER_TILE]
        low_cloud = sorted(
            tile_items,
            key=lambda item: (cloud_cover(item), -item_datetime(item).timestamp()),
        )[:LOW_CLOUD_PER_TILE]
        for item in [*recent, *low_cloud]:
            selected[str(item["id"])] = item
        per_tile[tile] = len({str(item["id"]) for item in [*recent, *low_cloud]})

    ordered = sorted(selected.values(), key=item_datetime, reverse=True)
    if len(ordered) > MAX_ITEMS_TOTAL:
        ordered = ordered[:MAX_ITEMS_TOTAL]
    return ordered, per_tile


def raster_env() -> dict[str, Any]:
    return {
        "AWS_NO_SIGN_REQUEST": "YES",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_HTTP_MAX_RETRY": "5",
        "GDAL_HTTP_RETRY_DELAY": "2",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": str(64 * 1024 * 1024),
    }


def reproject_asset(
    href: str,
    *,
    bands: int | Iterable[int],
    width: int,
    height: int,
    transform,
    dtype: str,
    resampling: Resampling,
) -> np.ndarray:
    if isinstance(bands, int):
        band_indexes = [bands]
    else:
        band_indexes = list(bands)
    shape_out = (len(band_indexes), height, width)
    last_error: Exception | None = None

    for attempt in range(1, 4):
        destination = np.zeros(shape_out, dtype=dtype)
        try:
            with rasterio.Env(**raster_env()):
                with rasterio.open(href) as src:
                    reproject(
                        source=rasterio.band(src, band_indexes),
                        destination=destination,
                        src_transform=src.transform,
                        src_crs=src.crs,
                        src_nodata=src.nodata,
                        dst_transform=transform,
                        dst_crs="EPSG:4326",
                        dst_nodata=0,
                        resampling=resampling,
                        num_threads=2,
                    )
            return destination
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f"Could not read {href}: {last_error}")


def compose_latest_clear(
    items: list[dict[str, Any]],
    *,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[Image.Image, dict[str, Any]]:
    transform = from_bounds(*bbox, width=width, height=height)
    clear_rgb = np.zeros((3, height, width), dtype=np.uint8)
    latest_any_rgb = np.zeros_like(clear_rgb)
    clear_filled = np.zeros((height, width), dtype=bool)
    any_filled = np.zeros((height, width), dtype=bool)
    scene_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for index, item in enumerate(items, 1):
        item_id = str(item.get("id"))
        dt = item_datetime(item)
        try:
            scl = reproject_asset(
                asset_href(item, "scl"),
                bands=1,
                width=width,
                height=height,
                transform=transform,
                dtype="uint8",
                resampling=Resampling.nearest,
            )[0]
            rgb = reproject_asset(
                asset_href(item, "visual"),
                bands=(1, 2, 3),
                width=width,
                height=height,
                transform=transform,
                dtype="uint8",
                resampling=Resampling.bilinear,
            )
        except Exception as exc:
            failures.append({"scene_id": item_id, "error": str(exc)})
            continue

        nonzero = np.max(rgb, axis=0) > 0
        newest_any = nonzero & ~any_filled
        if np.any(newest_any):
            latest_any_rgb[:, newest_any] = rgb[:, newest_any]
            any_filled[newest_any] = True

        clear = np.isin(scl, CLEAR_SCL_CODES) & nonzero
        newest_clear = clear & ~clear_filled
        clear_pixels = int(np.count_nonzero(newest_clear))
        if clear_pixels:
            clear_rgb[:, newest_clear] = rgb[:, newest_clear]
            clear_filled[newest_clear] = True

        scene_records.append(
            {
                "scene_id": item_id,
                "datetime_utc": utc_iso(dt),
                "mgrs_tile": tile_key(item),
                "scene_cloud_cover_percent": round(cloud_cover(item), 4),
                "new_clear_pixels": clear_pixels,
                "clear_fraction_after_scene": round(float(clear_filled.mean()), 6),
                "visual_href": asset_href(item, "visual"),
                "scl_href": asset_href(item, "scl"),
            }
        )
        print(
            f"[{index}/{len(items)}] {item_id} "
            f"cloud={cloud_cover(item):.1f}% clear={clear_filled.mean():.3%}",
            flush=True,
        )

        if clear_filled.mean() >= 0.992 and index >= max(8, len(items) // 3):
            break

    fallback = ~clear_filled & any_filled
    if np.any(fallback):
        clear_rgb[:, fallback] = latest_any_rgb[:, fallback]
    uncovered = ~any_filled

    clear_fraction = float(clear_filled.mean())
    fallback_fraction = float(fallback.mean())
    uncovered_fraction = float(uncovered.mean())
    if clear_fraction < MIN_CLEAR_FRACTION:
        raise RuntimeError(
            f"Current-year composite clear coverage is too low: {clear_fraction:.3%}"
        )
    if uncovered_fraction > MAX_UNCOVERED_FRACTION:
        raise RuntimeError(
            f"Current-year composite has too much uncovered area: {uncovered_fraction:.3%}"
        )

    image = Image.fromarray(np.moveaxis(clear_rgb, 0, 2), mode="RGB")
    stats = ImageStat.Stat(image.resize((256, 256)))
    if max(stats.stddev) < 8 or max(stats.mean) < 12:
        raise RuntimeError(
            f"Current-year image appears blank/flat: mean={stats.mean}, stddev={stats.stddev}"
        )

    used = [record for record in scene_records if record["new_clear_pixels"] > 0]
    if not used:
        raise RuntimeError("No Sentinel-2 scene contributed clear pixels")
    used_datetimes = [datetime.fromisoformat(record["datetime_utc"].replace("Z", "+00:00")) for record in used]
    metadata = {
        "processed_scene_count": len(scene_records),
        "used_clear_scene_count": len(used),
        "failed_scene_count": len(failures),
        "clear_pixel_fraction": round(clear_fraction, 6),
        "fallback_latest_observation_fraction": round(fallback_fraction, 6),
        "uncovered_fraction": round(uncovered_fraction, 6),
        "earliest_contributing_datetime_utc": utc_iso(min(used_datetimes)),
        "latest_contributing_datetime_utc": utc_iso(max(used_datetimes)),
        "scene_records": scene_records,
        "failures": failures,
        "mean_rgb": [round(value, 3) for value in stats.mean],
        "stddev_rgb": [round(value, 3) for value in stats.stddev],
    }
    return image, metadata


def polygon_parts(geom):
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        yield from geom.geoms
    else:
        raise TypeError(geom.geom_type)


def lonlat_to_xy(lon: float, lat: float, bbox, size) -> tuple[int, int]:
    minx, miny, maxx, maxy = bbox
    width, height = size
    x = round((lon - minx) / (maxx - minx) * width)
    y = round((maxy - lat) / (maxy - miny) * height)
    return x, y


def load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def draw_labelled(
    image: Image.Image,
    boundary_geom,
    bbox,
    *,
    year: int,
    data_through: str,
) -> Image.Image:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    for polygon in polygon_parts(boundary_geom):
        points = [lonlat_to_xy(float(lon), float(lat), bbox, canvas.size) for lon, lat in polygon.exterior.coords]
        if len(points) >= 2:
            draw.line(points, fill=(255, 255, 255, 235), width=4, joint="curve")
            draw.line(points, fill=(7, 20, 14, 180), width=1, joint="curve")

    title_font = load_font(29, bold=True)
    small_font = load_font(21, bold=True)
    title = f"KRABI PROVINCE · SENTINEL-2 L2A {year} YTD"
    subtitle = f"Latest-clear-pixel composite · data through {data_through}"
    title_box = draw.textbbox((0, 0), title, font=title_font)
    subtitle_box = draw.textbbox((0, 0), subtitle, font=small_font)
    panel_width = max(title_box[2], subtitle_box[2]) + 44
    draw.rounded_rectangle(
        (24, 24, 24 + panel_width, 116),
        radius=15,
        fill=(4, 12, 8, 200),
        outline=(255, 255, 255, 75),
    )
    draw.text((45, 37), title, font=title_font, fill=(255, 255, 255, 250))
    draw.text((45, 78), subtitle, font=small_font, fill=(191, 209, 198, 250))
    return canvas


def visual_difference(before: Image.Image, after: Image.Image) -> dict[str, float]:
    if before.size != after.size:
        raise ValueError(f"Image dimensions differ: {before.size} vs {after.size}")
    before_sample = before.resize((512, 512))
    after_sample = after.resize((512, 512))
    diff = ImageChops.difference(before_sample, after_sample)
    stats = ImageStat.Stat(diff)
    mean_abs = sum(stats.mean) / 3
    rms = sum(stats.rms) / 3
    changed_fraction = sum(1 for pixel in diff.convert("L").getdata() if pixel >= 12) / (512 * 512)
    if mean_abs < 1.0 or changed_fraction < 0.01:
        raise RuntimeError(
            "Current-year image is unexpectedly similar to the historical image: "
            f"mean_abs={mean_abs:.4f}, changed_fraction={changed_fraction:.6f}"
        )
    return {
        "mean_absolute_rgb_difference": round(mean_abs, 4),
        "mean_rms_rgb_difference": round(rms, 4),
        "fraction_pixels_luma_difference_gte_12": round(changed_fraction, 6),
    }


def save_jpeg(image: Image.Image, path: Path, quality: int = 91) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("regions/krabi/web/assets/province"),
    )
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    year = args.year
    if year != args.end_date.year:
        raise ValueError(f"--year {year} and --end-date {args.end_date} do not match")
    out = args.out.resolve()
    manifest_path = out / "province_imagery_manifest.json"
    boundary_path = out / "krabi_province_boundary.geojson"
    if not manifest_path.exists() or not boundary_path.exists():
        raise FileNotFoundError("Run build_krabi_province_assets.py before the current-year builder")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    boundary_collection = json.loads(boundary_path.read_text(encoding="utf-8"))
    if manifest.get("province") != "Krabi":
        raise RuntimeError(f"Manifest province is not Krabi: {manifest.get('province')}")
    if not boundary_collection.get("features"):
        raise RuntimeError("Krabi boundary GeoJSON has no features")

    geometry = boundary_collection["features"][0]["geometry"]
    boundary_geom = shape(geometry)
    bbox = tuple(float(value) for value in manifest["display_bbox_wgs84"])
    reference = manifest["years"].get("2024") or next(iter(manifest["years"].values()))
    width, height = map(int, reference["dimensions"])

    start = date(year, 1, 1)
    items = search_items(geometry, start, args.end_date)
    selected, per_tile = select_items(items)
    if not selected:
        raise RuntimeError("No usable current-year Sentinel-2 scenes were selected")
    print(
        json.dumps(
            {
                "year": year,
                "search_start": start.isoformat(),
                "search_end": args.end_date.isoformat(),
                "candidate_count": len(items),
                "selected_count": len(selected),
                "selected_per_tile": per_tile,
            },
            indent=2,
        ),
        flush=True,
    )

    image, composite = compose_latest_clear(
        selected,
        bbox=bbox,
        width=width,
        height=height,
    )
    latest_datetime = composite["latest_contributing_datetime_utc"]
    latest_date = latest_datetime[:10]

    plain_path = out / f"krabi_province_s2_{year}_ytd.jpg"
    labelled_path = out / f"krabi_province_s2_{year}_ytd_labelled.jpg"
    save_jpeg(image, plain_path)
    save_jpeg(
        draw_labelled(
            image,
            boundary_geom,
            bbox,
            year=year,
            data_through=latest_date,
        ),
        labelled_path,
    )

    before_year = min(int(value) for value in manifest["years"])
    before_path = out / manifest["years"][str(before_year)]["plain_path"]
    difference = visual_difference(Image.open(before_path).convert("RGB"), image)

    manifest["years"][str(year)] = {
        "source": "Element 84 Earth Search",
        "stac_endpoint": EARTH_SEARCH,
        "collection": COLLECTION,
        "product_type": "Sentinel-2 L2A current-year latest-clear-pixel composite",
        "temporal_status": "YEAR_TO_DATE_NOT_COMPLETE_ANNUAL_MOSAIC",
        "search_start_date": start.isoformat(),
        "search_end_date": args.end_date.isoformat(),
        "latest_acquisition_datetime_utc": latest_datetime,
        "latest_acquisition_date": latest_date,
        "candidate_scene_count": len(items),
        "selected_scene_count": len(selected),
        "selected_scene_count_by_mgrs_tile": per_tile,
        **composite,
        "plain_path": plain_path.name,
        "plain_sha256": sha256(plain_path),
        "labelled_path": labelled_path.name,
        "labelled_sha256": sha256(labelled_path),
        "dimensions": [width, height],
        "clear_scl_codes": list(CLEAR_SCL_CODES),
        "attribution": (
            f"Contains modified Copernicus Sentinel data {year}; "
            "accessed through Element 84 Earth Search."
        ),
        "interpretation_note": (
            "Real Sentinel-2 L2A scenes acquired in the current year. "
            "Latest clear observation varies by pixel and is not tide matched."
        ),
    }
    manifest["generated_utc"] = utc_iso(datetime.now(timezone.utc))
    manifest["latest_available_year"] = year
    manifest["latest_data_through"] = latest_date
    manifest["current_year_status"] = "VALIDATED_SENTINEL2_L2A_YEAR_TO_DATE"
    manifest["before_after_validation"] = {
        "before_year": before_year,
        "after_year": year,
        **difference,
    }
    manifest["interpretation"]["visual_use"] = (
        "province-wide historical annual mosaics plus current-year Sentinel-2 L2A YTD comparison"
    )
    manifest["attribution"] = (
        "Historical annual imagery: Sentinel-2 cloudless by EOX IT Services GmbH. "
        f"Current {year} imagery: contains modified Copernicus Sentinel data, "
        "accessed through Element 84 Earth Search. Boundary: OpenGISData-Thailand."
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": manifest["current_year_status"],
                "province": manifest["province"],
                "year": year,
                "latest_data_through": latest_date,
                "dimensions": [width, height],
                "plain_path": plain_path.name,
                "clear_pixel_fraction": composite["clear_pixel_fraction"],
                "fallback_fraction": composite["fallback_latest_observation_fraction"],
                "uncovered_fraction": composite["uncovered_fraction"],
                "difference_from_first_year": difference,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
