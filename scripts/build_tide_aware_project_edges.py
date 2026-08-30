#!/usr/bin/env python3
"""Build tide-aware screening indicators for the Samut Songkhram project plots.

The workflow selects one Sentinel-2 acquisition per year at a comparable
predicted tide, extracts an image-derived WATERLINE as supporting evidence,
extracts a fixed-threshold MANGROVE_EDGE_PROXY from same-season composites,
and compares project transects with nearby candidate controls.

This remains a screening analysis. Matching predicted station tide improves
comparability but does not normalize the shoreline, verify local water level,
validate mangrove classification, establish planting dates, or prove a causal
erosion-reduction effect.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask
from shapely.geometry import (
    LineString,
    MultiLineString,
    Point,
    mapping,
    shape,
)
from shapely.ops import transform, unary_union

from scripts.build_coastal_change_mvp import (
    build_composite,
    choose_water_mask,
    clean_binary,
    exterior_lines,
    iter_lines,
    mask_polygon,
    save_preview,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
CRS_WEB = "EPSG:4326"
CRS_ANALYSIS = "EPSG:32647"
TO_UTM = Transformer.from_crs(CRS_WEB, CRS_ANALYSIS, always_xy=True)
TO_WEB = Transformer.from_crs(CRS_ANALYSIS, CRS_WEB, always_xy=True)

DEFAULT_YEARS = (2023, 2024, 2025, 2026)
DEFAULT_CATALOG = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
)
DEFAULT_PLOTS = Path("data/aoi/samut_songkhram_project_plots.geojson")
DEFAULT_AOI = Path("data/aoi/samut_songkhram_project_analysis_aoi.geojson")
DEFAULT_OUTPUT = Path("data/processed/project_tide_aware")
DEFAULT_WEB = Path("web/public/data/project_tide_aware")

MAX_SECONDARY_BRACKET_MINUTES = 12 * 60
MAX_SCREENING_TIDE_SPREAD_M = 0.40
VEGETATION_NDVI_THRESHOLD = 0.35
POSITIONAL_SCREENING_THRESHOLD_M = 20.0
TRANSECT_SPACING_M = 50.0
TRANSECT_HALF_LENGTH_M = 1500.0
COASTAL_CONTEXT_BUFFER_M = 3500.0
CONTROL_EXCLUSION_BUFFER_M = 150.0
CONTROL_MAX_DISTANCE_M = 3000.0
CONTROL_SEPARATION_M = 150.0
TARGET_CONTROLS_PER_PLOT = 3


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def load_feature_union(path: Path) -> tuple[dict[str, Any], Any]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    geometries = [
        transform(TO_UTM.transform, shape(feature["geometry"]))
        for feature in collection["features"]
    ]
    return collection, unary_union(geometries).buffer(0)


def year_of(row: dict[str, str]) -> int:
    return int(row["acquisition_datetime_utc"][:4])


def parse_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def secondary_bracket_minutes(row: dict[str, str]) -> float:
    if row.get("tide_source_tier") != "secondary_published_extrema":
        return 0.0
    value = parse_float(row.get("tide_bracket_span_minutes"))
    return math.inf if value is None else value


def tide_eligible(row: dict[str, str]) -> bool:
    return (
        row.get("dataset") == "sentinel2"
        and row.get("tide_datum") == "MSL"
        and parse_float(row.get("tide_level")) is not None
        and row.get("tide_status")
        in {"modelled_secondary_extrema_cosine", "predicted_interpolated"}
    )


def select_common_tide_scenes(
    rows: list[dict[str, str]],
    *,
    years: Iterable[int] = DEFAULT_YEARS,
    max_secondary_bracket_minutes: float = MAX_SECONDARY_BRACKET_MINUTES,
) -> dict[str, Any]:
    """Select one acquisition per year by explicit, deterministic tide criteria."""
    requested_years = tuple(sorted(set(int(year) for year in years)))
    grouped: dict[int, list[dict[str, str]]] = {}
    for year in requested_years:
        candidates = [
            row for row in rows if year_of(row) == year and tide_eligible(row)
        ]
        if not candidates:
            raise ValueError(f"no tide-eligible Sentinel-2 scene for {year}")
        grouped[year] = sorted(
            candidates,
            key=lambda row: (
                row["acquisition_datetime_utc"],
                row["scene_id"],
            ),
        )

    combinations = []
    for combo in itertools.product(*(grouped[year] for year in requested_years)):
        levels = [float(row["tide_level"]) for row in combo]
        spans = [secondary_bracket_minutes(row) for row in combo]
        bracket_ok = all(span <= max_secondary_bracket_minutes for span in spans)
        target = float(np.mean(levels))
        spread = max(levels) - min(levels)
        max_deviation = max(abs(value - target) for value in levels)
        cloud = sum(float(row.get("cloud_cover_aoi") or 100.0) for row in combo)
        span_sum = sum(span for span in spans if math.isfinite(span))
        score = (
            0 if bracket_ok else 1,
            round(spread, 8),
            round(max_deviation, 8),
            round(cloud, 8),
            round(span_sum, 8),
            tuple(row["scene_id"] for row in combo),
        )
        combinations.append(
            {
                "rows": combo,
                "levels": levels,
                "spans": spans,
                "bracket_ok": bracket_ok,
                "target": target,
                "spread": spread,
                "max_deviation": max_deviation,
                "score": score,
            }
        )
    best = min(combinations, key=lambda item: item["score"])
    selected_ids = {row["scene_id"] for row in best["rows"]}
    target = float(best["target"])
    audit = []
    for row in sorted(
        [row for row in rows if year_of(row) in requested_years],
        key=lambda item: (year_of(item), item["acquisition_datetime_utc"]),
    ):
        level = parse_float(row.get("tide_level"))
        span = secondary_bracket_minutes(row)
        audit.append(
            {
                "year": year_of(row),
                "scene_id": row["scene_id"],
                "acquisition_datetime_bangkok": row[
                    "acquisition_datetime_bangkok"
                ],
                "tide_level_m_msl": level,
                "delta_from_selected_target_m": (
                    None if level is None else round(level - target, 4)
                ),
                "tide_status": row.get("tide_status"),
                "tide_source_tier": row.get("tide_source_tier"),
                "secondary_bracket_span_minutes": (
                    None if not math.isfinite(span) else round(span, 2)
                ),
                "secondary_bracket_acceptable": span
                <= max_secondary_bracket_minutes,
                "selected_for_waterline": row["scene_id"] in selected_ids,
                "selection_note": (
                    "selected by minimum cross-year tide spread after requiring "
                    "secondary interpolation brackets <= 12 hours"
                    if row["scene_id"] in selected_ids
                    else "not selected; retained for same-season vegetation composite"
                ),
            }
        )
    status = (
        "ACCEPTABLE_FOR_TIDE_AWARE_SCREENING"
        if best["bracket_ok"]
        and best["spread"] <= MAX_SCREENING_TIDE_SPREAD_M
        else "REVIEW_REQUIRED"
    )
    return {
        "years": list(requested_years),
        "selected_rows": list(best["rows"]),
        "target_tide_m_msl": round(target, 4),
        "tide_spread_m": round(float(best["spread"]), 4),
        "maximum_delta_from_target_m": round(float(best["max_deviation"]), 4),
        "maximum_secondary_bracket_minutes": round(
            max(best["spans"]), 2
        ),
        "status": status,
        "audit": audit,
    }


def finite_ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.divide(
        a,
        b,
        out=np.full_like(a, np.nan, dtype="float32"),
        where=np.isfinite(a) & np.isfinite(b) & (np.abs(b) > 1e-6),
    )


def geometry_mask_for(geometry: Any, grid: dict[str, Any]) -> np.ndarray:
    return geometry_mask(
        [mapping(geometry)],
        out_shape=(grid["height"], grid["width"]),
        transform=grid["transform"],
        invert=True,
    )


def project_waterline(
    ocean: Any,
    *,
    aoi_utm: Any,
    plot_union: Any,
    resolution_m: float,
) -> Any:
    raw = unary_union(exterior_lines(ocean))
    raw = raw.difference(aoi_utm.boundary.buffer(resolution_m * 2.5))
    raw = raw.intersection(
        plot_union.buffer(COASTAL_CONTEXT_BUFFER_M).intersection(aoi_utm)
    )
    lines = [
        line.simplify(resolution_m * 0.25)
        for line in iter_lines(raw)
        if line.length >= max(100.0, resolution_m * 5)
        and line.distance(plot_union) <= COASTAL_CONTEXT_BUFFER_M
    ]
    if not lines:
        return MultiLineString([])
    return unary_union(lines)


def save_lines(path: Path, geometry: Any, properties: dict[str, Any]) -> None:
    features = []
    for index, line in enumerate(iter_lines(geometry), start=1):
        if line.length < 50:
            continue
        props = dict(properties)
        props.update({"segment_id": index, "length_m": round(line.length, 2)})
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(transform(TO_WEB.transform, line)),
            }
        )
    write_json(path, {"type": "FeatureCollection", "features": features})


def build_vegetation_proxy(
    composite: np.ndarray,
    valid: np.ndarray,
    grid: dict[str, Any],
    *,
    corridor_utm: Any,
) -> tuple[Any, Any, float]:
    red, nir = composite[2], composite[3]
    ndvi = finite_ratio(nir - red, nir + red)
    corridor_mask = geometry_mask_for(corridor_utm, grid)
    mask = (
        valid
        & corridor_mask
        & np.isfinite(ndvi)
        & (ndvi >= VEGETATION_NDVI_THRESHOLD)
    )
    mask = clean_binary(mask, min_pixels=4)
    polygon = (
        mask_polygon(mask, grid["transform"])
        .intersection(corridor_utm)
        .buffer(0)
        .simplify(grid["resolution"] * 0.25)
    )
    edge = unary_union(exterior_lines(polygon))
    return polygon, edge, float(polygon.area / 10_000.0)


def save_polygon(
    path: Path, polygon: Any, properties: dict[str, Any]
) -> None:
    write_json(
        path,
        {
            "type": "FeatureCollection",
            "features": (
                []
                if polygon.is_empty
                else [
                    {
                        "type": "Feature",
                        "properties": properties,
                        "geometry": mapping(transform(TO_WEB.transform, polygon)),
                    }
                ]
            ),
        },
    )


def point_candidates(geometry: Any) -> list[Point]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type == "MultiPoint":
        return list(geometry.geoms)
    if geometry.geom_type in {"LineString", "LinearRing"}:
        coordinates = list(geometry.coords)
        if not coordinates:
            return []
        return [Point(coordinates[0]), Point(coordinates[-1])]
    if geometry.geom_type == "Polygon":
        return point_candidates(geometry.boundary)
    if hasattr(geometry, "geoms"):
        output: list[Point] = []
        for child in geometry.geoms:
            output.extend(point_candidates(child))
        return output
    return []


def build_transects(
    reference: Any,
    latest_ocean: Any,
    plots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    plot_union = unary_union([item["geometry_utm"] for item in plots])
    records = []
    number = 0
    for segment_index, segment in enumerate(
        sorted(iter_lines(reference), key=lambda line: (line.centroid.x, line.centroid.y)),
        start=1,
    ):
        if segment.length < TRANSECT_SPACING_M:
            continue
        for distance in np.arange(
            TRANSECT_SPACING_M / 2,
            segment.length,
            TRANSECT_SPACING_M,
        ):
            centre = segment.interpolate(float(distance))
            before = segment.interpolate(max(0.0, float(distance) - 20.0))
            after = segment.interpolate(
                min(segment.length, float(distance) + 20.0)
            )
            dx, dy = after.x - before.x, after.y - before.y
            magnitude = math.hypot(dx, dy)
            if magnitude < 1:
                continue
            nx, ny = -dy / magnitude, dx / magnitude
            test_a = Point(centre.x + nx * 100, centre.y + ny * 100)
            test_b = Point(centre.x - nx * 100, centre.y - ny * 100)
            a_sea = latest_ocean.buffer(10).covers(test_a)
            b_sea = latest_ocean.buffer(10).covers(test_b)
            if a_sea and not b_sea:
                sea_sign = 1
            elif b_sea and not a_sea:
                sea_sign = -1
            else:
                sea_sign = (
                    1
                    if test_a.distance(plot_union) > test_b.distance(plot_union)
                    else -1
                )
            seaward = Point(
                centre.x + sea_sign * nx * TRANSECT_HALF_LENGTH_M,
                centre.y + sea_sign * ny * TRANSECT_HALF_LENGTH_M,
            )
            inland = Point(
                centre.x - sea_sign * nx * TRANSECT_HALF_LENGTH_M,
                centre.y - sea_sign * ny * TRANSECT_HALF_LENGTH_M,
            )
            line = LineString([inland, seaward])
            intersections = []
            for item in plots:
                length = line.intersection(item["geometry_utm"]).length
                if length > 0:
                    intersections.append((length, item["plot_id"]))
            plot_id = max(intersections)[1] if intersections else ""
            role = "TREATMENT" if plot_id else "CONTROL_CANDIDATE_POOL"
            number += 1
            records.append(
                {
                    "transect_id": f"TA{number:04d}",
                    "segment_index": segment_index,
                    "chainage_m": round(float(distance), 2),
                    "geometry_utm": line,
                    "centre_utm": centre,
                    "baseline_projection_m": TRANSECT_HALF_LENGTH_M,
                    "role": role,
                    "plot_id": plot_id,
                    "distance_to_project_m": round(centre.distance(plot_union), 2),
                }
            )
    return records


def position_on_transect(
    transect: dict[str, Any],
    geometry: Any,
    *,
    mode: str,
) -> float | None:
    line = transect["geometry_utm"]
    points = point_candidates(line.intersection(geometry))
    if not points:
        return None
    projections = [line.project(point) for point in points]
    baseline = float(transect["baseline_projection_m"])
    if mode == "nearest_reference":
        selected = min(projections, key=lambda value: abs(value - baseline))
    elif mode == "seaward_most":
        selected = max(projections)
    else:
        raise ValueError(f"unknown intersection mode: {mode}")
    return round(float(selected - baseline), 2)


def linear_rate(values: dict[int, float | None]) -> float | None:
    available = sorted(
        (year, value)
        for year, value in values.items()
        if value is not None
    )
    if len(available) < 2:
        return None
    return float(
        np.polyfit(
            [item[0] for item in available],
            [float(item[1]) for item in available],
            1,
        )[0]
    )


def series_metrics(
    values: dict[int, float | None],
    *,
    start_year: int = 2023,
    end_year: int = 2026,
) -> dict[str, Any]:
    available_values = [
        float(value) for value in values.values() if value is not None
    ]
    start = values.get(start_year)
    end = values.get(end_year)
    nsm = (
        None
        if start is None or end is None
        else round(float(end) - float(start), 2)
    )
    elapsed = end_year - start_year
    epr = None if nsm is None or elapsed <= 0 else round(nsm / elapsed, 2)
    lrr = linear_rate(values)
    sce = (
        None
        if len(available_values) < 2
        else round(max(available_values) - min(available_values), 2)
    )
    if nsm is None:
        classification = "INSUFFICIENT_DATA"
    elif nsm > POSITIONAL_SCREENING_THRESHOLD_M:
        classification = "APPARENT_SEAWARD"
    elif nsm < -POSITIONAL_SCREENING_THRESHOLD_M:
        classification = "APPARENT_LANDWARD"
    else:
        classification = "WITHIN_20M"
    return {
        "n_observations": len(available_values),
        "nsm_2023_2026_m": nsm,
        "epr_2023_2026_m_per_year": epr,
        "lrr_m_per_year": None if lrr is None else round(lrr, 2),
        "sce_m": sce,
        "classification": classification,
    }


def median_or_none(values: Iterable[float | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return None if not cleaned else round(float(np.median(cleaned)), 2)


def control_score(
    treatment_delta: dict[str, float | None],
    candidate_delta: dict[str, float | None],
    distance_m: float,
) -> float:
    score = distance_m / 1000.0
    used = 0
    for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
        treatment = treatment_delta.get(indicator)
        candidate = candidate_delta.get(indicator)
        if treatment is not None and candidate is not None:
            score += abs(float(candidate) - float(treatment)) / 20.0
            used += 1
    return score + (2.0 if used == 0 else 0.0)


def choose_candidate_controls(
    *,
    transects: list[dict[str, Any]],
    positions: dict[tuple[str, str, int], float | None],
    plots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    treatment_by_plot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates = []
    for transect in transects:
        if transect["plot_id"]:
            treatment_by_plot[transect["plot_id"]].append(transect)
        else:
            candidates.append(transect)

    project_union = unary_union([item["geometry_utm"] for item in plots])
    plot_by_id = {item["plot_id"]: item for item in plots}
    output = []
    for plot_id, treatment in treatment_by_plot.items():
        treatment_delta = {}
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
            values = []
            for transect in treatment:
                first = positions.get((transect["transect_id"], indicator, 2023))
                second = positions.get((transect["transect_id"], indicator, 2024))
                if first is not None and second is not None:
                    values.append(second - first)
            treatment_delta[indicator] = median_or_none(values)

        eligible = []
        plot_geometry = plot_by_id[plot_id]["geometry_utm"]
        for candidate in candidates:
            line = candidate["geometry_utm"]
            if line.intersects(project_union.buffer(CONTROL_EXCLUSION_BUFFER_M)):
                continue
            distance = candidate["centre_utm"].distance(plot_geometry)
            if distance > CONTROL_MAX_DISTANCE_M:
                continue
            candidate_delta = {}
            complete = True
            for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
                first = positions.get((candidate["transect_id"], indicator, 2023))
                second = positions.get((candidate["transect_id"], indicator, 2024))
                candidate_delta[indicator] = (
                    None
                    if first is None or second is None
                    else second - first
                )
                if first is None:
                    complete = False
            if not complete:
                continue
            eligible.append(
                (
                    control_score(treatment_delta, candidate_delta, distance),
                    distance,
                    candidate,
                    candidate_delta,
                )
            )
        eligible.sort(key=lambda item: (item[0], item[1], item[2]["transect_id"]))
        selected = []
        for score, distance, candidate, candidate_delta in eligible:
            if any(
                candidate["centre_utm"].distance(item[2]["centre_utm"])
                < CONTROL_SEPARATION_M
                for item in selected
            ):
                continue
            selected.append((score, distance, candidate, candidate_delta))
            if len(selected) >= TARGET_CONTROLS_PER_PLOT:
                break
        for sequence, (score, distance, candidate, candidate_delta) in enumerate(
            selected, start=1
        ):
            output.append(
                {
                    "plot_id": plot_id,
                    "control_id": f"{plot_id}-C{sequence}",
                    "control_transect_id": candidate["transect_id"],
                    "matching_score": round(score, 4),
                    "distance_to_plot_m": round(distance, 2),
                    "baseline_waterline_change_2023_2024_m": (
                        None
                        if candidate_delta["WATERLINE"] is None
                        else round(candidate_delta["WATERLINE"], 2)
                    ),
                    "baseline_mangrove_edge_change_2023_2024_m": (
                        None
                        if candidate_delta["MANGROVE_EDGE_PROXY"] is None
                        else round(
                            candidate_delta["MANGROVE_EDGE_PROXY"], 2
                        )
                    ),
                    "field_verification_status": "CANDIDATE_UNVERIFIED",
                    "exclusion_note": (
                        "not intersecting any project plot or its 150 m exclusion "
                        "buffer; structures, dredging, reclamation and planting "
                        "history remain unverified"
                    ),
                }
            )
    return output


def aggregate_indicator(
    metrics: list[dict[str, Any]],
    *,
    indicator: str,
) -> dict[str, Any]:
    subset = [row for row in metrics if row["indicator"] == indicator]
    classified = [
        row for row in subset if row["classification"] != "INSUFFICIENT_DATA"
    ]
    counts = Counter(row["classification"] for row in subset)
    return {
        "transect_count": len(subset),
        "classified_transect_count": len(classified),
        "median_nsm_2023_2026_m": median_or_none(
            row["nsm_2023_2026_m"] for row in classified
        ),
        "median_epr_2023_2026_m_per_year": median_or_none(
            row["epr_2023_2026_m_per_year"] for row in classified
        ),
        "median_lrr_m_per_year": median_or_none(
            row["lrr_m_per_year"] for row in classified
        ),
        "class_counts": dict(sorted(counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--plots", type=Path, default=DEFAULT_PLOTS)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output", type=Path, default=DEFAULT_WEB)
    args = parser.parse_args()

    catalog_path = ROOT / args.catalog
    plots_path = ROOT / args.plots
    aoi_path = ROOT / args.aoi
    output = ROOT / args.output
    web_output = ROOT / args.web_output
    for path in (output, web_output):
        path.mkdir(parents=True, exist_ok=True)

    rows = load_csv(catalog_path)
    selection = select_common_tide_scenes(rows)
    if selection["status"] != "ACCEPTABLE_FOR_TIDE_AWARE_SCREENING":
        raise RuntimeError(
            "selected scene set did not meet tide-screening acceptance: "
            + json.dumps(selection, ensure_ascii=False)
        )
    selected_by_year = {
        year_of(row): row for row in selection["selected_rows"]
    }
    write_csv(output / "scene_selection_audit.csv", selection["audit"])
    write_json(
        output / "scene_selection.json",
        {
            key: value
            for key, value in selection.items()
            if key not in {"selected_rows", "audit"}
        }
        | {
            "selected_scenes": [
                {
                    "year": year_of(row),
                    "scene_id": row["scene_id"],
                    "acquisition_datetime_bangkok": row[
                        "acquisition_datetime_bangkok"
                    ],
                    "tide_level_m_msl": float(row["tide_level"]),
                    "delta_from_target_m": round(
                        float(row["tide_level"])
                        - selection["target_tide_m_msl"],
                        4,
                    ),
                    "tide_status": row["tide_status"],
                    "tide_source_tier": row["tide_source_tier"],
                    "tide_source_url": row["tide_source_url"],
                    "secondary_bracket_span_minutes": parse_float(
                        row.get("tide_bracket_span_minutes")
                    ),
                }
                for row in selection["selected_rows"]
            ]
        },
    )

    plot_collection = json.loads(plots_path.read_text(encoding="utf-8"))
    plots = []
    for feature in plot_collection["features"]:
        plots.append(
            {
                "plot_id": feature["properties"]["plot_id"],
                "properties": feature["properties"],
                "geometry_utm": transform(
                    TO_UTM.transform, shape(feature["geometry"])
                ).buffer(0),
            }
        )
    plot_union = unary_union([item["geometry_utm"] for item in plots]).buffer(0)
    _aoi_collection, aoi_utm = load_feature_union(aoi_path)
    corridor = plot_union.buffer(COASTAL_CONTEXT_BUFFER_M).intersection(
        aoi_utm
    )

    waterlines: dict[int, Any] = {}
    oceans: dict[int, Any] = {}
    vegetation_polygons: dict[int, Any] = {}
    vegetation_edges: dict[int, Any] = {}
    vegetation_area_ha: dict[int, float] = {}
    waterline_qa = []
    year_rows: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if year_of(row) in DEFAULT_YEARS and row.get("dataset") == "sentinel2":
            year_rows[year_of(row)].append(row)

    for year in DEFAULT_YEARS:
        selected = selected_by_year[year]
        water_composite, water_valid_count, water_grid = build_composite(
            [selected], "sentinel2"
        )
        water_valid = water_valid_count > 0
        save_preview(
            web_output / "imagery" / f"{year}_selected.webp",
            water_composite,
            water_valid,
        )
        green, swir1 = water_composite[1], water_composite[4]
        mndwi = finite_ratio(green - swir1, green + swir1)
        threshold, method, _ocean_mask, ocean, candidates = choose_water_mask(
            mndwi, water_valid, water_grid, aoi_utm
        )
        waterline = project_waterline(
            ocean,
            aoi_utm=aoi_utm,
            plot_union=plot_union,
            resolution_m=water_grid["resolution"],
        )
        if waterline.is_empty:
            raise RuntimeError(f"{year} project waterline is empty")
        oceans[year] = ocean
        waterlines[year] = waterline
        water_properties = {
            "indicator": "WATERLINE",
            "role": "SUPPORTING_ONLY",
            "year": year,
            "scene_id": selected["scene_id"],
            "acquisition_datetime_bangkok": selected[
                "acquisition_datetime_bangkok"
            ],
            "tide_level_m_msl": float(selected["tide_level"]),
            "tide_target_m_msl": selection["target_tide_m_msl"],
            "tide_delta_from_target_m": round(
                float(selected["tide_level"])
                - selection["target_tide_m_msl"],
                4,
            ),
            "tide_status": selected["tide_status"],
            "tide_source_tier": selected["tide_source_tier"],
            "mndwi_threshold": round(float(threshold), 5),
            "threshold_method": method,
            "source_resolution_m": water_grid["resolution"],
            "interpretation": (
                "image-derived waterline selected at comparable predicted station "
                "tide; tide-screened, not tide-normalized or surveyed"
            ),
            "confidence": "LOW",
        }
        save_lines(output / "waterline" / f"{year}.geojson", waterline, water_properties)
        save_lines(
            web_output / "waterline" / f"{year}.geojson",
            waterline,
            water_properties,
        )
        waterline_qa.append(
            {
                "year": year,
                "scene_id": selected["scene_id"],
                "tide_level_m_msl": float(selected["tide_level"]),
                "mndwi_threshold": round(float(threshold), 5),
                "threshold_method": method,
                "valid_fraction": round(float(water_valid.mean()), 5),
                "waterline_length_m": round(float(waterline.length), 2),
                "threshold_candidates": json.dumps(
                    candidates, ensure_ascii=False, sort_keys=True
                ),
            }
        )

        composite, valid_count, grid = build_composite(
            sorted(
                year_rows[year],
                key=lambda item: item["acquisition_datetime_utc"],
            ),
            "sentinel2",
        )
        valid = valid_count > 0
        polygon, edge, area_ha = build_vegetation_proxy(
            composite, valid, grid, corridor_utm=corridor
        )
        vegetation_polygons[year] = polygon
        vegetation_edges[year] = edge
        vegetation_area_ha[year] = area_ha
        vegetation_properties = {
            "indicator": "MANGROVE_EDGE_PROXY",
            "role": "PRIMARY_SCREENING",
            "year": year,
            "ndvi_threshold": VEGETATION_NDVI_THRESHOLD,
            "scene_count": len(year_rows[year]),
            "scene_ids": ";".join(row["scene_id"] for row in year_rows[year]),
            "season_window": "January-April",
            "source_resolution_m": grid["resolution"],
            "classification": (
                "fixed NDVI vegetation proxy in project coastal context; "
                "not a validated mangrove inventory"
            ),
            "confidence": "LOW",
        }
        save_polygon(
            output / "mangrove_proxy" / f"{year}_polygon.geojson",
            polygon,
            vegetation_properties | {"area_ha": round(area_ha, 2)},
        )
        save_lines(
            output / "mangrove_proxy" / f"{year}_seaward_edge.geojson",
            edge,
            vegetation_properties,
        )
        save_polygon(
            web_output / "mangrove_proxy" / f"{year}_polygon.geojson",
            polygon,
            vegetation_properties | {"area_ha": round(area_ha, 2)},
        )
        save_lines(
            web_output / "mangrove_proxy" / f"{year}_seaward_edge.geojson",
            edge,
            vegetation_properties,
        )

    write_csv(output / "waterline_qa.csv", waterline_qa)

    transects = build_transects(waterlines[2026], oceans[2026], plots)
    if not transects:
        raise RuntimeError("no tide-aware project transects were generated")
    treatment_counts = Counter(
        row["plot_id"] for row in transects if row["plot_id"]
    )
    missing_plots = sorted(
        set(item["plot_id"] for item in plots).difference(treatment_counts)
    )

    positions: dict[tuple[str, str, int], float | None] = {}
    timeseries = []
    for transect in transects:
        for year in DEFAULT_YEARS:
            for indicator, geometry, mode in (
                (
                    "WATERLINE",
                    waterlines[year],
                    "nearest_reference",
                ),
                (
                    "MANGROVE_EDGE_PROXY",
                    vegetation_edges[year],
                    "seaward_most",
                ),
            ):
                position = position_on_transect(
                    transect, geometry, mode=mode
                )
                positions[(transect["transect_id"], indicator, year)] = position
                timeseries.append(
                    {
                        "transect_id": transect["transect_id"],
                        "role": transect["role"],
                        "plot_id": transect["plot_id"],
                        "indicator": indicator,
                        "year": year,
                        "position_m_relative_to_2026_waterline": position,
                        "tide_level_m_msl": (
                            float(selected_by_year[year]["tide_level"])
                            if indicator == "WATERLINE"
                            else None
                        ),
                        "tide_status": (
                            selected_by_year[year]["tide_status"]
                            if indicator == "WATERLINE"
                            else "not_applicable_to_fixed_ndvi_proxy"
                        ),
                        "confidence": "LOW",
                    }
                )
    write_csv(output / "indicator_timeseries.csv", timeseries)

    metrics = []
    for transect in transects:
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
            values = {
                year: positions[
                    (transect["transect_id"], indicator, year)
                ]
                for year in DEFAULT_YEARS
            }
            row = {
                "transect_id": transect["transect_id"],
                "role": transect["role"],
                "plot_id": transect["plot_id"],
                "indicator": indicator,
                **series_metrics(values),
                "position_2023_m": values[2023],
                "position_2024_m": values[2024],
                "position_2025_m": values[2025],
                "position_2026_m": values[2026],
                "confidence": "LOW",
            }
            first_2025 = values[2025]
            first_2023 = values[2023]
            row["nsm_2023_2025_m"] = (
                None
                if first_2023 is None or first_2025 is None
                else round(first_2025 - first_2023, 2)
            )
            metrics.append(row)
    write_csv(output / "transect_metrics.csv", metrics)

    controls = choose_candidate_controls(
        transects=transects,
        positions=positions,
        plots=plots,
    )
    write_csv(output / "candidate_controls.csv", controls)
    controls_by_plot: dict[str, list[str]] = defaultdict(list)
    for row in controls:
        controls_by_plot[row["plot_id"]].append(
            row["control_transect_id"]
        )

    screening_comparisons = []
    per_plot = []
    for plot in plots:
        plot_id = plot["plot_id"]
        treatment_ids = {
            row["transect_id"]
            for row in transects
            if row["plot_id"] == plot_id
        }
        control_ids = set(controls_by_plot.get(plot_id, []))
        indicator_results = {}
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
            treatment_rows = [
                row
                for row in metrics
                if row["indicator"] == indicator
                and row["transect_id"] in treatment_ids
            ]
            control_rows = [
                row
                for row in metrics
                if row["indicator"] == indicator
                and row["transect_id"] in control_ids
            ]
            treatment_nsm = median_or_none(
                row["nsm_2023_2026_m"] for row in treatment_rows
            )
            control_nsm = median_or_none(
                row["nsm_2023_2026_m"] for row in control_rows
            )
            difference = (
                None
                if treatment_nsm is None or control_nsm is None
                else round(treatment_nsm - control_nsm, 2)
            )
            screening_comparisons.append(
                {
                    "plot_id": plot_id,
                    "indicator": indicator,
                    "treatment_transect_count": len(treatment_rows),
                    "candidate_control_count": len(control_rows),
                    "treatment_median_nsm_2023_2026_m": treatment_nsm,
                    "control_median_nsm_2023_2026_m": control_nsm,
                    "screening_difference_m": difference,
                    "interpretation": (
                        "positive means project edge moved more seaward (or less "
                        "landward) than unverified nearby candidate controls; "
                        "not a causal estimate"
                    ),
                    "confidence": "LOW",
                }
            )
            indicator_results[indicator] = {
                "treatment_transect_count": len(treatment_rows),
                "candidate_control_count": len(control_rows),
                "median_nsm_2023_2026_m": treatment_nsm,
                "candidate_control_median_nsm_2023_2026_m": control_nsm,
                "screening_difference_m": difference,
                "class_counts": dict(
                    Counter(row["classification"] for row in treatment_rows)
                ),
            }
        per_plot.append(
            {
                "plot_id": plot_id,
                "official_participating_area_rai": plot[
                    "properties"
                ].get("official_participating_area_rai"),
                "waterline": indicator_results["WATERLINE"],
                "mangrove_edge_proxy": indicator_results[
                    "MANGROVE_EDGE_PROXY"
                ],
            }
        )
    write_csv(output / "screening_control_comparison.csv", screening_comparisons)

    transect_features = []
    selected_control_ids = {
        row["control_transect_id"] for row in controls
    }
    for transect in transects:
        props = {
            key: value
            for key, value in transect.items()
            if key not in {"geometry_utm", "centre_utm"}
        }
        props["selected_as_candidate_control"] = (
            transect["transect_id"] in selected_control_ids
        )
        transect_features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(
                    transform(TO_WEB.transform, transect["geometry_utm"])
                ),
            }
        )
    transect_collection = {
        "type": "FeatureCollection",
        "features": transect_features,
    }
    write_json(output / "transects.geojson", transect_collection)
    write_json(web_output / "transects.geojson", transect_collection)

    treatment_metrics = [
        row for row in metrics if row["role"] == "TREATMENT"
    ]
    tide_source_counts = Counter(
        row["tide_source_tier"] for row in selection["selected_rows"]
    )
    summary = {
        "title": (
            "Samut Songkhram tide-aware waterline and mangrove-edge screening"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "TIDE_AWARE_SCREENING",
        "erosion_effect_conclusion": "NOT_DEMONSTRATED",
        "allowed_claim_th": (
            "ผลดาวเทียมที่คัดตามระดับน้ำสนับสนุนการติดตามแนวโน้ม "
            "แต่ยังต้องตรวจด้วยโดรนหรือภาคสนาม"
        ),
        "plot_count": len(plots),
        "plot_ids": [item["plot_id"] for item in plots],
        "official_participating_area_rai": plot_collection["metadata"][
            "official_participating_area_rai"
        ],
        "years": list(DEFAULT_YEARS),
        "waterline_scene_selection": {
            "status": selection["status"],
            "criterion": (
                "one acquisition per year; minimum cross-year predicted-tide "
                "spread after requiring secondary interpolation brackets <=12 h"
            ),
            "target_tide_m_msl": selection["target_tide_m_msl"],
            "tide_spread_m": selection["tide_spread_m"],
            "maximum_delta_from_target_m": selection[
                "maximum_delta_from_target_m"
            ],
            "maximum_secondary_bracket_minutes": selection[
                "maximum_secondary_bracket_minutes"
            ],
            "source_tier_counts": dict(sorted(tide_source_counts.items())),
            "selected_scenes": [
                {
                    "year": year_of(row),
                    "date": row["acquisition_datetime_bangkok"][:10],
                    "scene_id": row["scene_id"],
                    "tide_level_m_msl": float(row["tide_level"]),
                    "tide_status": row["tide_status"],
                    "tide_source_tier": row["tide_source_tier"],
                    "secondary_bracket_span_minutes": parse_float(
                        row.get("tide_bracket_span_minutes")
                    ),
                }
                for row in selection["selected_rows"]
            ],
            "scientific_limit": (
                "Predicted station tide is matched, but the residual 0.345 m "
                "spread is not converted to horizontal distance because local "
                "intertidal slope and water-level observations are unavailable."
            ),
        },
        "indicators": {
            "waterline": {
                "role": "SUPPORTING_ONLY",
                "definition": (
                    "MNDWI image-derived waterline from one comparable-tide "
                    "Sentinel-2 acquisition per year"
                ),
                **aggregate_indicator(
                    treatment_metrics, indicator="WATERLINE"
                ),
            },
            "mangrove_edge_proxy": {
                "role": "PRIMARY_SCREENING",
                "definition": (
                    "seaward edge of fixed NDVI >=0.35 vegetation proxy from "
                    "January-April median Sentinel-2 composites"
                ),
                "area_ha_by_year": {
                    str(year): round(vegetation_area_ha[year], 2)
                    for year in DEFAULT_YEARS
                },
                **aggregate_indicator(
                    treatment_metrics,
                    indicator="MANGROVE_EDGE_PROXY",
                ),
            },
        },
        "transects": {
            "spacing_m": TRANSECT_SPACING_M,
            "half_length_m": TRANSECT_HALF_LENGTH_M,
            "total_count": len(transects),
            "treatment_count": sum(
                bool(item["plot_id"]) for item in transects
            ),
            "candidate_pool_count": sum(
                not item["plot_id"] for item in transects
            ),
            "treatment_count_by_plot": dict(sorted(treatment_counts.items())),
            "plots_without_treatment_transects": missing_plots,
            "position_convention": (
                "metres relative to the 2026 selected-scene waterline; "
                "positive is seaward"
            ),
            "screening_threshold_m": POSITIONAL_SCREENING_THRESHOLD_M,
        },
        "controls": {
            "status": "CANDIDATE_UNVERIFIED",
            "target_count_per_plot": TARGET_CONTROLS_PER_PLOT,
            "selected_count": len(controls),
            "selected_count_by_plot": dict(
                sorted(
                    (plot_id, len(values))
                    for plot_id, values in controls_by_plot.items()
                )
            ),
            "selection_basis": (
                "nearby transects outside a 150 m project exclusion buffer, "
                "matched on distance and 2023-2024 indicator movement"
            ),
            "unverified_factors": [
                "coastal structures",
                "dredging or reclamation",
                "other planting history",
                "field geomorphology",
            ],
        },
        "per_plot": per_plot,
        "screening_control_comparison": screening_comparisons,
        "limitations": [
            "วันปลูกและวันปลูกซ่อมรายแปลงยังไม่ได้รับการยืนยัน",
            (
                "ระดับน้ำปี 2023-2025 เป็นค่าประมาณระหว่างจุดน้ำขึ้นลงจากแหล่ง "
                "ทุติยภูมิที่ตรวจเทียบกับข้อมูลทางการปี 2026 แล้ว"
            ),
            (
                "WATERLINE เป็นการคัดภาพที่ระดับน้ำใกล้กัน ไม่ใช่การปรับแนวน้ำ "
                "ให้เป็นระดับอ้างอิงเดียวกัน"
            ),
            (
                "Sentinel-2 วิเคราะห์บนกริด 20 เมตร; การเปลี่ยนแปลงภายใน "
                "±20 เมตรไม่ควรตีความทิศทาง"
            ),
            (
                "MANGROVE_EDGE_PROXY เป็นขอบพืชจาก NDVI ไม่ใช่การจำแนก "
                "ป่าชายเลนที่ผ่าน confusion-matrix validation"
            ),
            (
                "candidate controls ยังไม่ได้ตรวจภาคสนามเรื่องโครงสร้าง "
                "การขุดลอก การถม และประวัติปลูก"
            ),
            (
                "ไม่มีระดับน้ำที่วัด ณ แปลง ไม่มี DEM ความลาดหาด และไม่มี "
                "แนวชายฝั่งจาก RTK/UAV สำหรับตรวจสอบความคลาดเคลื่อน"
            ),
        ],
        "source_data": {
            "plots": str(args.plots),
            "analysis_aoi": str(args.aoi),
            "tide_matched_catalog": str(args.catalog),
            "scene_selection_audit": str(
                args.output / "scene_selection_audit.csv"
            ),
        },
    }
    write_json(output / "summary.json", summary)
    write_json(web_output / "summary.json", summary)

    write_json(
        web_output / "index.json",
        {
            "years": list(DEFAULT_YEARS),
            "selected_imagery": {
                str(year): f"imagery/{year}_selected.webp"
                for year in DEFAULT_YEARS
            },
            "waterlines": {
                str(year): f"waterline/{year}.geojson"
                for year in DEFAULT_YEARS
            },
            "mangrove_proxy": {
                str(year): f"mangrove_proxy/{year}_polygon.geojson"
                for year in DEFAULT_YEARS
            },
            "transects": "transects.geojson",
        },
    )

    for name in (
        "scene_selection_audit.csv",
        "indicator_timeseries.csv",
        "transect_metrics.csv",
        "candidate_controls.csv",
        "screening_control_comparison.csv",
    ):
        source = output / name
        if source.exists():
            shutil.copy2(source, web_output / name)

    print(
        json.dumps(
            {
                "status": selection["status"],
                "selected_tide_spread_m": selection["tide_spread_m"],
                "transects": len(transects),
                "treatment_counts": dict(treatment_counts),
                "candidate_controls": len(controls),
                "plots_without_treatment_transects": missing_plots,
                "evidence_level": summary["evidence_level"],
                "erosion_effect_conclusion": summary[
                    "erosion_effect_conclusion"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
