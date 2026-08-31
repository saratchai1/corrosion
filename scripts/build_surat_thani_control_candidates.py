#!/usr/bin/env python3
"""Rank provisional unverified control/reference windows outside 37-STC frontage.

This is a screening aid, not control verification. Candidate windows are selected from
image-derived transects outside the current PDD neighbourhood based on similarity of
pre-intervention 2017-2023 trend and observation completeness. The script cannot prove
that a segment is unplanted or free of coastal structures; those checks remain mandatory.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
TRANSECTS = ROOT / "data/processed/surat_thani/statistics/transect_summary.geojson"
OUT = ROOT / "data/analysis/surat_thani/control_candidates.json"
WEB = ROOT / "web/public/data/surat_thani/control_candidates.json"
INTERNAL_WEB = ROOT / "data/processed/surat_thani/web/control_candidates.json"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
PROJECT_NEAR_M = 150.0
CONTROL_MIN_DISTANCE_M = 400.0
WINDOW_TRANSECTS = 5
MIN_WINDOW_SEPARATION_M = 500.0
PRE_YEARS = list(range(2017, 2024))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fnum(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def slope(props: dict) -> float | None:
    pts = []
    positions = props.get("positions_m") or {}
    for year in PRE_YEARS:
        value = fnum(positions.get(str(year)))
        if value is not None:
            pts.append((year, value))
    if len(pts) < 5:
        return None
    return float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0])


def completeness(props: dict) -> float:
    positions = props.get("positions_m") or {}
    return sum(fnum(positions.get(str(y))) is not None for y in PRE_YEARS) / len(PRE_YEARS)


def midpoint_lonlat(feature: dict) -> list[float]:
    line = shape(feature["geometry"])
    p = line.interpolate(0.5, normalized=True)
    return [round(float(p.x), 6), round(float(p.y), 6)]


def patch_index(path: Path) -> None:
    if not path.exists():
        return
    obj = load(path)
    obj["control_candidates_file"] = "control_candidates.json"
    obj["control_candidates_status"] = "PROVISIONAL_UNVERIFIED"
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    plot_fc = load(PLOT)
    tr_fc = load(TRANSECTS)
    plot = unary_union([shape(f["geometry"]) for f in plot_fc["features"]])
    plot_utm = transform(TO_UTM, plot)

    rows = []
    project_slopes = []
    for feat in tr_fc["features"]:
        props = feat.get("properties", {})
        geom_utm = transform(TO_UTM, shape(feat["geometry"]))
        distance = float(geom_utm.distance(plot_utm))
        s = slope(props)
        c = completeness(props)
        record = {
            "feature": feat,
            "transect_id": props.get("transect_id"),
            "chainage_m": float(props.get("chainage_m", 0)),
            "distance_to_pdd_m": distance,
            "pre_slope_m_per_year": s,
            "pre_completeness": c,
        }
        rows.append(record)
        if distance <= PROJECT_NEAR_M and s is not None:
            project_slopes.append(s)

    if not project_slopes:
        raise SystemExit("no usable project-frontage pretrend slopes")
    target = float(median(project_slopes))

    eligible = [
        r for r in rows
        if r["distance_to_pdd_m"] >= CONTROL_MIN_DISTANCE_M
        and r["pre_slope_m_per_year"] is not None
        and r["pre_completeness"] >= 6 / 7
    ]
    eligible.sort(key=lambda r: r["chainage_m"])
    if len(eligible) < WINDOW_TRANSECTS:
        raise SystemExit(f"only {len(eligible)} eligible outside transects")

    windows = []
    for i in range(0, len(eligible) - WINDOW_TRANSECTS + 1):
        block = eligible[i:i + WINDOW_TRANSECTS]
        chainages = [r["chainage_m"] for r in block]
        # Require a genuinely contiguous 100-m-spaced block; do not bridge the project gap.
        if max(np.diff(chainages), default=0) > 150:
            continue
        slopes = [float(r["pre_slope_m_per_year"]) for r in block]
        med_slope = float(median(slopes))
        med_distance = float(median([r["distance_to_pdd_m"] for r in block]))
        mean_complete = float(np.mean([r["pre_completeness"] for r in block]))
        center_chainage = float(median(chainages))
        score = abs(med_slope - target) + (1.0 - mean_complete) * 5.0
        windows.append({
            "start_chainage_m": min(chainages),
            "end_chainage_m": max(chainages),
            "center_chainage_m": center_chainage,
            "transect_ids": [r["transect_id"] for r in block],
            "median_distance_to_pdd_m": round(med_distance, 1),
            "median_pre_2017_2023_slope_m_per_year": round(med_slope, 2),
            "pretrend_difference_from_project_m_per_year": round(med_slope - target, 2),
            "mean_pre_observation_completeness": round(mean_complete, 3),
            "midpoint_lon_lat": midpoint_lonlat(block[len(block)//2]["feature"]),
            "ranking_score_lower_is_better": round(score, 3),
        })

    windows.sort(key=lambda w: (w["ranking_score_lower_is_better"], -w["median_distance_to_pdd_m"]))
    selected = []
    for candidate in windows:
        if any(abs(candidate["center_chainage_m"] - s["center_chainage_m"]) < MIN_WINDOW_SEPARATION_M for s in selected):
            continue
        selected.append(candidate)
        if len(selected) == 3:
            break

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "status": "PROVISIONAL_UNVERIFIED_CONTROL_CANDIDATES",
        "project_frontage_reference": {
            "current_pdd_area_rai": 157.55,
            "representative_intervention_date": "2023-10-18",
            "project_frontage_median_pre_2017_2023_slope_m_per_year": round(target, 2),
        },
        "screening_method": {
            "outside_distance_min_m": CONTROL_MIN_DISTANCE_M,
            "window_transects": WINDOW_TRANSECTS,
            "window_length_approx_m": (WINDOW_TRANSECTS - 1) * 100,
            "minimum_selected_window_center_separation_m": MIN_WINDOW_SEPARATION_M,
            "rank_basis": "absolute difference from project median 2017-2023 image-derived pretrend plus completeness penalty",
        },
        "candidate_count": len(selected),
        "candidates": [dict(rank=i+1, **c) for i, c in enumerate(selected)],
        "mandatory_verification_before_use_as_controls": [
            "confirm no mangrove planting during the intervention/post period",
            "confirm no new seawall, breakwater, bamboo fence or other erosion-control structure difference",
            "confirm no dredging, embankment or channel intervention that changes coastal process",
            "visually confirm comparable coastal setting, mudflat exposure and river-mouth influence",
            "review high-resolution imagery and preferably field/UAV evidence"
        ],
        "claim_limit": "Candidates are generated from satellite-transect similarity only and are not verified controls. They must not be used for a comparative-effect or causal planting claim until the mandatory checks are completed."
    }

    if len(selected) < 2:
        payload["warning"] = "Fewer than two spatially separated candidates were available from this analytical coast segment. Extend the control search AOI before impact analysis."

    for path in [OUT, WEB, INTERNAL_WEB]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        patch_index(path)

    print(json.dumps({
        "project_pretrend": round(target, 2),
        "eligible_transects": len(eligible),
        "candidate_windows": len(windows),
        "selected": payload["candidates"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
