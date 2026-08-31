#!/usr/bin/env python3
"""Assess vegetation establishment inside 37-STC versus no-known-intervention controls.

This complements the coastal vegetation-edge analysis. It measures annual 10 m Sentinel-2
NDVI inside the current 157.55-rai PDD polygon and inside three pseudo-project control
windows derived from the verified control transects. Control windows use the median
cross-shore span of the PDD where it intersects project-frontage transects, so the
comparison samples a broadly similar coastal-depth band rather than arbitrary buffers.

The result is a planting-establishment screening signal, not an erosion-impact claim.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import rasterio.features
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform, unary_union

import build_surat_thani_vegetation_edge_screening as veg

ROOT = Path(__file__).resolve().parents[1]
TRANSECTS = ROOT / "data/processed/surat_thani/statistics/transect_summary.geojson"
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
CANDIDATES = ROOT / "data/analysis/surat_thani/control_candidates.json"
VERIFICATION = ROOT / "data/analysis/surat_thani/control_verification.json"

OUT = ROOT / "data/analysis/surat_thani/planting_establishment_screening.json"
OUT_WINDOWS = ROOT / "data/analysis/surat_thani/vegetation_control_windows.geojson"
WEB = ROOT / "web/public/data/surat_thani/planting_establishment_screening.json"
WEB_WINDOWS = ROOT / "web/public/data/surat_thani/vegetation_control_windows.geojson"
INTERNAL_WEB = ROOT / "data/processed/surat_thani/web/planting_establishment_screening.json"
INTERNAL_WINDOWS = ROOT / "data/processed/surat_thani/web/vegetation_control_windows.geojson"

YEARS = list(range(2017, 2027))
PRE_YEARS = list(range(2017, 2024))
POST_YEARS = [2024, 2025, 2026]
THRESHOLDS = veg.THRESHOLDS
PRIMARY_THRESHOLD = veg.PRIMARY_THRESHOLD
PROJECT_DISTANCE_M = 150.0
CONTROL_HALF_SPACING_BUFFER_M = 55.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fnum(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def med(values: list[float | None], digits: int = 4) -> float | None:
    vals = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return None if not vals else round(float(median(vals)), digits)


def slope(values: dict[str, float | None], years: list[int], minimum: int) -> float | None:
    pts = []
    for year in years:
        value = fnum(values.get(str(year)))
        if value is not None:
            pts.append((year, value))
    if len(pts) < minimum:
        return None
    return float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0])


def line_interval(line: Any, polygon: Any) -> tuple[float, float] | None:
    inter = line.intersection(polygon)
    if inter.is_empty:
        return None
    points: list[Point] = []

    def collect(g: Any) -> None:
        if g.is_empty:
            return
        if g.geom_type == "Point":
            points.append(g)
        elif g.geom_type in {"LineString", "LinearRing"}:
            coords = list(g.coords)
            if coords:
                points.extend([Point(coords[0]), Point(coords[-1])])
        elif hasattr(g, "geoms"):
            for child in g.geoms:
                collect(child)

    collect(inter)
    if not points:
        return None
    distances = sorted(float(line.project(p)) for p in points)
    if distances[-1] - distances[0] < 20:
        return None
    return distances[0], distances[-1]


def control_windows(tr_fc: dict[str, Any], plot_utm: Any, candidates: dict[str, Any]) -> tuple[dict[int, Any], dict[str, float]]:
    by_id = {f.get("properties", {}).get("transect_id"): f for f in tr_fc.get("features", [])}
    intervals = []
    for feature in tr_fc.get("features", []):
        line = transform(TO_UTM, shape(feature["geometry"]))
        if float(line.distance(plot_utm)) > PROJECT_DISTANCE_M:
            continue
        interval = line_interval(line, plot_utm)
        if interval is not None:
            intervals.append(interval)
    if len(intervals) < 3:
        raise RuntimeError(f"only {len(intervals)} project/PDD intersection intervals")
    inland_m = float(median([x[0] for x in intervals]))
    seaward_m = float(median([x[1] for x in intervals]))
    if seaward_m <= inland_m + 20:
        raise RuntimeError("invalid median project cross-shore interval")

    windows: dict[int, Any] = {}
    for candidate in candidates.get("candidates", []):
        rank = int(candidate["rank"])
        strips = []
        for tid in candidate.get("transect_ids", []):
            feature = by_id.get(tid)
            if not feature:
                raise RuntimeError(f"missing control transect {tid}")
            line = transform(TO_UTM, shape(feature["geometry"]))
            a = min(max(inland_m, 0.0), line.length)
            b = min(max(seaward_m, 0.0), line.length)
            if b <= a:
                continue
            segment = LineString([line.interpolate(a), line.interpolate(b)])
            strips.append(segment.buffer(CONTROL_HALF_SPACING_BUFFER_M, cap_style="flat"))
        if not strips:
            raise RuntimeError(f"no strips for control rank {rank}")
        windows[rank] = unary_union(strips).buffer(0)
    return windows, {
        "median_project_interval_from_inland_m": round(inland_m, 1),
        "median_project_interval_to_seaward_m": round(seaward_m, 1),
        "median_project_cross_shore_span_m": round(seaward_m - inland_m, 1),
        "project_intersecting_transects_used": len(intervals),
    }


def raster_values(array: np.ndarray, geom_utm: Any, ref: dict[str, Any]) -> np.ndarray:
    mask = rasterio.features.geometry_mask(
        [mapping(geom_utm)],
        out_shape=(ref["height"], ref["width"]),
        transform=ref["transform"],
        invert=True,
    )
    vals = array[mask & np.isfinite(array)]
    return vals.astype("float64")


def metrics(array: np.ndarray, geom_utm: Any, ref: dict[str, Any]) -> dict[str, Any]:
    vals = raster_values(array, geom_utm, ref)
    if not len(vals):
        return {"valid_pixel_count": 0, "median_ndvi": None, "mean_ndvi": None, "p25_ndvi": None, "p75_ndvi": None, "p90_ndvi": None, "green_fraction": {f"{t:.2f}": None for t in THRESHOLDS}}
    return {
        "valid_pixel_count": int(len(vals)),
        "median_ndvi": round(float(np.median(vals)), 4),
        "mean_ndvi": round(float(np.mean(vals)), 4),
        "p25_ndvi": round(float(np.percentile(vals, 25)), 4),
        "p75_ndvi": round(float(np.percentile(vals, 75)), 4),
        "p90_ndvi": round(float(np.percentile(vals, 90)), 4),
        "green_fraction": {f"{t:.2f}": round(float(np.mean(vals >= t)), 4) for t in THRESHOLDS},
    }


def annual_group_metrics(annual: dict[int, dict[str, Any]], geom_utm: Any) -> dict[str, Any]:
    out = {}
    for year, data in annual.items():
        composite_metrics = metrics(data["composite"], geom_utm, data["ref"])
        scene_medians = []
        scene_green = []
        for scene in data["scenes"]:
            sm = metrics(scene["ndvi"], geom_utm, data["ref"])
            if sm["median_ndvi"] is not None:
                scene_medians.append(float(sm["median_ndvi"]))
            gf = sm["green_fraction"].get(f"{PRIMARY_THRESHOLD:.2f}")
            if gf is not None:
                scene_green.append(float(gf))
        composite_metrics["single_scene_median_ndvi_range"] = None if len(scene_medians) < 2 else round(max(scene_medians) - min(scene_medians), 4)
        composite_metrics["single_scene_green_fraction_range"] = None if len(scene_green) < 2 else round(max(scene_green) - min(scene_green), 4)
        out[str(year)] = composite_metrics
    return out


def series(group: dict[str, Any], field: str, threshold: float | None = None) -> dict[str, float | None]:
    result = {}
    for year in YEARS:
        item = group[str(year)]
        if field == "green_fraction":
            result[str(year)] = fnum(item[field].get(f"{threshold:.2f}")) if threshold is not None else None
        else:
            result[str(year)] = fnum(item.get(field))
    return result


def change_vs_2023(values: dict[str, float | None]) -> dict[str, float | None]:
    base = fnum(values.get("2023"))
    return {
        str(year): None if base is None or fnum(values.get(str(year))) is None else round(float(values[str(year)]) - base, 4)
        for year in YEARS
    }


def compare_series(project: dict[str, Any], controls: dict[str, Any], field: str, threshold: float | None = None) -> dict[str, Any]:
    p = series(project, field, threshold)
    c = series(controls, field, threshold)
    pc = change_vs_2023(p)
    cc = change_vs_2023(c)
    did = {
        str(year): None if pc[str(year)] is None or cc[str(year)] is None else round(pc[str(year)] - cc[str(year)], 4)
        for year in YEARS
    }
    p_pre = slope(p, PRE_YEARS, 5)
    c_pre = slope(c, PRE_YEARS, 5)
    p_post = slope(p, POST_YEARS, 3)
    c_post = slope(c, POST_YEARS, 3)
    return {
        "project_values": p,
        "control_values": c,
        "project_change_from_2023": pc,
        "control_change_from_2023": cc,
        "project_minus_control_change_from_2023": did,
        "project_pre_2017_2023_slope_per_year": None if p_pre is None else round(p_pre, 5),
        "control_pre_2017_2023_slope_per_year": None if c_pre is None else round(c_pre, 5),
        "project_post_2024_2026_slope_per_year": None if p_post is None else round(p_post, 5),
        "control_post_2024_2026_slope_per_year": None if c_post is None else round(c_post, 5),
        "difference_in_differences_2026_vs_2023": did.get("2026"),
    }


def patch_index(path: Path) -> None:
    if not path.exists():
        return
    payload = load(path)
    payload.update({
        "planting_establishment_screening_file": "planting_establishment_screening.json",
        "vegetation_control_windows_file": "vegetation_control_windows.geojson",
        "planting_establishment_status": "10M_SENTINEL2_NDVI_PROJECT_VS_USER_CONFIRMED_CONTROLS",
    })
    write(path, payload)


def main() -> int:
    verification = load(VERIFICATION)
    expected = "USER_CONFIRMED_NO_KNOWN_INTERVENTIONS_READY_FOR_COMPARATIVE_SCREENING"
    if verification.get("status") != expected:
        raise SystemExit(f"control verification not ready: {verification.get('status')}")

    rows = veg.catalog_rows()
    annual = {year: veg.build_year(rows, year) for year in YEARS}
    tr_fc = load(TRANSECTS)
    plot_fc = load(PLOT)
    candidates = load(CANDIDATES)
    plot_web = unary_union([shape(f["geometry"]) for f in plot_fc.get("features", [])])
    plot_utm = transform(TO_UTM, plot_web)
    windows, window_design = control_windows(tr_fc, plot_utm, candidates)
    pooled_controls = unary_union(list(windows.values())).buffer(0)

    project_metrics = annual_group_metrics(annual, plot_utm)
    control_metrics_by_rank = {str(rank): annual_group_metrics(annual, geom) for rank, geom in windows.items()}
    pooled_metrics = annual_group_metrics(annual, pooled_controls)

    median_comparison = compare_series(project_metrics, pooled_metrics, "median_ndvi")
    threshold_comparisons = {
        f"{threshold:.2f}": compare_series(project_metrics, pooled_metrics, "green_fraction", threshold)
        for threshold in THRESHOLDS
    }
    green_dids = [
        fnum(v.get("difference_in_differences_2026_vs_2023"))
        for v in threshold_comparisons.values()
    ]
    green_dids = [x for x in green_dids if x is not None]
    signs = {0 if abs(x) < 1e-12 else (1 if x > 0 else -1) for x in green_dids}
    green_sign = "CONSISTENT_POSITIVE" if signs == {1} else "CONSISTENT_NEGATIVE" if signs == {-1} else "MIXED_OR_ZERO"

    ndvi_did = fnum(median_comparison.get("difference_in_differences_2026_vs_2023"))
    primary_green_did = fnum(threshold_comparisons[f"{PRIMARY_THRESHOLD:.2f}"].get("difference_in_differences_2026_vs_2023"))
    if ndvi_did is not None and primary_green_did is not None and ndvi_did > 0 and primary_green_did > 0 and green_sign == "CONSISTENT_POSITIVE":
        establishment_signal = "POSITIVE_PROJECT_RELATIVE_VEGETATION_ESTABLISHMENT_SIGNAL"
    elif ndvi_did is not None and primary_green_did is not None and ndvi_did < 0 and primary_green_did < 0 and green_sign == "CONSISTENT_NEGATIVE":
        establishment_signal = "NEGATIVE_PROJECT_RELATIVE_VEGETATION_SIGNAL"
    else:
        establishment_signal = "MIXED_OR_THRESHOLD_SENSITIVE_VEGETATION_SIGNAL"

    window_features = []
    for rank, geom in windows.items():
        window_features.append({
            "type": "Feature",
            "properties": {
                "control_rank": rank,
                "role": "PSEUDO_PROJECT_VEGETATION_COMPARISON_WINDOW",
                "area_ha": round(float(geom.area / 10000), 2),
                "user_confirmed_no_known_intervention": True,
                "design": window_design,
            },
            "geometry": mapping(transform(Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True).transform, geom)),
        })

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "analysis_role": "PLANTING_ESTABLISHMENT_SCREENING_NOT_EROSION_IMPACT",
        "representative_intervention_date": "2023-10-18",
        "spatial_design": {
            "project_geometry": "current PDD / SHP PDD 157.55 rai",
            "project_area_ha": round(float(plot_utm.area / 10000), 2),
            "control_window_design": window_design,
            "control_window_areas_ha": {str(rank): round(float(geom.area / 10000), 2) for rank, geom in windows.items()},
            "pooled_control_area_ha": round(float(pooled_controls.area / 10000), 2),
            "control_verification_status": verification.get("status"),
        },
        "indicator": {
            "sensor": "Sentinel-2 L2A",
            "resolution_m": 10,
            "annual_period": "February-April",
            "annual_composite": "median of cloud-masked scene NDVI",
            "median_ndvi": "continuous greenness/density proxy",
            "green_fraction_thresholds": THRESHOLDS,
            "primary_green_fraction_threshold": PRIMARY_THRESHOLD,
            "young_seedling_limit": "Sparse seedlings below pixel-scale canopy occupancy can remain undetected even if alive.",
        },
        "project_annual_metrics": project_metrics,
        "control_annual_metrics_by_rank": control_metrics_by_rank,
        "pooled_control_annual_metrics": pooled_metrics,
        "comparisons": {
            "median_ndvi": median_comparison,
            "green_fraction": threshold_comparisons,
        },
        "robustness": {
            "green_fraction_2026_vs_2023_did_sign_across_thresholds": green_sign,
            "green_fraction_2026_vs_2023_did_values": green_dids,
            "median_ndvi_2026_vs_2023_did": ndvi_did,
            "primary_green_fraction_2026_vs_2023_did": primary_green_did,
            "establishment_signal": establishment_signal,
        },
        "evidence_status": {
            "project_boundary": "USER_SUPPLIED_CURRENT_PDD",
            "control_intervention_exclusion": "USER_CONFIRMED",
            "control_spatial_comparability": "PSEUDO_WINDOWS_MATCH_PROJECT_CROSS_SHORE_DEPTH_BUT_NOT_FIELD_VERIFIED",
            "field_or_uav_validation": "PENDING",
            "claim_status": "VEGETATION_ESTABLISHMENT_SCREENING_ONLY_NOT_CAUSAL_EROSION_CLAIM",
        },
        "interpretation_limits": [
            "This analysis asks whether vegetation greenness/occupancy inside the planted PDD changed relative to nearby no-known-intervention coastal windows; it does not measure shoreline protection directly.",
            "A positive relative vegetation signal can support establishment monitoring but cannot prove survival counts, species identity, or erosion reduction.",
            "A weak signal does not prove planting failure because young/sparse seedlings can be sub-pixel at 10 m.",
            "UAV or field observations should validate canopy occupancy and survival where possible.",
        ],
    }

    fc = {"type": "FeatureCollection", "features": window_features}
    for path in [OUT, WEB, INTERNAL_WEB]:
        write(path, payload)
    for path in [OUT_WINDOWS, WEB_WINDOWS, INTERNAL_WINDOWS]:
        write(path, fc)
    for path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        patch_index(path)

    print(json.dumps({
        "project_area_ha": payload["spatial_design"]["project_area_ha"],
        "control_window_areas_ha": payload["spatial_design"]["control_window_areas_ha"],
        "median_ndvi_did_2026_vs_2023": ndvi_did,
        "green_fraction_did_primary": primary_green_did,
        "green_threshold_sign": green_sign,
        "establishment_signal": establishment_signal,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
