#!/usr/bin/env python3
"""Build image-derived coastal-change products for the Samut Songkhram MVP.

The extracted feature is a spectral water-land boundary, not a surveyed or
tide-normalized shoreline. All epochs remain explicitly tide-unverified.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import (
    LineString,
    MultiLineString,
    Point,
    Polygon,
    mapping,
    shape,
)
from shapely.ops import linemerge, nearest_points, transform, unary_union


ROOT = Path(__file__).resolve().parents[1]
AOI_PATH = ROOT / "data/aoi/samut_songkhram_aoi.geojson"
CATALOG_PATH = ROOT / "data/catalog/mvp_optical_scenes.csv"
EPOCH_PATH = ROOT / "data/catalog/mvp_epochs.json"
OUT = ROOT / "data/processed"
WEB_DATA = OUT / "web"
CRS_ANALYSIS = "EPSG:32647"
CRS_WEB = "EPSG:4326"
BAND_NAMES = ["blue", "green", "red", "nir", "swir1"]
TIDE_STATUS = "unverified"

# A provisional centreline used only to isolate the exposed coast from inland
# canals and river banks. Boundary positions themselves always come from imagery.
COAST_GUIDE_WGS84 = LineString(
    [
        (99.938, 13.307),
        (99.955, 13.312),
        (99.973, 13.320),
        (99.991, 13.332),
        (100.008, 13.344),
        (100.026, 13.355),
        (100.044, 13.368),
        (100.061, 13.381),
        (100.075, 13.393),
    ]
)


@dataclass
class EpochResult:
    target_year: int
    actual_year: int
    dataset: str
    sensor: str
    resolution_m: int
    dates: list[str]
    composite_path: Path
    preview_path: Path
    boundary_path: Path
    vegetation_path: Path
    threshold: float
    vegetation_threshold: float
    valid_fraction: float
    ocean_fraction: float
    vegetation_area_ha: float
    boundary_utm: Any
    ocean_utm: Any
    image_coordinates: list[list[float]]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


TO_UTM = transformer(CRS_WEB, CRS_ANALYSIS)
TO_WEB = transformer(CRS_ANALYSIS, CRS_WEB)


def project_geom(geom: Any, tx: Transformer) -> Any:
    return transform(tx.transform, geom)


def load_aoi() -> tuple[Any, Any]:
    record = load_json(AOI_PATH)
    aoi_web = shape(record["features"][0]["geometry"])
    return aoi_web, project_geom(aoi_web, TO_UTM)


def load_catalog() -> list[dict[str, str]]:
    with CATALOG_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def row_coverage(row: dict[str, str]) -> float:
    match = re.search(r"AOI coverage=([0-9.]+)", row.get("selection_reason", ""))
    return float(match.group(1)) if match else 0.0


def scene_rows(
    catalog: list[dict[str, str]],
    dataset: str,
    actual_year: int,
    start: str | None = None,
    end: str | None = None,
    count: int | None = None,
) -> list[dict[str, str]]:
    selected = []
    for row in catalog:
        if row.get("dataset") != dataset or not row.get("local_path"):
            continue
        if not row.get("acquisition_datetime_utc", "").startswith(str(actual_year)):
            continue
        acquisition_date = row.get("acquisition_datetime_utc", "")[:10]
        if start and acquisition_date < start:
            continue
        if end and acquisition_date > end:
            continue
        if row_coverage(row) < 0.95:
            continue
        paths = [ROOT / value for value in row["local_path"].split(";")]
        if not paths or not all(path.exists() for path in paths):
            continue
        selected.append(row)
    if actual_year == 2009:
        landsat5 = [row for row in selected if row.get("sensor") == "landsat-5"]
        if len(landsat5) >= 2:
            selected = landsat5
    selected.sort(key=lambda row: row["acquisition_datetime_utc"])
    if count is not None:
        selected = selected[:count]
    return selected


def paths_by_band(row: dict[str, str]) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for value in row["local_path"].split(";"):
        path = ROOT / value
        output[path.name.split("_")[0].upper()] = path
    return output


def target_grid(rows: list[dict[str, str]], dataset: str) -> dict[str, Any]:
    paths = paths_by_band(rows[0])
    reference = paths["GREEN"] if dataset == "landsat" else paths["B11"]
    with rasterio.open(reference) as src:
        return {
            "crs": src.crs,
            "transform": src.transform,
            "height": src.height,
            "width": src.width,
            "resolution": int(round(abs(src.transform.a))),
            "bounds": src.bounds,
        }


def aligned_read(
    path: Path,
    grid: dict[str, Any],
    resampling: Resampling,
    dtype: str,
) -> np.ndarray:
    destination = np.zeros((grid["height"], grid["width"]), dtype=dtype)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            dst_nodata=0,
            resampling=resampling,
        )
    return destination


def read_scene(
    row: dict[str, str], dataset: str, grid: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    paths = paths_by_band(row)
    if dataset == "landsat":
        keys = ["BLUE", "GREEN", "RED", "NIR", "SWIR1"]
        qa = aligned_read(paths["QA"], grid, Resampling.nearest, "uint16")
        invalid_bits = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
        valid = (qa & invalid_bits) == 0
        arrays = [
            aligned_read(paths[key], grid, Resampling.bilinear, "float32")
            for key in keys
        ]
        data = np.stack(arrays).astype("float32") * 0.0000275 - 0.2
        valid &= np.all(np.stack(arrays) > 0, axis=0)
    else:
        keys = ["B2", "B3", "B4", "B8", "B11"]
        scl = aligned_read(paths["SCL"], grid, Resampling.nearest, "uint16")
        valid = ~np.isin(scl, [0, 1, 3, 8, 9, 10, 11])
        arrays = [
            aligned_read(paths[key], grid, Resampling.bilinear, "float32")
            for key in keys
        ]
        data = np.stack(arrays).astype("float32") / 10000.0
        valid &= np.all(np.stack(arrays) > 0, axis=0)
    valid &= np.all(np.isfinite(data), axis=0)
    valid &= np.all((data > -0.25) & (data < 1.7), axis=0)
    data[:, ~valid] = np.nan
    return data, valid


def build_composite(
    rows: list[dict[str, str]], dataset: str
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    grid = target_grid(rows, dataset)
    scenes = []
    masks = []
    for row in rows:
        data, valid = read_scene(row, dataset, grid)
        scenes.append(data)
        masks.append(valid)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        composite = np.nanmedian(np.stack(scenes), axis=0).astype("float32")
    valid_count = np.sum(np.stack(masks), axis=0).astype("uint8")
    composite[:, valid_count == 0] = np.nan
    return composite, valid_count, grid


def write_composite(
    path: Path,
    composite: np.ndarray,
    grid: dict[str, Any],
    tags: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "COG",
        "height": grid["height"],
        "width": grid["width"],
        "count": len(BAND_NAMES),
        "dtype": "float32",
        "crs": grid["crs"],
        "transform": grid["transform"],
        "nodata": np.nan,
        "compress": "DEFLATE",
        "blocksize": 512,
        "overview_resampling": "average",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(composite)
        for index, name in enumerate(BAND_NAMES, start=1):
            dst.set_band_description(index, name)
        dst.update_tags(**{key: str(value) for key, value in tags.items()})


def save_preview(path: Path, composite: np.ndarray, valid: np.ndarray) -> None:
    rgb = composite[[2, 1, 0]].copy()
    output = np.zeros((rgb.shape[1], rgb.shape[2], 3), dtype="uint8")
    for channel in range(3):
        values = rgb[channel][valid & np.isfinite(rgb[channel])]
        low, high = np.percentile(values, [2, 98]) if values.size else (0.0, 1.0)
        stretched = np.clip((rgb[channel] - low) / max(high - low, 1e-6), 0, 1)
        output[:, :, channel] = np.nan_to_num(stretched ** 0.85 * 255).astype("uint8")
    image = Image.fromarray(output)
    max_dimension = 1400
    if max(image.size) > max_dimension:
        scale = max_dimension / max(image.size)
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=84, method=6)


def otsu_threshold(values: np.ndarray, fallback: float = 0.0) -> float:
    values = values[np.isfinite(values)]
    if values.size < 100:
        return fallback
    values = np.clip(values, -1.0, 1.0)
    hist, edges = np.histogram(values, bins=256, range=(-1.0, 1.0))
    centres = (edges[:-1] + edges[1:]) / 2
    weight1 = np.cumsum(hist)
    weight2 = np.cumsum(hist[::-1])[::-1]
    mean1 = np.cumsum(hist * centres) / np.maximum(weight1, 1)
    mean2 = (
        np.cumsum((hist * centres)[::-1]) / np.maximum(weight2[::-1], 1)
    )[::-1]
    variance = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    if not np.any(np.isfinite(variance)):
        return fallback
    return float(centres[int(np.nanargmax(variance))])


def clean_binary(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    structure = ndimage.generate_binary_structure(2, 2)
    cleaned = ndimage.binary_opening(mask, structure=structure, iterations=1)
    cleaned = ndimage.binary_closing(cleaned, structure=structure, iterations=1)
    labels, count = ndimage.label(cleaned, structure=structure)
    if count:
        sizes = np.bincount(labels.ravel())
        cleaned = sizes[labels] >= min_pixels
        cleaned[labels == 0] = False
    inverse_labels, inverse_count = ndimage.label(~cleaned, structure=structure)
    if inverse_count:
        inverse_sizes = np.bincount(inverse_labels.ravel())
        cleaned |= (inverse_sizes[inverse_labels] < min_pixels) & (inverse_labels != 0)
    return cleaned


def select_ocean(mask: np.ndarray) -> np.ndarray:
    structure = ndimage.generate_binary_structure(2, 2)
    labels, count = ndimage.label(mask, structure=structure)
    if not count:
        return np.zeros_like(mask, dtype=bool)
    edge_labels = np.unique(
        np.concatenate([labels[-3:, :].ravel(), labels[:, -3:].ravel()])
    )
    edge_labels = edge_labels[edge_labels != 0]
    sizes = np.bincount(labels.ravel())
    if edge_labels.size:
        chosen = int(edge_labels[np.argmax(sizes[edge_labels])])
    else:
        chosen = int(np.argmax(sizes[1:]) + 1)
    return labels == chosen


def choose_water_mask(
    mndwi: np.ndarray, valid: np.ndarray, grid: dict[str, Any], aoi_utm: Any
) -> tuple[float, str, np.ndarray, Any, dict[str, Any]]:
    """Compare Otsu, fixed, and percentile candidates with stability guardrails."""
    values = mndwi[valid & np.isfinite(mndwi)]
    otsu = float(np.clip(otsu_threshold(values, 0.0), -0.15, 0.25))
    candidates = {
        "otsu": otsu,
        "fixed_zero": 0.0,
        "percentile_60": float(np.percentile(values, 60)) if values.size else 0.0,
    }
    evaluated: dict[str, tuple[float, np.ndarray, Any]] = {}
    diagnostics: dict[str, Any] = {}
    for name, threshold in candidates.items():
        water = clean_binary(valid & (mndwi > threshold), min_pixels=10)
        ocean_mask = select_ocean(water)
        ocean = mask_polygon(ocean_mask, grid["transform"]).intersection(aoi_utm)
        fraction = float(ocean.area / max(aoi_utm.area, 1))
        evaluated[name] = (threshold, ocean_mask, ocean)
        diagnostics[name] = {
            "threshold": round(threshold, 5),
            "ocean_fraction": round(fraction, 4),
        }
    # Prefer Otsu when the edge-connected ocean occupies a plausible share of
    # this coastal AOI. Only invoke alternatives to reject obvious histogram
    # failures; the guardrail is not a tide normalization.
    otsu_fraction = diagnostics["otsu"]["ocean_fraction"]
    if 0.30 <= otsu_fraction <= 0.50:
        chosen_name = "otsu"
    else:
        plausible = [
            name
            for name in ["fixed_zero", "percentile_60"]
            if 0.30 <= diagnostics[name]["ocean_fraction"] <= 0.50
        ]
        chosen_name = (
            min(plausible, key=lambda name: abs(diagnostics[name]["ocean_fraction"] - 0.42))
            if plausible
            else "otsu"
        )
    threshold, ocean_mask, ocean = evaluated[chosen_name]
    return threshold, chosen_name, ocean_mask, ocean, diagnostics


def mask_polygon(mask: np.ndarray, affine: Any) -> Any:
    polygons = [
        shape(geometry)
        for geometry, value in shapes(
            mask.astype("uint8"), mask=mask, transform=affine, connectivity=8
        )
        if value == 1
    ]
    return unary_union(polygons) if polygons else Polygon()


def iter_lines(geom: Any) -> Iterable[LineString]:
    if geom.is_empty:
        return
    if geom.geom_type == "LineString":
        yield geom
    elif geom.geom_type == "LinearRing":
        yield LineString(geom)
    elif hasattr(geom, "geoms"):
        for child in geom.geoms:
            yield from iter_lines(child)


def exterior_lines(geom: Any) -> list[LineString]:
    """Return polygon exteriors only, excluding pond/island interior rings."""
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [LineString(geom.exterior.coords)]
    if geom.geom_type == "MultiPolygon":
        return [LineString(part.exterior.coords) for part in geom.geoms]
    if hasattr(geom, "geoms"):
        output: list[LineString] = []
        for child in geom.geoms:
            output.extend(exterior_lines(child))
        return output
    return []


def coastal_boundary(ocean: Any, aoi_utm: Any, resolution: int) -> Any:
    guide = project_geom(COAST_GUIDE_WGS84, TO_UTM)
    corridor = guide.buffer(4000, cap_style="flat")
    raw = unary_union(exterior_lines(ocean)).difference(
        aoi_utm.boundary.buffer(resolution * 2.5)
    )
    raw = raw.intersection(corridor)
    if raw.is_empty:
        return MultiLineString([])
    # Enforce one continuous coastal trace by sampling a provisional guide and
    # snapping every retained vertex to the image-derived ocean exterior. This
    # excludes connected fishpond/canal detours while preserving image positions.
    vertices = []
    sample_spacing = max(50.0, float(resolution) * 2)
    for distance in np.arange(0, guide.length + sample_spacing, sample_spacing):
        point = guide.interpolate(min(float(distance), guide.length))
        snapped = nearest_points(point, raw)[1]
        if point.distance(snapped) <= 2500:
            if not vertices or Point(vertices[-1]).distance(snapped) >= resolution * 0.5:
                vertices.append((snapped.x, snapped.y))
    if len(vertices) < 3:
        lines = [line for line in iter_lines(raw) if line.length >= 150]
        return max(lines, key=lambda line: line.length) if lines else MultiLineString([])
    return LineString(vertices).simplify(resolution * 0.35)


def image_coordinates(bounds: Any) -> list[list[float]]:
    corners = [
        (bounds.left, bounds.top),
        (bounds.right, bounds.top),
        (bounds.right, bounds.bottom),
        (bounds.left, bounds.bottom),
    ]
    return [[float(lon), float(lat)] for lon, lat in (TO_WEB.transform(*p) for p in corners)]


def save_boundary(
    path: Path,
    boundary: Any,
    properties: dict[str, Any],
) -> None:
    features = []
    for index, line in enumerate(iter_lines(boundary), start=1):
        if line.length < 150:
            continue
        props = dict(properties)
        props.update({"segment_id": index, "length_m": round(line.length, 1)})
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(project_geom(line, TO_WEB)),
            }
        )
    write_json(path, feature_collection(features))


def vegetation_proxy(
    composite: np.ndarray,
    valid: np.ndarray,
    ocean: Any,
    boundary: Any,
    grid: dict[str, Any],
) -> tuple[Any, float, float]:
    red, nir = composite[2], composite[3]
    ndvi = np.divide(nir - red, nir + red, out=np.full_like(red, np.nan), where=np.abs(nir + red) > 1e-6)
    candidate_values = ndvi[valid & np.isfinite(ndvi)]
    threshold = float(np.clip(otsu_threshold(candidate_values, 0.4), 0.32, 0.55))
    corridor = project_geom(COAST_GUIDE_WGS84, TO_UTM).buffer(5000, cap_style="flat")
    corridor_mask = rasterio.features.geometry_mask(
        [mapping(corridor)],
        out_shape=(grid["height"], grid["width"]),
        transform=grid["transform"],
        invert=True,
    )
    vegetation = valid & (ndvi >= threshold) & corridor_mask
    vegetation &= ~rasterio.features.geometry_mask(
        [mapping(ocean)],
        out_shape=(grid["height"], grid["width"]),
        transform=grid["transform"],
        invert=True,
    )
    vegetation = clean_binary(vegetation, min_pixels=8)
    polygon = mask_polygon(vegetation, grid["transform"]).intersection(corridor)
    polygon = polygon.buffer(0).simplify(grid["resolution"] * 0.6)
    return polygon, threshold, float(polygon.area / 10_000)


def process_epoch(
    entry: dict[str, Any], catalog: list[dict[str, str]], aoi_utm: Any
) -> EpochResult:
    target_year = int(entry["target_year"])
    actual_year = int(entry["actual_year"])
    dataset = str(entry["dataset"])
    rows = scene_rows(
        catalog,
        dataset,
        actual_year,
        start=entry.get("start"),
        end=entry.get("end"),
        count=int(entry["count"]) if entry.get("count") is not None else None,
    )
    if len(rows) < 2:
        raise RuntimeError(
            f"epoch {target_year} has only {len(rows)} usable full-coverage scenes"
        )
    composite, valid_count, grid = build_composite(rows, dataset)
    valid = valid_count > 0
    dates = [row["acquisition_datetime_utc"][:10] for row in rows]
    sensors = sorted({row["sensor"] for row in rows})
    sensor = ", ".join(sensors)
    period = f"{dates[0]} to {dates[-1]}"
    composite_path = OUT / "optical" / f"{target_year}_composite.tif"
    write_composite(
        composite_path,
        composite,
        grid,
        {
            "target_year": target_year,
            "actual_year": actual_year,
            "sensor": sensor,
            "acquisition_period": period,
            "scene_count": len(rows),
            "method": "quality-masked per-band median surface reflectance",
            "tide_status": TIDE_STATUS,
            "boundary_interpretation": "spectral water-land boundary; not surveyed shoreline",
        },
    )
    preview_path = WEB_DATA / "imagery" / f"{target_year}.webp"
    save_preview(preview_path, composite, valid)

    green, swir = composite[1], composite[4]
    mndwi = np.divide(green - swir, green + swir, out=np.full_like(green, np.nan), where=np.abs(green + swir) > 1e-6)
    threshold, threshold_method, ocean_mask, ocean, threshold_candidates = choose_water_mask(
        mndwi, valid, grid, aoi_utm
    )
    boundary = coastal_boundary(ocean, aoi_utm, grid["resolution"])
    boundary_path = OUT / "water_boundary" / f"{target_year}_water_land_boundary.geojson"
    boundary_properties = {
        "year": target_year,
        "target_year": target_year,
        "actual_year": actual_year,
        "sensor": sensor,
        "actual_acquisition_period": period,
        "acquisition_period": period,
        "scene_count": len(rows),
        "method": f"MNDWI {threshold_method}, conservative morphology, edge-connected ocean exterior, corridor-guided continuous trace",
        "threshold": round(threshold, 5),
        "mndwi_threshold": round(threshold, 5),
        "threshold_candidates": threshold_candidates,
        "tide_status": TIDE_STATUS,
        "source_resolution_m": grid["resolution"],
        "interpretation": "image-derived water-land boundary, not a true/surveyed shoreline",
        "qa_status": "MVP automated extraction; visual review required",
    }
    save_boundary(boundary_path, boundary, boundary_properties)

    vegetation, vegetation_threshold, vegetation_area_ha = vegetation_proxy(
        composite, valid, ocean, boundary, grid
    )
    vegetation_path = OUT / "vegetation" / f"{target_year}_coastal_vegetation_proxy.geojson"
    vegetation_feature = {
        "type": "Feature",
        "properties": {
            "target_year": target_year,
            "actual_year": actual_year,
            "sensor": sensor,
            "method": "NDVI threshold within provisional coastal corridor and image-derived land",
            "ndvi_threshold": round(vegetation_threshold, 5),
            "area_ha": round(vegetation_area_ha, 2),
            "interpretation": "coastal vegetation spectral proxy; not a verified mangrove inventory",
            "tide_status": TIDE_STATUS,
        },
        "geometry": mapping(project_geom(vegetation, TO_WEB)),
    }
    write_json(vegetation_path, feature_collection([vegetation_feature]))

    valid_fraction = float(valid.mean())
    ocean_fraction = float(ocean.area / max(aoi_utm.area, 1))
    print(
        f"epoch={target_year} actual={actual_year} scenes={len(rows)} "
        f"valid={valid_fraction:.3f} water={ocean_fraction:.3f} "
        f"boundary_km={boundary.length / 1000:.2f} vegetation_ha={vegetation_area_ha:.1f}",
        flush=True,
    )
    return EpochResult(
        target_year=target_year,
        actual_year=actual_year,
        dataset=dataset,
        sensor=sensor,
        resolution_m=grid["resolution"],
        dates=dates,
        composite_path=composite_path,
        preview_path=preview_path,
        boundary_path=boundary_path,
        vegetation_path=vegetation_path,
        threshold=threshold,
        vegetation_threshold=vegetation_threshold,
        valid_fraction=valid_fraction,
        ocean_fraction=ocean_fraction,
        vegetation_area_ha=vegetation_area_ha,
        boundary_utm=boundary,
        ocean_utm=ocean,
        image_coordinates=image_coordinates(grid["bounds"]),
    )


def snapped_reference(boundary: Any) -> LineString:
    guide = project_geom(COAST_GUIDE_WGS84, TO_UTM)
    points = []
    for distance in np.arange(0, guide.length + 1, 100):
        guide_point = guide.interpolate(float(distance))
        snapped = nearest_points(guide_point, boundary)[1]
        if guide_point.distance(snapped) <= 2500:
            if not points or Point(points[-1]).distance(snapped) > 10:
                points.append((snapped.x, snapped.y))
    if len(points) < 3:
        lines = list(iter_lines(boundary))
        if not lines:
            raise RuntimeError("latest image-derived boundary is empty")
        return max(lines, key=lambda line: line.length)
    return LineString(points).simplify(15)


def intersection_points(geom: Any) -> list[Point]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Point":
        return [geom]
    if geom.geom_type == "MultiPoint":
        return list(geom.geoms)
    if geom.geom_type in {"LineString", "LinearRing"}:
        return [geom.interpolate(0.5, normalized=True)]
    if hasattr(geom, "geoms"):
        output = []
        for child in geom.geoms:
            output.extend(intersection_points(child))
        return output
    return []


def build_transects(results: list[EpochResult]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    latest = results[-1]
    reference = snapped_reference(latest.boundary_utm)
    interval = 100.0
    half_length = 1500.0
    features = []
    time_rows: list[dict[str, Any]] = []
    summaries = []
    transect_number = 0
    for distance in np.arange(0, reference.length + 1, interval):
        centre = reference.interpolate(float(distance))
        before = reference.interpolate(max(0.0, float(distance) - 30.0))
        after = reference.interpolate(min(reference.length, float(distance) + 30.0))
        dx, dy = after.x - before.x, after.y - before.y
        magnitude = math.hypot(dx, dy)
        if magnitude < 1:
            continue
        nx, ny = -dy / magnitude, dx / magnitude
        side_a = Point(centre.x + nx * half_length, centre.y + ny * half_length)
        side_b = Point(centre.x - nx * half_length, centre.y - ny * half_length)
        a_is_sea = latest.ocean_utm.buffer(5).contains(side_a)
        b_is_sea = latest.ocean_utm.buffer(5).contains(side_b)
        if a_is_sea and not b_is_sea:
            inland, seaward = side_b, side_a
        elif b_is_sea and not a_is_sea:
            inland, seaward = side_a, side_b
        else:
            # Gulf of Thailand is generally south/southeast of this coast.
            seaward, inland = (side_a, side_b) if side_a.y < side_b.y else (side_b, side_a)
        transect = LineString([inland, seaward])
        baseline_position = transect.project(centre)
        positions: dict[str, float | None] = {}
        observations = 0
        for result in results:
            points = intersection_points(transect.intersection(result.boundary_utm))
            if points:
                point = min(points, key=lambda item: item.distance(centre))
                position = float(transect.project(point) - baseline_position)
                positions[str(result.target_year)] = round(position, 2)
                observations += 1
            else:
                positions[str(result.target_year)] = None
            time_rows.append(
                {
                    "transect_id": f"T{transect_number + 1:03d}",
                    "year": result.target_year,
                    "target_year": result.target_year,
                    "actual_year": result.actual_year,
                    "distance_m": positions[str(result.target_year)],
                    "position_m": positions[str(result.target_year)],
                    "sensor": result.sensor,
                    "resolution_m": result.resolution_m,
                    "tide_status": TIDE_STATUS,
                    "confidence": "LOW",
                }
            )
        earliest = positions.get(str(results[0].target_year))
        newest = positions.get(str(latest.target_year))
        net = None if earliest is None or newest is None else float(newest - earliest)
        elapsed = latest.actual_year - results[0].actual_year
        rate = None if net is None or elapsed <= 0 else net / elapsed
        regression_observations = [
            (result.actual_year, positions[str(result.target_year)])
            for result in results
            if positions[str(result.target_year)] is not None
        ]
        regression_rate = (
            float(
                np.polyfit(
                    [item[0] for item in regression_observations],
                    [float(item[1]) for item in regression_observations],
                    1,
                )[0]
            )
            if len(regression_observations) >= 2
            else None
        )
        uncertainty = max(result.resolution_m for result in results)
        if observations < 4 or net is None:
            change_class = "insufficient_data"
        elif net > uncertainty:
            change_class = "apparent_accretion"
        elif net < -uncertainty:
            change_class = "apparent_erosion"
        else:
            change_class = "stable"
        transect_number += 1
        transect_id = f"T{transect_number:03d}"
        properties = {
            "transect_id": transect_id,
            "chainage_m": round(float(distance), 1),
            "spacing_m": interval,
            "length_m": half_length * 2,
            "observations": observations,
            "positions_m": positions,
            "net_change_m": None if net is None else round(net, 2),
            "net_movement_m": None if net is None else round(net, 2),
            "rate_m_per_year": None if rate is None else round(rate, 2),
            "end_point_rate_m_per_year": None if rate is None else round(rate, 2),
            "regression_rate_m_per_year": None if regression_rate is None else round(regression_rate, 2),
            "start_year": results[0].target_year,
            "end_year": latest.target_year,
            "n_observations": observations,
            "classification": change_class,
            "classification_detail": "stable_within_resolution" if change_class == "stable" else change_class,
            "confidence": "LOW",
            "confidence_reasons": [
                "tide level unavailable for every epoch",
                "intertidal mudflat exposure can move the observed wet/dry edge",
                "sensor resolution and wet/dry pixel mixing limit positional precision",
                "automated spectral boundary requires field or orthophoto validation",
            ],
            "interpretation": "positive is apparent seaward movement; not tide-normalized shoreline change",
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": mapping(project_geom(transect, TO_WEB)),
            }
        )
        summaries.append(properties)

    valid_summaries = [item for item in summaries if item["classification"] != "insufficient_data"]
    nets = [float(item["net_change_m"]) for item in valid_summaries if item["net_change_m"] is not None]
    class_counts = {
        key: sum(item["classification"] == key for item in summaries)
        for key in [
            "apparent_erosion",
            "apparent_accretion",
            "stable",
            "insufficient_data",
        ]
    }
    summary = {
        "title": "Samut Songkhram image-derived coastal change MVP",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "epoch_count": len(results),
        "target_years": [item.target_year for item in results],
        "actual_years": [item.actual_year for item in results],
        "reference_epoch": latest.target_year,
        "transect_spacing_m": interval,
        "transect_count": len(summaries),
        "classified_transect_count": len(valid_summaries),
        "class_counts": class_counts,
        "apparent_erosion_length_km": round(class_counts["apparent_erosion"] * interval / 1000, 2),
        "apparent_accretion_length_km": round(class_counts["apparent_accretion"] * interval / 1000, 2),
        "stable_length_km": round(class_counts["stable"] * interval / 1000, 2),
        "median_net_change_m": round(float(np.median(nets)), 2) if nets else None,
        "mean_net_change_m": round(float(np.mean(nets)), 2) if nets else None,
        "tide_status": TIDE_STATUS,
        "overall_confidence": "LOW",
        "interpretation": "Results describe apparent movement of image-derived water-land boundaries, not true or surveyed shorelines.",
    }
    return feature_collection(features), time_rows, summary


def copy_web_products(results: list[EpochResult]) -> None:
    for directory in ["boundaries", "vegetation"]:
        (WEB_DATA / directory).mkdir(parents=True, exist_ok=True)
    for result in results:
        shutil.copy2(
            result.boundary_path,
            WEB_DATA / "boundaries" / result.boundary_path.name,
        )
        shutil.copy2(
            result.vegetation_path,
            WEB_DATA / "vegetation" / result.vegetation_path.name,
        )


def build_outputs(results: list[EpochResult]) -> None:
    transects, time_rows, summary = build_transects(results)
    transect_path = OUT / "transects" / "transects.geojson"
    write_json(transect_path, transects)
    csv_path = OUT / "transects" / "transect_timeseries.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(time_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(time_rows)
    vegetation_stats = [
        {
            "target_year": result.target_year,
            "actual_year": result.actual_year,
            "area_ha": round(result.vegetation_area_ha, 2),
            "ndvi_threshold": round(result.vegetation_threshold, 5),
        }
        for result in results
    ]
    summary["vegetation_proxy"] = vegetation_stats
    write_json(OUT / "statistics" / "summary.json", summary)
    with (OUT / "statistics" / "vegetation_proxy.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(vegetation_stats[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(vegetation_stats)

    first_vegetation = vegetation_stats[0]["area_ha"]
    last_vegetation = vegetation_stats[-1]["area_ha"]
    summary["vegetation_proxy_change_ha"] = round(last_vegetation - first_vegetation, 2)
    summary["vegetation_proxy_change_percent"] = round(
        (last_vegetation - first_vegetation) / max(first_vegetation, 0.01) * 100,
        2,
    )
    write_json(OUT / "statistics" / "summary.json", summary)
    write_json(OUT / "statistics" / "transect_summary.geojson", transects)
    yearly_path = OUT / "statistics" / "transect_yearly.csv"
    with yearly_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(time_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(time_rows)

    copy_web_products(results)
    write_json(WEB_DATA / "transects.geojson", transects)
    write_json(WEB_DATA / "transect_summary.geojson", transects)
    write_json(WEB_DATA / "transect_yearly.json", time_rows)
    write_json(WEB_DATA / "summary.json", summary)
    write_json(WEB_DATA / "vegetation_stats.json", vegetation_stats)
    index = {
        "title": "Samut Songkhram Coastal Change MVP",
        "aoi": "Samut Songkhram coast (provisional analytical AOI)",
        "analysis_crs": CRS_ANALYSIS,
        "tide_status": TIDE_STATUS,
        "disclaimer_th": "เส้นที่แสดงเป็นขอบเขตน้ำ–แผ่นดินจากภาพดาวเทียม ไม่ใช่เส้นชายฝั่งจริงหรือผลสำรวจ และยังไม่ได้ปรับแก้ระดับน้ำขึ้นน้ำลง",
        "disclaimer_en": "Displayed lines are image-derived water-land boundaries, not surveyed shorelines, and are not tide-normalized.",
        "epochs": [
            {
                "targetYear": result.target_year,
                "actualYear": result.actual_year,
                "dataset": result.dataset,
                "sensor": result.sensor,
                "dates": result.dates,
                "sceneCount": len(result.dates),
                "resolutionM": result.resolution_m,
                "tideStatus": TIDE_STATUS,
                "mndwiThreshold": round(result.threshold, 5),
                "validFraction": round(result.valid_fraction, 4),
                "oceanFraction": round(result.ocean_fraction, 4),
                "vegetationAreaHa": round(result.vegetation_area_ha, 2),
                "image": f"imagery/{result.target_year}.webp",
                "imageCoordinates": result.image_coordinates,
                "boundary": f"boundaries/{result.boundary_path.name}",
                "vegetation": f"vegetation/{result.vegetation_path.name}",
            }
            for result in results
        ],
    }
    write_json(WEB_DATA / "index.json", index)
    write_json(WEB_DATA / "years.json", {"years": [item.target_year for item in results]})
    write_json(
        WEB_DATA / "imagery_index.json",
        {"epochs": index["epochs"], "tide_status": TIDE_STATUS},
    )
    shutil.copytree(
        WEB_DATA,
        ROOT / "web/public/data",
        dirs_exist_ok=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--epochs",
        help="Optional comma-separated target years; default processes every MVP epoch",
    )
    args = parser.parse_args()
    metadata = load_json(EPOCH_PATH)
    entries = metadata["epochs"]
    if args.epochs:
        selected = {int(value) for value in args.epochs.split(",")}
        entries = [entry for entry in entries if int(entry["target_year"]) in selected]
    entries.sort(key=lambda entry: int(entry["target_year"]))
    if len(entries) < 2:
        raise SystemExit("at least two epochs are required")
    catalog = load_catalog()
    _, aoi_utm = load_aoi()
    for directory in [
        "optical",
        "water_boundary",
        "vegetation",
        "transects",
        "statistics",
        "web",
    ]:
        (OUT / directory).mkdir(parents=True, exist_ok=True)
    results = [process_epoch(entry, catalog, aoi_utm) for entry in entries]
    build_outputs(results)
    print(f"built {len(results)} epochs under {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
