#!/usr/bin/env python3
"""Build a conservative Sentinel-1 GRD relative project-vs-control diagnostic for 37-STC.

This is deliberately *not* an absolute SAR biomass or mangrove classifier. The Planetary
Computer collection used by the existing project downloader is Sentinel-1 Level-1 GRD,
not the precomputed radiometrically terrain-corrected collection. We therefore avoid
interpreting absolute backscatter. Instead, for a single repeated relative-orbit family,
we compare the project PDD with nearby verified no-known-intervention control windows
inside each same acquisition and track changes in within-scene project-minus-control
log backscatter and VH/VV log-ratio.

Because project and controls are only a few kilometres apart and share the same scene,
this cancels many scene-wide acquisition factors. It remains an independent corroboration
check only; it cannot replace calibrated RTC processing, optical/UAV validation, or field
survival evidence.
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
import rasterio.features
import requests
from pyproj import Transformer
from rasterio.warp import Resampling, reproject
from shapely.geometry import shape
from shapely.ops import transform, unary_union

import build_surat_thani_planting_establishment_screening as est

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/catalog/surat_thani_s1_corroboration_scenes.csv"
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
TRANSECTS = ROOT / "data/processed/surat_thani/statistics/transect_summary.geojson"
CANDIDATES = ROOT / "data/analysis/surat_thani/control_candidates.json"
VERIFICATION = ROOT / "data/analysis/surat_thani/control_verification.json"
OUT = ROOT / "data/analysis/surat_thani/s1_relative_corroboration.json"
WEB = ROOT / "web/public/data/surat_thani/s1_relative_corroboration.json"
INTERNAL_WEB = ROOT / "data/processed/surat_thani/web/s1_relative_corroboration.json"
YEARS = [2023, 2024, 2025, 2026]
MAX_SCENES_PER_YEAR = 3
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


def paths_by_band(row: dict[str, str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for value in (row.get("local_path") or "").split(";"):
        if not value:
            continue
        path = ROOT / value
        out[path.name.split("_")[0].upper()] = path
    return out


def catalog_rows() -> list[dict[str, str]]:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    usable = []
    for row in rows:
        if row.get("dataset") != "sentinel1":
            continue
        year = int(row.get("acquisition_datetime_utc", "0000")[:4] or 0)
        if year not in YEARS:
            continue
        paths = paths_by_band(row)
        if all(key in paths and paths[key].exists() for key in ("VV", "VH")):
            usable.append(row)
    return usable


def metadata(row: dict[str, str]) -> dict[str, Any]:
    source = row.get("source_url") or ""
    props: dict[str, Any] = {}
    status = "NOT_FETCHED"
    if source:
        try:
            response = requests.get(source, timeout=45)
            response.raise_for_status()
            props = response.json().get("properties", {})
            status = "STAC_ITEM_FETCHED"
        except Exception as exc:
            status = f"STAC_ITEM_FETCH_FAILED:{type(exc).__name__}"
    bkk = row.get("acquisition_datetime_bangkok", "")
    hour_family = None
    try:
        hour_family = int(bkk[11:13])
    except Exception:
        pass
    orbit_state = props.get("sat:orbit_state") or props.get("sar:observation_direction")
    relative_orbit = props.get("sat:relative_orbit")
    track_key = (
        f"{orbit_state}:{relative_orbit}"
        if orbit_state is not None and relative_orbit is not None
        else f"LOCAL_HOUR_FAMILY:{hour_family}"
    )
    return {
        "track_key": track_key,
        "orbit_state": orbit_state,
        "relative_orbit": relative_orbit,
        "local_hour_family": hour_family,
        "metadata_status": status,
    }


def choose_track(rows: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    enriched = []
    for row in rows:
        item = dict(row)
        item.update(metadata(row))
        enriched.append(item)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in enriched:
        groups.setdefault(str(row["track_key"]), []).append(row)
    scored = []
    for key, group in groups.items():
        counts = {year: sum(r.get("acquisition_datetime_utc", "").startswith(f"{year}-") for r in group) for year in YEARS}
        year_coverage = sum(counts[y] >= 2 for y in YEARS)
        minimum_count = min(counts.values()) if counts else 0
        total = sum(counts.values())
        # Small deterministic preference for the early-morning local pass if otherwise tied.
        hours = [r.get("local_hour_family") for r in group if r.get("local_hour_family") is not None]
        hour_penalty = abs(float(median(hours)) - 6.0) if hours else 99.0
        scored.append((year_coverage, minimum_count, total, -hour_penalty, key, counts))
    if not scored:
        raise RuntimeError("no Sentinel-1 track candidates")
    scored.sort(reverse=True)
    year_coverage, minimum_count, total, _hour_score, key, counts = scored[0]
    if year_coverage < len(YEARS) or minimum_count < 2:
        raise RuntimeError(f"no repeated Sentinel-1 track has >=2 same-season scenes in all years: {scored}")
    return key, [r for r in enriched if r["track_key"] == key]


def evenly_select(rows: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    group = sorted(
        [r for r in rows if r.get("acquisition_datetime_utc", "").startswith(f"{year}-")],
        key=lambda r: r.get("acquisition_datetime_utc", ""),
    )
    if len(group) <= MAX_SCENES_PER_YEAR:
        return group
    indices = sorted({round(i * (len(group) - 1) / (MAX_SCENES_PER_YEAR - 1)) for i in range(MAX_SCENES_PER_YEAR)})
    return [group[i] for i in indices]


def read_pair(row: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    paths = paths_by_band(row)
    with rasterio.open(paths["VV"]) as vv_src:
        vv = vv_src.read(1).astype("float32")
        ref = {
            "crs": vv_src.crs,
            "transform": vv_src.transform,
            "height": vv_src.height,
            "width": vv_src.width,
            "nodata": vv_src.nodata,
        }
    with rasterio.open(paths["VH"]) as vh_src:
        if (
            vh_src.crs == ref["crs"]
            and vh_src.transform == ref["transform"]
            and vh_src.height == ref["height"]
            and vh_src.width == ref["width"]
        ):
            vh = vh_src.read(1).astype("float32")
        else:
            vh = np.full((ref["height"], ref["width"]), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(vh_src, 1),
                destination=vh,
                src_transform=vh_src.transform,
                src_crs=vh_src.crs,
                src_nodata=vh_src.nodata,
                dst_transform=ref["transform"],
                dst_crs=ref["crs"],
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
    return vv, vh, ref


def polygon_metrics(vv: np.ndarray, vh: np.ndarray, ref: dict[str, Any], geom_utm: Any) -> dict[str, Any]:
    mask = rasterio.features.geometry_mask(
        [geom_utm.__geo_interface__],
        out_shape=(ref["height"], ref["width"]),
        transform=ref["transform"],
        invert=True,
    )
    valid = mask & np.isfinite(vv) & np.isfinite(vh) & (vv > 0) & (vh > 0)
    if not valid.any():
        return {"valid_pixel_count": 0, "median_log10_vv": None, "median_log10_vh": None, "median_vh_vv_log_ratio": None}
    vv_vals = vv[valid].astype("float64")
    vh_vals = vh[valid].astype("float64")
    log_vv = np.log10(vv_vals)
    log_vh = np.log10(vh_vals)
    ratio = 10.0 * np.log10(vh_vals / vv_vals)
    return {
        "valid_pixel_count": int(valid.sum()),
        "median_log10_vv": round(float(np.median(log_vv)), 5),
        "median_log10_vh": round(float(np.median(log_vh)), 5),
        "median_vh_vv_log_ratio": round(float(np.median(ratio)), 4),
        "p25_vh_vv_log_ratio": round(float(np.percentile(ratio, 25)), 4),
        "p75_vh_vv_log_ratio": round(float(np.percentile(ratio, 75)), 4),
    }


def contrast(project: dict[str, Any], control: dict[str, Any]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for field in ("median_log10_vv", "median_log10_vh", "median_vh_vv_log_ratio"):
        p = fnum(project.get(field))
        c = fnum(control.get(field))
        out[f"project_minus_control_{field}"] = None if p is None or c is None else round(p - c, 5)
    return out


def main() -> int:
    verification = load(VERIFICATION)
    expected = "USER_CONFIRMED_NO_KNOWN_INTERVENTIONS_READY_FOR_COMPARATIVE_SCREENING"
    if verification.get("status") != expected:
        raise SystemExit(f"control verification not ready: {verification.get('status')}")

    tr_fc = load(TRANSECTS)
    plot_fc = load(PLOT)
    candidates = load(CANDIDATES)
    plot_utm = transform(TO_UTM, unary_union([shape(f["geometry"]) for f in plot_fc.get("features", [])]))
    windows, window_design = est.control_windows(tr_fc, plot_utm, candidates)
    pooled_control = unary_union(list(windows.values())).buffer(0)

    rows = catalog_rows()
    track_key, track_rows = choose_track(rows)
    selected_by_year = {year: evenly_select(track_rows, year) for year in YEARS}
    if not all(len(selected_by_year[year]) >= 2 for year in YEARS):
        raise RuntimeError({year: len(selected_by_year[year]) for year in YEARS})

    scenes = []
    annual: dict[str, Any] = {}
    for year in YEARS:
        year_records = []
        for row in selected_by_year[year]:
            vv, vh, ref = read_pair(row)
            project = polygon_metrics(vv, vh, ref, plot_utm)
            control = polygon_metrics(vv, vh, ref, pooled_control)
            controls_by_rank = {str(rank): polygon_metrics(vv, vh, ref, geom) for rank, geom in windows.items()}
            record = {
                "scene_id": row.get("scene_id"),
                "acquisition_datetime_utc": row.get("acquisition_datetime_utc"),
                "acquisition_datetime_bangkok": row.get("acquisition_datetime_bangkok"),
                "track_key": row.get("track_key"),
                "orbit_state": row.get("orbit_state"),
                "relative_orbit": row.get("relative_orbit"),
                "metadata_status": row.get("metadata_status"),
                "project": project,
                "pooled_control": control,
                "controls_by_rank": controls_by_rank,
                "within_scene_contrast": contrast(project, control),
            }
            year_records.append(record)
            scenes.append(record)
        fields = [
            "project_minus_control_median_log10_vv",
            "project_minus_control_median_log10_vh",
            "project_minus_control_median_vh_vv_log_ratio",
        ]
        annual[str(year)] = {
            "scene_count": len(year_records),
            "scene_ids": [r["scene_id"] for r in year_records],
            "median_within_scene_contrast": {
                field: med([fnum(r["within_scene_contrast"].get(field)) for r in year_records], 5)
                for field in fields
            },
            "single_scene_contrast_range": {
                field: (
                    None
                    if len([v for v in [fnum(r["within_scene_contrast"].get(field)) for r in year_records] if v is not None]) < 2
                    else round(
                        max(v for v in [fnum(r["within_scene_contrast"].get(field)) for r in year_records] if v is not None)
                        - min(v for v in [fnum(r["within_scene_contrast"].get(field)) for r in year_records] if v is not None),
                        5,
                    )
                )
                for field in fields
            },
        }

    change_2026_vs_2023 = {}
    for field in annual["2023"]["median_within_scene_contrast"]:
        a = fnum(annual["2023"]["median_within_scene_contrast"].get(field))
        b = fnum(annual["2026"]["median_within_scene_contrast"].get(field))
        change_2026_vs_2023[field] = None if a is None or b is None else round(b - a, 5)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "analysis_role": "INDEPENDENT_SENTINEL1_RELATIVE_CORROBORATION_ONLY",
        "representative_intervention_date": "2023-10-18",
        "method": {
            "collection": "Microsoft Planetary Computer sentinel-1-grd",
            "product_level": "Sentinel-1 Level-1 GRD",
            "bands": ["VV", "VH"],
            "same_season": "February-April 2023-2026",
            "track_selection": "single repeated STAC relative-orbit/orbit-state family when metadata is available; local-hour family fallback only if metadata fetch fails",
            "selected_track_key": track_key,
            "scenes_per_year_max": MAX_SCENES_PER_YEAR,
            "absolute_backscatter_interpretation": "NOT_ALLOWED",
            "relative_metric": "within-scene project-minus-control medians of log10(VV), log10(VH), and 10*log10(VH/VV)",
            "rationale": "project and controls share each acquisition, reducing scene-wide calibration/orbit effects; still not equivalent to calibrated RTC analysis",
        },
        "spatial_design": {
            "project": "current 157.55-rai PDD polygon",
            "controls": "three user-confirmed no-known-intervention pseudo-project windows",
            "control_window_design": window_design,
        },
        "annual": annual,
        "selected_scenes": scenes,
        "change_2026_vs_2023_in_within_scene_project_minus_control": change_2026_vs_2023,
        "evidence_status": {
            "control_intervention_exclusion": "USER_CONFIRMED",
            "radiometric_terrain_correction": "NOT_APPLIED_IN_THIS_GRD_RELATIVE_DIAGNOSTIC",
            "absolute_sar_biomass_claim": "NOT_ALLOWED",
            "field_or_uav_validation": "PENDING",
            "claim_status": "CORROBORATION_DIAGNOSTIC_ONLY_NOT_CAUSAL_OR_BIOMASS_CLAIM",
        },
        "interpretation_limits": [
            "Do not label absolute GRD values as calibrated dB biomass or mangrove density.",
            "VH/VV relative change can respond to vegetation structure, water, surface roughness and dielectric changes; direction is not uniquely attributable to planting.",
            "A consistent optical and SAR relative signal strengthens monitoring confidence but still requires UAV/field validation for survival/species/impact claims.",
            "If a calibrated RTC product becomes available, rerun this analysis with RTC and incidence-angle/terrain handling before publication-quality SAR interpretation.",
        ],
    }
    for path in [OUT, WEB, INTERNAL_WEB]:
        write(path, payload)
    for path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        if path.exists():
            idx = load(path)
            idx["s1_relative_corroboration_file"] = "s1_relative_corroboration.json"
            idx["s1_relative_corroboration_status"] = payload["evidence_status"]["claim_status"]
            write(path, idx)
    print(json.dumps({
        "selected_track": track_key,
        "scenes_per_year": {year: len(selected_by_year[year]) for year in YEARS},
        "change_2026_vs_2023": change_2026_vs_2023,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
