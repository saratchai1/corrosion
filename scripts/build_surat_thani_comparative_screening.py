#!/usr/bin/env python3
"""Build a conservative treatment-vs-control coastal-change screening for 37-STC.

Controls are the three satellite-ranked windows in control_candidates.json. This
script only runs them as controls when control_verification.json records the
project user's confirmation that no known planting/coastal-structure/dredging
intervention affected those windows. Physical coastal-setting equivalence and
field/UAV validation remain separate evidence gates, so outputs are screening
metrics rather than causal estimates.
"""
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
TRANSECTS = ROOT / "data/processed/surat_thani/statistics/transect_summary.geojson"
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
CANDIDATES = ROOT / "data/analysis/surat_thani/control_candidates.json"
VERIFICATION = ROOT / "data/analysis/surat_thani/control_verification.json"
OUT = ROOT / "data/analysis/surat_thani/comparative_screening.json"
WEB = ROOT / "web/public/data/surat_thani/comparative_screening.json"
INTERNAL_WEB = ROOT / "data/processed/surat_thani/web/comparative_screening.json"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
PROJECT_DISTANCE_M = 150.0
PRE_YEARS = list(range(2017, 2024))
POST_YEARS = [2024, 2025, 2026]
ALL_YEARS = list(range(2017, 2027))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fnum(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def slope_for_years(props: dict, years: list[int], minimum: int) -> float | None:
    positions = props.get("positions_m") or {}
    pts = []
    for year in years:
        value = fnum(positions.get(str(year)))
        if value is not None:
            pts.append((year, value))
    if len(pts) < minimum:
        return None
    return float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0])


def net_change(props: dict, start: int = 2023, end: int = 2026) -> float | None:
    positions = props.get("positions_m") or {}
    a = fnum(positions.get(str(start)))
    b = fnum(positions.get(str(end)))
    if a is None or b is None:
        return None
    return b - a


def summarize_group(features: list[dict]) -> dict:
    if not features:
        raise ValueError("empty comparison group")
    pre = []
    post = []
    changes = []
    yearly = {}
    for feat in features:
        props = feat.get("properties", {})
        s_pre = slope_for_years(props, PRE_YEARS, 5)
        s_post = slope_for_years(props, POST_YEARS, 3)
        n = net_change(props)
        if s_pre is not None:
            pre.append(s_pre)
        if s_post is not None:
            post.append(s_post)
        if n is not None:
            changes.append(n)
    for year in ALL_YEARS:
        vals = []
        for feat in features:
            value = fnum((feat.get("properties", {}).get("positions_m") or {}).get(str(year)))
            if value is not None:
                vals.append(value)
        if vals:
            yearly[str(year)] = {
                "median_position_m": round(float(median(vals)), 2),
                "transect_count": len(vals),
            }
    med_pre = float(median(pre)) if pre else None
    med_post = float(median(post)) if post else None
    med_change = float(median(changes)) if changes else None
    return {
        "transect_count": len(features),
        "transect_ids": [f.get("properties", {}).get("transect_id") for f in features],
        "median_pre_2017_2023_slope_m_per_year": round(med_pre, 3) if med_pre is not None else None,
        "median_post_2024_2026_slope_m_per_year": round(med_post, 3) if med_post is not None else None,
        "median_slope_change_post_minus_pre_m_per_year": round(med_post - med_pre, 3) if med_pre is not None and med_post is not None else None,
        "median_apparent_change_2023_to_2026_m": round(med_change, 2) if med_change is not None else None,
        "yearly_median_positions_m": yearly,
    }


def patch_index(path: Path) -> None:
    if not path.exists():
        return
    obj = load(path)
    obj["comparative_screening_file"] = "comparative_screening.json"
    obj["comparative_screening_status"] = "TREATMENT_CONTROL_SCREENING_WITH_USER_CONFIRMED_NO_KNOWN_CONTROL_INTERVENTIONS"
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    tr_fc = load(TRANSECTS)
    plot_fc = load(PLOT)
    candidates = load(CANDIDATES)
    verification = load(VERIFICATION)

    expected_status = "USER_CONFIRMED_NO_KNOWN_INTERVENTIONS_READY_FOR_COMPARATIVE_SCREENING"
    if verification.get("status") != expected_status:
        raise SystemExit(f"control verification not ready: {verification.get('status')}")
    confirmed = verification.get("user_confirmed") or {}
    required = [
        "no_mangrove_planting_during_intervention_or_post_period",
        "no_new_seawall_breakwater_bamboo_fence_or_other_coastal_protection_structure",
        "no_dredging_embankment_or_channel_intervention_known_to_change_coastal_process",
        "no_other_known_intervention_materially_different_from_37_STC",
    ]
    if not all(confirmed.get(k) is True for k in required):
        raise SystemExit("not all no-intervention control checks are user-confirmed")

    features = tr_fc.get("features", [])
    by_id = {f.get("properties", {}).get("transect_id"): f for f in features}
    plot = unary_union([shape(f["geometry"]) for f in plot_fc["features"]])
    plot_utm = transform(TO_UTM, plot)
    project = []
    for feat in features:
        line_utm = transform(TO_UTM, shape(feat["geometry"]))
        if float(line_utm.distance(plot_utm)) <= PROJECT_DISTANCE_M:
            project.append(feat)
    project_summary = summarize_group(project)

    control_summaries = []
    pooled_control_features = []
    for candidate in candidates.get("candidates", []):
        ids = candidate.get("transect_ids", [])
        group = [by_id[i] for i in ids if i in by_id]
        if len(group) != len(ids) or not group:
            raise SystemExit(f"missing transects for candidate rank {candidate.get('rank')}")
        pooled_control_features.extend(group)
        summary = summarize_group(group)
        summary.update({
            "rank": candidate.get("rank"),
            "center_chainage_m": candidate.get("center_chainage_m"),
            "median_distance_to_pdd_m": candidate.get("median_distance_to_pdd_m"),
            "midpoint_lon_lat": candidate.get("midpoint_lon_lat"),
            "pretrend_ranking_score": candidate.get("ranking_score_lower_is_better"),
        })
        control_summaries.append(summary)
    pooled = summarize_group(pooled_control_features)

    p_delta = project_summary["median_slope_change_post_minus_pre_m_per_year"]
    c_delta = pooled["median_slope_change_post_minus_pre_m_per_year"]
    p_net = project_summary["median_apparent_change_2023_to_2026_m"]
    c_net = pooled["median_apparent_change_2023_to_2026_m"]
    slope_contrast = round(p_delta - c_delta, 3) if p_delta is not None and c_delta is not None else None
    net_contrast = round(p_net - c_net, 2) if p_net is not None and c_net is not None else None

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "representative_intervention_date": "2023-10-18",
        "positive_direction": "seaward; negative values indicate apparent landward movement/retreat of the automated water-land boundary",
        "control_verification_status": verification.get("status"),
        "project_frontage": project_summary,
        "controls": {
            "candidate_count": len(control_summaries),
            "windows": control_summaries,
            "pooled_15_transects": pooled,
        },
        "screening_contrasts": {
            "project_minus_control_slope_change_m_per_year": slope_contrast,
            "interpretation_of_positive_slope_contrast": "project frontage shifted toward a less-negative/more-seaward post-vs-pre trend more than pooled controls",
            "project_minus_control_apparent_change_2023_2026_m": net_contrast,
            "interpretation_of_positive_net_contrast": "project frontage had more seaward/less landward apparent 2023-2026 movement than pooled controls",
            "method": "descriptive median-transect contrast; not a formal causal difference-in-differences estimate",
        },
        "evidence_status": {
            "known_control_intervention_exclusion": "USER_CONFIRMED",
            "pretrend_similarity": "SATELLITE_RANKED",
            "physical_coastal_setting_equivalence": "NOT_FIELD_VERIFIED",
            "tide_normalization": "PARTIAL_2023_PHASE_AND_2026_MSL_ONLY",
            "field_or_uav_validation": "PENDING",
            "claim_status": "COMPARATIVE_SCREENING_ONLY_NOT_CAUSAL_IMPACT_CLAIM",
        },
        "claim_limit": "The comparison can show whether the image-derived trend near 37-STC differs from the selected no-known-intervention reference windows. It must not yet be stated as proof that planting caused erosion reduction because tide normalization, physical-setting equivalence and field/UAV validation are incomplete."
    }

    for path in [OUT, WEB, INTERNAL_WEB]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        patch_index(path)

    print(json.dumps({
        "project": project_summary,
        "pooled_controls": pooled,
        "slope_change_contrast_m_per_year": slope_contrast,
        "net_change_contrast_m": net_contrast,
        "status": payload["evidence_status"]["claim_status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
