#!/usr/bin/env python3
"""Build a tide-independent coastal vegetation-edge screening for Surat Thani 37-STC.

The primary signal is the seaward edge of persistent high-NDVI vegetation sampled on
fixed coast-normal transects. Sentinel-2 B4/B8 are used at 10 m, independently from
the MNDWI waterline. Three same-season scenes per year are cloud-masked with SCL and
combined as an annual median NDVI surface. Threshold and single-scene sensitivity are
reported explicitly.

This is a coastal-vegetation spectral proxy, not a species-classified mangrove survey.
It is intended to replace the waterline as the primary satellite screening indicator,
while field/UAV/orthophoto validation remains required for an impact claim.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/catalog/surat_thani_mvp_optical_scenes.csv"
TRANSECTS = ROOT / "data/processed/surat_thani/statistics/transect_summary.geojson"
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
CANDIDATES = ROOT / "data/analysis/surat_thani/control_candidates.json"
VERIFICATION = ROOT / "data/analysis/surat_thani/control_verification.json"

OUT_JSON = ROOT / "data/analysis/surat_thani/mangrove_edge_proxy_screening.json"
OUT_TRANSECTS = ROOT / "data/processed/surat_thani/statistics/coastal_vegetation_edge_transects.geojson"
OUT_POINTS = ROOT / "data/processed/surat_thani/statistics/coastal_vegetation_edge_points.geojson"
WEB_JSON = ROOT / "web/public/data/surat_thani/mangrove_edge_proxy_screening.json"
WEB_TRANSECTS = ROOT / "web/public/data/surat_thani/coastal_vegetation_edge_transects.geojson"
WEB_POINTS = ROOT / "web/public/data/surat_thani/coastal_vegetation_edge_points.geojson"
INTERNAL_WEB_JSON = ROOT / "data/processed/surat_thani/web/mangrove_edge_proxy_screening.json"
INTERNAL_WEB_TRANSECTS = ROOT / "data/processed/surat_thani/web/coastal_vegetation_edge_transects.geojson"
INTERNAL_WEB_POINTS = ROOT / "data/processed/surat_thani/web/coastal_vegetation_edge_points.geojson"

YEARS = list(range(2017, 2027))
PRE_YEARS = list(range(2017, 2024))
POST_YEARS = [2024, 2025, 2026]
THRESHOLDS = [0.28, 0.32, 0.36]
PRIMARY_THRESHOLD = 0.32
SAMPLE_STEP_M = 10.0
MIN_VEGETATED_RUN_M = 30.0
PROJECT_DISTANCE_M = 150.0
MIN_COMPOSITE_SCENES = 2
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fnum(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def med(values: list[float | None], digits: int = 3) -> float | None:
    vals = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return None if not vals else round(float(median(vals)), digits)


def percentile(values: list[float | None], q: float, digits: int = 2) -> float | None:
    vals = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return None if not vals else round(float(np.percentile(vals, q)), digits)


def catalog_rows() -> list[dict[str, str]]:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def band_paths(row: dict[str, str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for value in (row.get("local_path") or "").split(";"):
        if not value:
            continue
        path = ROOT / value
        key = path.name.split("_")[0].upper()
        out[key] = path
    return out


def year_rows(rows: list[dict[str, str]], year: int) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("dataset") != "sentinel2":
            continue
        dt = row.get("acquisition_datetime_utc", "")
        if not dt.startswith(f"{year}-"):
            continue
        try:
            month = int(dt[5:7])
        except ValueError:
            continue
        if month not in {2, 3, 4}:
            continue
        scene_id = row.get("scene_id", "")
        if not scene_id or scene_id in seen:
            continue
        paths = band_paths(row)
        if not all(key in paths and paths[key].exists() for key in ("B4", "B8", "SCL")):
            continue
        selected.append(row)
        seen.add(scene_id)
    selected.sort(key=lambda r: r.get("acquisition_datetime_utc", ""))
    return selected[:3]


def aligned_read(path: Path, ref: dict[str, Any], *, categorical: bool) -> np.ndarray:
    dtype = "uint16" if categorical else "float32"
    dst = np.zeros((ref["height"], ref["width"]), dtype=dtype)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=ref["transform"],
            dst_crs=ref["crs"],
            dst_nodata=0,
            resampling=Resampling.nearest if categorical else Resampling.bilinear,
        )
    return dst


def scene_ndvi(row: dict[str, str], ref: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    paths = band_paths(row)
    red = aligned_read(paths["B4"], ref, categorical=False)
    nir = aligned_read(paths["B8"], ref, categorical=False)
    scl = aligned_read(paths["SCL"], ref, categorical=True)
    # SCL: 0 no data, 1 saturated/defective, 3 cloud shadow, 8/9 cloud,
    # 10 cirrus, 11 snow/ice. Water is intentionally NOT masked: NDVI itself
    # defines the vegetation edge and avoids depending on the waterline model.
    valid = ~np.isin(scl, [0, 1, 3, 8, 9, 10, 11])
    valid &= (red > 0) & (nir > 0)
    denom = nir + red
    ndvi = np.divide(nir - red, denom, out=np.full_like(red, np.nan, dtype="float32"), where=np.abs(denom) > 1e-6)
    valid &= np.isfinite(ndvi) & (ndvi >= -1.0) & (ndvi <= 1.0)
    ndvi[~valid] = np.nan
    return ndvi.astype("float32"), valid


def build_year(rows: list[dict[str, str]], year: int) -> dict[str, Any]:
    selected = year_rows(rows, year)
    if len(selected) < 2:
        raise RuntimeError(f"{year}: only {len(selected)} usable downloaded Sentinel-2 scenes")
    first = band_paths(selected[0])["B4"]
    with rasterio.open(first) as src:
        ref = {
            "crs": src.crs,
            "transform": src.transform,
            "height": src.height,
            "width": src.width,
        }
    scene_arrays = []
    scene_meta = []
    for row in selected:
        ndvi_arr, valid = scene_ndvi(row, ref)
        scene_arrays.append(ndvi_arr)
        scene_meta.append({
            "scene_id": row.get("scene_id"),
            "acquisition_datetime_bangkok": row.get("acquisition_datetime_bangkok"),
            "cloud_cover_aoi": fnum(row.get("cloud_cover_aoi")),
            "ndvi": ndvi_arr,
            "valid": valid,
        })
    stack = np.stack(scene_arrays)
    valid_count = np.sum(np.isfinite(stack), axis=0).astype("uint8")
    with np.errstate(all="ignore"):
        composite = np.nanmedian(stack, axis=0).astype("float32")
    composite[valid_count < min(MIN_COMPOSITE_SCENES, len(selected))] = np.nan
    return {
        "year": year,
        "ref": ref,
        "composite": composite,
        "valid_count": valid_count,
        "scenes": scene_meta,
        "scene_ids": [r.get("scene_id") for r in selected],
        "dates": [r.get("acquisition_datetime_utc", "")[:10] for r in selected],
        "scene_count": len(selected),
        "composite_valid_fraction": round(float(np.isfinite(composite).mean()), 4),
    }


def sample_line(array: np.ndarray, line_utm: Any, transform_affine: Any, step_m: float) -> tuple[np.ndarray, np.ndarray]:
    if line_utm.length <= 0:
        return np.array([]), np.array([])
    distances = np.arange(0.0, line_utm.length + 0.001, step_m, dtype="float32")
    if not len(distances) or distances[-1] < line_utm.length:
        distances = np.append(distances, line_utm.length)
    xs = []
    ys = []
    for d in distances:
        p = line_utm.interpolate(float(d))
        xs.append(p.x)
        ys.append(p.y)
    rows, cols = rasterio.transform.rowcol(transform_affine, xs, ys)
    values = np.full(len(distances), np.nan, dtype="float32")
    h, w = array.shape
    for i, (r, c) in enumerate(zip(rows, cols)):
        if 0 <= r < h and 0 <= c < w:
            values[i] = array[r, c]
    return distances.astype("float64"), values


def edge_from_samples(distances: np.ndarray, values: np.ndarray, threshold: float) -> dict[str, Any] | None:
    if len(distances) < 4:
        return None
    finite = np.isfinite(values)
    veg = finite & (values >= threshold)
    # Close a single 10-m internal canopy/shadow gap but do not invent values
    # across broad invalid/cloud gaps.
    closed = ndimage.binary_closing(veg, structure=np.ones(3, dtype=bool))
    closed &= finite
    min_samples = max(2, int(math.ceil(MIN_VEGETATED_RUN_M / SAMPLE_STEP_M)))
    runs: list[tuple[int, int]] = []
    start = None
    for i, flag in enumerate(closed):
        if flag and start is None:
            start = i
        if start is not None and (not flag or i == len(closed) - 1):
            end = i if flag and i == len(closed) - 1 else i - 1
            if end - start + 1 >= min_samples:
                runs.append((start, end))
            start = None
    if not runs:
        return None
    # Transects are stored inland -> seaward. The seaward-most persistent
    # vegetated run is therefore the coastal vegetation edge candidate.
    start_i, end_i = max(runs, key=lambda pair: pair[1])
    if end_i >= len(distances) - 1:
        # Edge lies outside the transect; reject rather than report a censored edge.
        return None
    edge_m = float((distances[end_i] + distances[end_i + 1]) / 2.0)
    return {
        "edge_m_from_inland": edge_m,
        "run_start_m": float(distances[start_i]),
        "run_length_m": float(distances[end_i] - distances[start_i] + SAMPLE_STEP_M),
        "ndvi_last_vegetated_sample": fnum(values[end_i]),
        "ndvi_first_seaward_sample": fnum(values[end_i + 1]),
    }


def slope(positions: dict[str, float | None], years: list[int], minimum: int) -> float | None:
    pts = []
    for year in years:
        value = fnum(positions.get(str(year)))
        if value is not None:
            pts.append((year, value))
    if len(pts) < minimum:
        return None
    return float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0])


def group_summary(records: dict[str, dict[str, Any]], ids: list[str], threshold: float) -> dict[str, Any]:
    key = f"{threshold:.2f}"
    pre = []
    post = []
    net = []
    yearly_rel: dict[str, list[float]] = {str(y): [] for y in YEARS}
    observed = 0
    possible = len(ids) * len(YEARS)
    threshold_spreads = []
    scene_ranges = []
    used_ids = []
    for tid in ids:
        rec = records.get(tid)
        if not rec:
            continue
        used_ids.append(tid)
        positions = rec["threshold_positions_m"][key]
        s_pre = slope(positions, PRE_YEARS, 5)
        s_post = slope(positions, POST_YEARS, 3)
        if s_pre is not None:
            pre.append(s_pre)
        if s_post is not None:
            post.append(s_post)
        p23 = fnum(positions.get("2023"))
        p26 = fnum(positions.get("2026"))
        if p23 is not None and p26 is not None:
            net.append(p26 - p23)
        for year in YEARS:
            value = fnum(positions.get(str(year)))
            if value is not None:
                observed += 1
                if p23 is not None:
                    yearly_rel[str(year)].append(value - p23)
            spread = fnum(rec["threshold_spread_m_by_year"].get(str(year)))
            if spread is not None:
                threshold_spreads.append(spread)
            sr = fnum(rec["scene_edge_range_m_by_year"].get(str(year)))
            if sr is not None:
                scene_ranges.append(sr)
    med_pre = med(pre)
    med_post = med(post)
    return {
        "transect_count": len(used_ids),
        "transect_ids": used_ids,
        "observation_completeness": round(observed / possible, 3) if possible else None,
        "median_pre_2017_2023_slope_m_per_year": med_pre,
        "median_post_2024_2026_slope_m_per_year": med_post,
        "median_slope_change_post_minus_pre_m_per_year": None if med_pre is None or med_post is None else round(med_post - med_pre, 3),
        "median_change_2023_to_2026_m": med(net, 2),
        "yearly_median_edge_change_relative_to_2023_m": {year: med(vals, 2) for year, vals in yearly_rel.items()},
        "median_threshold_edge_spread_m": med(threshold_spreads, 2),
        "p90_threshold_edge_spread_m": percentile(threshold_spreads, 90),
        "median_single_scene_edge_range_m": med(scene_ranges, 2),
        "p90_single_scene_edge_range_m": percentile(scene_ranges, 90),
    }


def patch_index(path: Path) -> None:
    if not path.exists():
        return
    payload = load_json(path)
    payload.update({
        "primary_satellite_indicator": "coastal_vegetation_edge_proxy",
        "vegetation_edge_screening_file": "mangrove_edge_proxy_screening.json",
        "vegetation_edge_transects_file": "coastal_vegetation_edge_transects.geojson",
        "vegetation_edge_points_file": "coastal_vegetation_edge_points.geojson",
        "vegetation_edge_status": "10M_SENTINEL2_NDVI_SCREENING_WITH_THRESHOLD_AND_SCENE_SENSITIVITY",
        "waterline_role": "SUPPORTING_SENSITIVITY_CONTEXT_ONLY",
    })
    write_json(path, payload)


def main() -> int:
    verification = load_json(VERIFICATION)
    expected = "USER_CONFIRMED_NO_KNOWN_INTERVENTIONS_READY_FOR_COMPARATIVE_SCREENING"
    if verification.get("status") != expected:
        raise SystemExit(f"control verification not ready: {verification.get('status')}")

    rows = catalog_rows()
    annual = {year: build_year(rows, year) for year in YEARS}
    transforms = {str(data["ref"]["crs"]): Transformer.from_crs("EPSG:4326", data["ref"]["crs"], always_xy=True).transform for data in annual.values()}

    tr_fc = load_json(TRANSECTS)
    plot_fc = load_json(PLOT)
    candidates = load_json(CANDIDATES)
    plot = unary_union([shape(f["geometry"]) for f in plot_fc.get("features", [])])
    plot_utm = transform(TO_UTM, plot)

    control_ids: list[str] = []
    control_rank_by_id: dict[str, int] = {}
    for candidate in candidates.get("candidates", []):
        rank = int(candidate.get("rank"))
        for tid in candidate.get("transect_ids", []):
            if tid not in control_ids:
                control_ids.append(tid)
            control_rank_by_id[tid] = rank

    records: dict[str, dict[str, Any]] = {}
    project_ids: list[str] = []
    transect_features: list[dict[str, Any]] = []
    point_features: list[dict[str, Any]] = []

    for feature in tr_fc.get("features", []):
        props = feature.get("properties", {})
        tid = props.get("transect_id")
        if not tid:
            continue
        line_web = shape(feature["geometry"])
        line_utm = transform(TO_UTM, line_web)
        project_distance = float(line_utm.distance(plot_utm))
        is_project = project_distance <= PROJECT_DISTANCE_M
        is_control = tid in control_ids
        if is_project:
            project_ids.append(tid)

        threshold_positions = {f"{t:.2f}": {} for t in THRESHOLDS}
        threshold_spread: dict[str, float | None] = {}
        scene_range: dict[str, float | None] = {}
        scene_median: dict[str, float | None] = {}
        primary_detail: dict[str, Any] = {}

        for year in YEARS:
            data = annual[year]
            tx = transforms[str(data["ref"]["crs"])]
            line_grid = transform(tx, line_web)
            distances, values = sample_line(data["composite"], line_grid, data["ref"]["transform"], SAMPLE_STEP_M)
            year_edges: dict[float, dict[str, Any] | None] = {}
            for threshold in THRESHOLDS:
                edge = edge_from_samples(distances, values, threshold)
                year_edges[threshold] = edge
                threshold_positions[f"{threshold:.2f}"][str(year)] = None if edge is None else round(float(edge["edge_m_from_inland"]), 2)
            edge_vals = [e["edge_m_from_inland"] for e in year_edges.values() if e is not None]
            threshold_spread[str(year)] = None if len(edge_vals) < 2 else round(max(edge_vals) - min(edge_vals), 2)
            primary_detail[str(year)] = year_edges[PRIMARY_THRESHOLD]

            single_edges = []
            for scene in data["scenes"]:
                sd, sv = sample_line(scene["ndvi"], line_grid, data["ref"]["transform"], SAMPLE_STEP_M)
                se = edge_from_samples(sd, sv, PRIMARY_THRESHOLD)
                if se is not None:
                    single_edges.append(float(se["edge_m_from_inland"]))
            scene_range[str(year)] = None if len(single_edges) < 2 else round(max(single_edges) - min(single_edges), 2)
            scene_median[str(year)] = med(single_edges, 2)

        primary_positions = threshold_positions[f"{PRIMARY_THRESHOLD:.2f}"]
        p2023 = fnum(primary_positions.get("2023"))
        rel = {
            str(year): None if p2023 is None or fnum(primary_positions.get(str(year))) is None else round(float(primary_positions[str(year)]) - p2023, 2)
            for year in YEARS
        }
        records[tid] = {
            "transect_id": tid,
            "chainage_m": props.get("chainage_m"),
            "project_frontage": is_project,
            "distance_to_pdd_m": round(project_distance, 2),
            "control_rank": control_rank_by_id.get(tid),
            "threshold_positions_m": threshold_positions,
            "primary_edge_change_relative_2023_m": rel,
            "threshold_spread_m_by_year": threshold_spread,
            "scene_edge_range_m_by_year": scene_range,
            "single_scene_median_edge_m_by_year": scene_median,
            "primary_edge_detail": primary_detail,
        }

        if not (is_project or is_control):
            continue
        group = "PROJECT_37_STC" if is_project else f"CONTROL_RANK_{control_rank_by_id.get(tid)}"
        copied = json.loads(json.dumps(feature))
        cp = copied.setdefault("properties", {})
        cp.update({
            "analysis_group": group,
            "vegetation_edge_proxy": True,
            "ndvi_primary_threshold": PRIMARY_THRESHOLD,
            "edge_positions_m_from_inland": primary_positions,
            "edge_change_relative_2023_m": rel,
            "threshold_spread_m_by_year": threshold_spread,
            "single_scene_edge_range_m_by_year": scene_range,
            "interpretation": "seaward edge of persistent high-NDVI coastal vegetation; not species-classified mangrove survey",
        })
        transect_features.append(copied)

        for year in YEARS:
            edge_m = fnum(primary_positions.get(str(year)))
            if edge_m is None or line_utm.length <= 0:
                continue
            fraction = min(1.0, max(0.0, edge_m / line_utm.length))
            point = line_web.interpolate(fraction, normalized=True)
            point_features.append({
                "type": "Feature",
                "properties": {
                    "transect_id": tid,
                    "group": group,
                    "year": year,
                    "edge_position_m_from_inland": round(edge_m, 2),
                    "edge_change_relative_2023_m": rel[str(year)],
                    "ndvi_threshold": PRIMARY_THRESHOLD,
                    "threshold_spread_m": threshold_spread[str(year)],
                    "single_scene_edge_range_m": scene_range[str(year)],
                    "source_scene_ids": annual[year]["scene_ids"],
                    "source_dates": annual[year]["dates"],
                },
                "geometry": mapping(Point(point.x, point.y)),
            })

    project_ids = sorted(set(project_ids))
    if len(project_ids) < 10:
        raise SystemExit(f"only {len(project_ids)} project-frontage transects")
    if len(control_ids) != 15:
        raise SystemExit(f"expected 15 control transects, got {len(control_ids)}")

    threshold_results: dict[str, Any] = {}
    net_contrasts = []
    slope_contrasts = []
    for threshold in THRESHOLDS:
        project = group_summary(records, project_ids, threshold)
        controls = group_summary(records, control_ids, threshold)
        pnet = project["median_change_2023_to_2026_m"]
        cnet = controls["median_change_2023_to_2026_m"]
        ps = project["median_slope_change_post_minus_pre_m_per_year"]
        cs = controls["median_slope_change_post_minus_pre_m_per_year"]
        net_contrast = None if pnet is None or cnet is None else round(pnet - cnet, 2)
        slope_contrast = None if ps is None or cs is None else round(ps - cs, 3)
        threshold_results[f"{threshold:.2f}"] = {
            "project_frontage": project,
            "pooled_controls": controls,
            "project_minus_control_change_2023_2026_m": net_contrast,
            "project_minus_control_slope_change_m_per_year": slope_contrast,
        }
        if net_contrast is not None:
            net_contrasts.append(net_contrast)
        if slope_contrast is not None:
            slope_contrasts.append(slope_contrast)

    primary = threshold_results[f"{PRIMARY_THRESHOLD:.2f}"]
    signs = {0 if abs(x) < 1e-9 else (1 if x > 0 else -1) for x in net_contrasts}
    sign_consistency = "CONSISTENT_POSITIVE" if signs == {1} else "CONSISTENT_NEGATIVE" if signs == {-1} else "MIXED_OR_ZERO"
    empirical_components = [
        fnum(primary["project_frontage"].get("median_threshold_edge_spread_m")),
        fnum(primary["project_frontage"].get("median_single_scene_edge_range_m")),
        10.0,
    ]
    empirical_instability = round(max(v for v in empirical_components if v is not None), 2)

    if sign_consistency == "CONSISTENT_POSITIVE":
        robustness_note = "Project-minus-control 2023-2026 vegetation-edge change is positive across all tested NDVI thresholds."
    elif sign_consistency == "CONSISTENT_NEGATIVE":
        robustness_note = "Project-minus-control 2023-2026 vegetation-edge change is negative across all tested NDVI thresholds."
    else:
        robustness_note = "Project-minus-control sign changes or reaches zero across tested NDVI thresholds; interpretation is threshold-sensitive."

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "representative_intervention_date": "2023-10-18",
        "analysis_role": "PRIMARY_SATELLITE_COASTAL_VEGETATION_EDGE_SCREENING",
        "indicator": {
            "name": "coastal_vegetation_edge_proxy",
            "preferred_interpretation": "seaward edge of persistent high-NDVI coastal vegetation",
            "not_claimed": "not a species-classified mangrove inventory and not a field-surveyed vegetation edge",
            "sensor": "Sentinel-2 L2A B4/B8",
            "native_analysis_resolution_m": 10,
            "annual_composite": "median NDVI from up to three cloud-masked February-April scenes",
            "cloud_mask": "Sentinel-2 SCL excludes no-data, saturated/defective, cloud shadow, medium/high cloud, cirrus, snow/ice",
            "primary_ndvi_threshold": PRIMARY_THRESHOLD,
            "tested_thresholds": THRESHOLDS,
            "sample_step_m": SAMPLE_STEP_M,
            "minimum_persistent_vegetated_run_m": MIN_VEGETATED_RUN_M,
            "edge_rule": "seaward-most persistent vegetated run on each fixed inland-to-seaward transect",
            "tide_dependency": "NONE_EXPLICIT; water mask/waterline is not used in edge detection",
        },
        "annual_inputs": {
            str(year): {
                "scene_count": annual[year]["scene_count"],
                "dates": annual[year]["dates"],
                "scene_ids": annual[year]["scene_ids"],
                "composite_valid_fraction": annual[year]["composite_valid_fraction"],
            }
            for year in YEARS
        },
        "groups": {
            "project_frontage_transect_count": len(project_ids),
            "project_frontage_transect_ids": project_ids,
            "control_transect_count": len(control_ids),
            "control_transect_ids": control_ids,
            "control_verification_status": verification.get("status"),
        },
        "threshold_results": threshold_results,
        "primary_result": primary,
        "robustness": {
            "net_contrast_sign_across_thresholds": sign_consistency,
            "net_contrast_values_m": net_contrasts,
            "slope_change_contrast_values_m_per_year": slope_contrasts,
            "net_contrast_range_m": None if not net_contrasts else [round(min(net_contrasts), 2), round(max(net_contrasts), 2)],
            "empirical_edge_instability_floor_m": empirical_instability,
            "empirical_edge_instability_definition": "max of 10 m native pixel size, project median threshold edge spread, and project median single-scene edge range",
            "note": robustness_note,
        },
        "evidence_status": {
            "waterline_role": "SUPPORTING_SENSITIVITY_CONTEXT_ONLY",
            "vegetation_edge_role": "PRIMARY_SATELLITE_SCREENING_INDICATOR",
            "known_control_intervention_exclusion": "USER_CONFIRMED",
            "control_physical_setting": "SATELLITE_SCREENED_NOT_FIELD_VERIFIED",
            "field_or_uav_validation": "PENDING",
            "species_classification": "NOT_AVAILABLE_FROM_THIS_10M_NDVI_METHOD",
            "claim_status": "VEGETATION_EDGE_COMPARATIVE_SCREENING_ONLY_NOT_CAUSAL_IMPACT_CLAIM",
        },
        "interpretation_limits": [
            "A positive seaward vegetation-edge signal can be consistent with vegetation establishment but does not by itself prove that planted mangroves caused erosion reduction.",
            "Young or sparse seedlings may occupy less than a 10 m Sentinel-2 pixel and can be missed even when alive.",
            "NDVI can respond to canopy density, phenology, wet background and mixed pixels; threshold and scene sensitivity are therefore reported.",
            "Use UAV/field/orthophoto evidence to confirm that the detected edge is mangrove and to validate sub-pixel or sparse planting areas.",
        ],
    }

    fc_tr = {"type": "FeatureCollection", "features": transect_features}
    fc_pt = {"type": "FeatureCollection", "features": point_features}
    for path in [OUT_JSON, WEB_JSON, INTERNAL_WEB_JSON]:
        write_json(path, payload)
    for path in [OUT_TRANSECTS, WEB_TRANSECTS, INTERNAL_WEB_TRANSECTS]:
        write_json(path, fc_tr)
    for path in [OUT_POINTS, WEB_POINTS, INTERNAL_WEB_POINTS]:
        write_json(path, fc_pt)
    for path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        patch_index(path)

    print(json.dumps({
        "project_transects": len(project_ids),
        "control_transects": len(control_ids),
        "primary": primary,
        "robustness": payload["robustness"],
        "point_features": len(point_features),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
