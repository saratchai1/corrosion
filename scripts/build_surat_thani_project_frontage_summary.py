#!/usr/bin/env python3
"""Extract a plot-focused coastal-change screening summary for Surat Thani 37-STC.

The full MVP has transects along several kilometres of surrounding Chaiya coast. This
script selects transects that cross or pass within 150 m of the current 157.55-rai PDD
boundary so portfolio-wide coastal behaviour is not mistaken for plot-frontage behaviour.
All metrics remain image-derived water-land-boundary screening, not surveyed shoreline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import numpy as np
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
PLOT = ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson"
TRANSECTS = ROOT / "data/processed/surat_thani/statistics/transect_summary.geojson"
OUT_SUMMARY = ROOT / "data/processed/surat_thani/statistics/project_frontage_summary.json"
OUT_GEOJSON = ROOT / "data/processed/surat_thani/statistics/project_frontage_transects.geojson"
WEB_SUMMARY = ROOT / "web/public/data/surat_thani/project_frontage_summary.json"
WEB_GEOJSON = ROOT / "web/public/data/surat_thani/project_frontage_transects.geojson"
WEB_INTERNAL_SUMMARY = ROOT / "data/processed/surat_thani/web/project_frontage_summary.json"
WEB_INTERNAL_GEOJSON = ROOT / "data/processed/surat_thani/web/project_frontage_transects.geojson"
SELECTION_DISTANCE_M = 150.0
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def slope(props: dict, years: list[int]) -> float | None:
    points = []
    positions = props.get("positions_m") or {}
    for year in years:
        value = finite(positions.get(str(year)))
        if value is not None:
            points.append((year, value))
    if len(points) < 3:
        return None
    return float(np.polyfit([p[0] for p in points], [p[1] for p in points], 1)[0])


def med(values):
    vals = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    return None if not vals else round(float(median(vals)), 2)


def patch_index(path: Path) -> None:
    if not path.exists():
        return
    payload = read_json(path)
    payload["project_frontage_summary_file"] = "project_frontage_summary.json"
    payload["project_frontage_transects_file"] = "project_frontage_transects.geojson"
    payload["project_frontage_scope"] = "37-STC current PDD boundary, 157.55 rai, transects within 150 m"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    plot_fc = read_json(PLOT)
    transect_fc = read_json(TRANSECTS)
    plot_geom = unary_union([shape(f["geometry"]) for f in plot_fc["features"]])
    plot_utm = transform(TO_UTM, plot_geom)

    selected = []
    all_features = transect_fc.get("features", [])
    for feature in all_features:
        geom_utm = transform(TO_UTM, shape(feature["geometry"]))
        distance = float(geom_utm.distance(plot_utm))
        if distance > SELECTION_DISTANCE_M:
            continue
        copied = json.loads(json.dumps(feature))
        props = copied.setdefault("properties", {})
        props["project_frontage"] = True
        props["distance_to_current_pdd_m"] = round(distance, 2)
        p2023 = finite((props.get("positions_m") or {}).get("2023"))
        p2026 = finite((props.get("positions_m") or {}).get("2026"))
        props["apparent_change_2023_2026_m"] = (
            None if p2023 is None or p2026 is None else round(p2026 - p2023, 2)
        )
        props["pre_2017_2023_slope_m_per_year"] = (
            None if (v := slope(props, list(range(2017, 2024)))) is None else round(v, 2)
        )
        props["post_2024_2026_slope_m_per_year"] = (
            None if (v := slope(props, [2024, 2025, 2026])) is None else round(v, 2)
        )
        selected.append(copied)

    if not selected:
        raise SystemExit("no transects selected near current 37-STC boundary")

    years = list(range(2017, 2027))
    yearly_medians = {}
    for year in years:
        values = [
            finite((f.get("properties", {}).get("positions_m") or {}).get(str(year)))
            for f in selected
        ]
        valid = [v for v in values if v is not None]
        yearly_medians[str(year)] = {
            "median_position_m": med(valid),
            "transect_count": len(valid),
        }

    changes = [f["properties"].get("apparent_change_2023_2026_m") for f in selected]
    pre_slopes = [f["properties"].get("pre_2017_2023_slope_m_per_year") for f in selected]
    post_slopes = [f["properties"].get("post_2024_2026_slope_m_per_year") for f in selected]
    class_counts = {}
    for f in selected:
        label = f.get("properties", {}).get("classification", "unknown")
        class_counts[label] = class_counts.get(label, 0) + 1

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "scope": {
            "primary_boundary_area_rai": 157.55,
            "primary_boundary": "current PDD / SHP PDD",
            "selection_rule": f"full 3-km transect intersects or passes within {SELECTION_DISTANCE_M:.0f} m of current PDD polygon",
            "selected_transect_count": len(selected),
            "all_coast_transect_count": len(all_features),
        },
        "period": {
            "representative_intervention_date": "2023-10-18",
            "2023_feb_apr_role": "PRE_INTERVENTION",
            "post_years": [2024, 2025, 2026],
        },
        "image_derived_water_land_boundary_screening": {
            "yearly_median_positions_m": yearly_medians,
            "median_apparent_change_2023_to_2026_m": med(changes),
            "median_pre_2017_2023_slope_m_per_year": med(pre_slopes),
            "median_post_2024_2026_slope_m_per_year": med(post_slopes),
            "classification_counts_from_full_mvp": class_counts,
            "positive_direction": "seaward",
        },
        "tide_context": {
            "2023": "selected Sentinel-2 scenes have official LLW extrema stage/phase context",
            "2024": "reproducible hourly MSL not yet available",
            "2025": "reproducible hourly MSL not yet available",
            "2026": "selected Sentinel-2 scenes matched to official Ko Prap hourly MSL",
            "status": "PARTIAL_TIDE_CONTEXT_ONLY",
        },
        "confidence": "LOW",
        "claim_status": "SCREENING_ONLY_NOT_FOR_CAUSAL_IMPACT_CLAIMS",
        "interpretation": "Metrics describe apparent movement of automated image-derived water-land boundaries near the current 37-STC polygon. They are not surveyed shoreline positions and cannot yet establish that planting changed erosion rate.",
        "next_evidence_needed": [
            "reproducible tide context for 2024-2025 or same-stage image selection",
            "manual/orthophoto validation of mangrove edge or bank edge",
            "verified unplanted control segments with comparable pretrend",
            "field or UAV validation"
        ]
    }

    fc = {"type": "FeatureCollection", "features": selected}
    for path, payload in [
        (OUT_SUMMARY, summary),
        (OUT_GEOJSON, fc),
        (WEB_SUMMARY, summary),
        (WEB_GEOJSON, fc),
        (WEB_INTERNAL_SUMMARY, summary),
        (WEB_INTERNAL_GEOJSON, fc),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    for index_path in [
        ROOT / "web/public/data/surat_thani/index.json",
        ROOT / "data/processed/surat_thani/web/index.json",
    ]:
        patch_index(index_path)

    print(json.dumps({
        "selected": len(selected),
        "all": len(all_features),
        "median_change_2023_2026_m": summary["image_derived_water_land_boundary_screening"]["median_apparent_change_2023_to_2026_m"],
        "median_pre_slope": summary["image_derived_water_land_boundary_screening"]["median_pre_2017_2023_slope_m_per_year"],
        "median_post_slope": summary["image_derived_water_land_boundary_screening"]["median_post_2024_2026_slope_m_per_year"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
