#!/usr/bin/env python3
"""Compare two water-polygon GeoJSONs on a projected grid.

`water_gain` means area classified as water in the latest date but not baseline.
It is only an erosion/inundation *candidate* until tide and classification error
are controlled. `water_loss` is the reverse and may indicate accretion/drying.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform
TO_WGS = Transformer.from_crs("EPSG:32647", "EPSG:4326", always_xy=True).transform


def load_union(path: Path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    feats = obj.get("features", [])
    if not feats:
        raise ValueError(f"No water polygon features in {path}")
    polygons = [shape(f["geometry"]) for f in feats]
    union = unary_union(polygons)
    properties = feats[0].get("properties", {})
    return union, properties


def parts(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline/latest water polygons")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-unverified-tide", action="store_true")
    parser.add_argument("--min-change-m2", type=float, default=100.0)
    args = parser.parse_args()

    base4326, base_props = load_union(args.baseline)
    latest4326, latest_props = load_union(args.latest)
    tide_ok = base_props.get("tide_status") == "verified" and latest_props.get("tide_status") == "verified"
    if not tide_ok and not args.allow_unverified_tide:
        raise SystemExit(
            "Tide is not verified for both dates. Match tide first or pass "
            "--allow-unverified-tide for screening-only output."
        )

    baseline = transform(TO_UTM, base4326)
    latest = transform(TO_UTM, latest4326)
    water_gain = latest.difference(baseline)
    water_loss = baseline.difference(latest)
    stable_water = baseline.intersection(latest)

    status = "TIDE_VERIFIED_SCREENING" if tide_ok else "TIDE_UNVERIFIED_SCREENING"
    features = []
    for change_type, geom in (("water_gain", water_gain), ("water_loss", water_loss)):
        for i, poly in enumerate(parts(geom), 1):
            if poly.area < args.min_change_m2:
                continue
            features.append({
                "type": "Feature",
                "properties": {
                    "change_type": change_type,
                    "part": i,
                    "area_m2": round(poly.area, 2),
                    "baseline_date": base_props.get("acquisition_date"),
                    "latest_date": latest_props.get("acquisition_date"),
                    "baseline_tide_status": base_props.get("tide_status"),
                    "latest_tide_status": latest_props.get("tide_status"),
                    "analysis_status": status,
                },
                "geometry": mapping(transform(TO_WGS, poly)),
            })

    args.out.mkdir(parents=True, exist_ok=True)
    geojson = {"type": "FeatureCollection", "features": features}
    (args.out / "water_change.geojson").write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "baseline_date": base_props.get("acquisition_date"),
        "latest_date": latest_props.get("acquisition_date"),
        "baseline_tide_status": base_props.get("tide_status"),
        "latest_tide_status": latest_props.get("tide_status"),
        "analysis_status": status,
        "water_gain_m2": round(sum(p.area for p in parts(water_gain)), 2),
        "water_loss_m2": round(sum(p.area for p in parts(water_loss)), 2),
        "stable_water_m2": round(sum(p.area for p in parts(stable_water)), 2),
        "interpretation": {
            "water_gain": "candidate land-to-water / inundation / erosion signal; not causal attribution",
            "water_loss": "candidate water-to-land / accretion / drying signal; not causal attribution",
        },
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
