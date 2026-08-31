#!/usr/bin/env python3
"""Summarize the 2023-2026 tide-stage sensitivity run at 37-STC and its controls."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import numpy as np
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
TRANSECTS = ROOT / "data/processed/surat_thani_tide_matched/statistics/transect_summary.geojson"
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
CANDIDATES = ROOT / "data/analysis/surat_thani/control_candidates.json"
VERIFICATION = ROOT / "data/analysis/surat_thani/control_verification.json"
SELECTION = ROOT / "data/analysis/surat_thani/tide_matched_scene_selection.json"
BASELINE = ROOT / "data/analysis/surat_thani/comparative_screening.json"
OUT = ROOT / "data/analysis/surat_thani/tide_matched_sensitivity_summary.json"
WEB = ROOT / "web/public/data/surat_thani/tide_matched_sensitivity_summary.json"
PROJECT_DISTANCE_M = 150.0
YEARS = [2023, 2024, 2025, 2026]
POST_YEARS = [2024, 2025, 2026]
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fnum(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def summarize(features: list[dict]) -> dict:
    yearly = {}
    for year in YEARS:
        vals = [
            fnum((f.get("properties", {}).get("positions_m") or {}).get(str(year)))
            for f in features
        ]
        vals = [v for v in vals if v is not None]
        yearly[str(year)] = {
            "median_position_m": None if not vals else round(float(median(vals)), 2),
            "transect_count": len(vals),
        }
    nets = []
    posts = []
    for f in features:
        positions = f.get("properties", {}).get("positions_m") or {}
        a = fnum(positions.get("2023"))
        b = fnum(positions.get("2026"))
        if a is not None and b is not None:
            nets.append(b - a)
        pts = [(y, fnum(positions.get(str(y)))) for y in POST_YEARS]
        pts = [(y, v) for y, v in pts if v is not None]
        if len(pts) == 3:
            posts.append(float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0]))
    return {
        "transect_count": len(features),
        "transect_ids": [f.get("properties", {}).get("transect_id") for f in features],
        "yearly_median_positions_m": yearly,
        "median_apparent_change_2023_to_2026_m": None if not nets else round(float(median(nets)), 2),
        "median_post_2024_2026_slope_m_per_year": None if not posts else round(float(median(posts)), 3),
    }


def main() -> int:
    tr = load(TRANSECTS)
    plot_fc = load(PLOT)
    candidates = load(CANDIDATES)
    verification = load(VERIFICATION)
    selection = load(SELECTION)
    baseline = load(BASELINE)

    if verification.get("status") != "USER_CONFIRMED_NO_KNOWN_INTERVENTIONS_READY_FOR_COMPARATIVE_SCREENING":
        raise SystemExit("controls are not user-confirmed")

    features = tr.get("features", [])
    plot = unary_union([shape(f["geometry"]) for f in plot_fc["features"]])
    plot_utm = transform(TO_UTM, plot)
    project = [
        f for f in features
        if float(transform(TO_UTM, shape(f["geometry"])).distance(plot_utm)) <= PROJECT_DISTANCE_M
    ]
    if not project:
        raise SystemExit("no tide-matched project frontage transects")
    project_summary = summarize(project)

    windows = []
    pooled = []
    for candidate in candidates.get("candidates", []):
        lo = float(candidate["start_chainage_m"])
        hi = float(candidate["end_chainage_m"])
        group = [
            f for f in features
            if lo - 1e-6 <= float(f.get("properties", {}).get("chainage_m", -1)) <= hi + 1e-6
        ]
        if not group:
            raise SystemExit(f"no tide-matched transects in control chainage {lo}-{hi}")
        pooled.extend(group)
        s = summarize(group)
        s.update({
            "rank": candidate.get("rank"),
            "baseline_chainage_start_m": lo,
            "baseline_chainage_end_m": hi,
            "midpoint_lon_lat": candidate.get("midpoint_lon_lat"),
        })
        windows.append(s)
    pooled_summary = summarize(pooled)

    project_net = project_summary["median_apparent_change_2023_to_2026_m"]
    control_net = pooled_summary["median_apparent_change_2023_to_2026_m"]
    matched_net_contrast = None if project_net is None or control_net is None else round(project_net - control_net, 2)
    project_post = project_summary["median_post_2024_2026_slope_m_per_year"]
    control_post = pooled_summary["median_post_2024_2026_slope_m_per_year"]
    matched_post_contrast = None if project_post is None or control_post is None else round(project_post - control_post, 3)

    b_project = baseline["project_frontage"]["median_apparent_change_2023_to_2026_m"]
    b_control = baseline["controls"]["pooled_15_transects"]["median_apparent_change_2023_to_2026_m"]
    b_net_contrast = baseline["screening_contrasts"]["project_minus_control_apparent_change_2023_2026_m"]

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "analysis_role": "SECONDARY_TIDE_STAGE_SENSITIVITY_ANALYSIS",
        "scene_selection": selection,
        "tide_matched_project_frontage": project_summary,
        "tide_matched_controls": {
            "windows": windows,
            "pooled": pooled_summary,
        },
        "tide_matched_contrasts": {
            "project_minus_control_apparent_change_2023_2026_m": matched_net_contrast,
            "project_minus_control_post_2024_2026_slope_m_per_year": matched_post_contrast,
        },
        "baseline_three_scene_composite": {
            "project_apparent_change_2023_2026_m": b_project,
            "control_apparent_change_2023_2026_m": b_control,
            "project_minus_control_apparent_change_2023_2026_m": b_net_contrast,
        },
        "sensitivity_delta": {
            "project_net_change_matched_minus_baseline_m": None if project_net is None else round(project_net - b_project, 2),
            "control_net_change_matched_minus_baseline_m": None if control_net is None else round(control_net - b_control, 2),
            "net_contrast_matched_minus_baseline_m": None if matched_net_contrast is None else round(matched_net_contrast - b_net_contrast, 2),
        },
        "interpretation_rule": {
            "positive_project_minus_control": "project frontage is more seaward/less landward than controls over 2023-2026",
            "negative_project_minus_control": "project frontage is more landward/less seaward than controls over 2023-2026",
        },
        "claim_status": "TIDE_STAGE_SENSITIVITY_SCREENING_ONLY_NOT_CAUSAL_IMPACT_CLAIM",
        "limitations": [
            "Single-scene annual boundaries reduce mixed tide-stage averaging but increase sensitivity to one acquisition and spectral threshold.",
            "2024 selected scene has direction and official MSL context but unresolved relative extrema phase.",
            "Control physical-setting equivalence and field/UAV validation are still not complete.",
            "Water-land boundary is supporting evidence; mangrove edge and bank edge remain preferred indicators."
        ],
    }
    for path in [OUT, WEB]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "project_transects": project_summary["transect_count"],
        "control_transects": pooled_summary["transect_count"],
        "matched_project_net_m": project_net,
        "matched_control_net_m": control_net,
        "matched_net_contrast_m": matched_net_contrast,
        "baseline_net_contrast_m": b_net_contrast,
        "contrast_delta_m": payload["sensitivity_delta"]["net_contrast_matched_minus_baseline_m"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
