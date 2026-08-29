#!/usr/bin/env python3
"""Summarize annual water-mask outputs into reproducible screening tables."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path


def linear_slope(rows: list[dict[str, object]], key: str) -> tuple[float | None, float | None]:
    pts = []
    origin = datetime.fromisoformat(str(rows[0]["date"]))
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        dt = datetime.fromisoformat(str(row["date"]))
        x = (dt - origin).days / 365.2425
        pts.append((x, float(value)))
    if len(pts) < 3:
        return None, None
    xbar = sum(x for x, _ in pts) / len(pts)
    ybar = sum(y for _, y in pts) / len(pts)
    denom = sum((x - xbar) ** 2 for x, _ in pts)
    if denom == 0:
        return None, None
    slope = sum((x - xbar) * (y - ybar) for x, y in pts) / denom
    intercept = ybar - slope * xbar
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in pts)
    sst = sum((y - ybar) ** 2 for _, y in pts)
    r2 = 1.0 - sse / sst if sst else None
    return slope, r2


def polygon_area(path: Path) -> float:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return sum(float(f.get("properties", {}).get("area_m2_projected", 0.0)) for f in obj.get("features", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize water history summary.json files")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for summary_path in sorted(args.root.glob("*/summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        polygons = summary_path.parent / "water_polygons.geojson"
        rows.append({
            "date": summary["date"],
            "sensor": summary["sensor"],
            "valid_pixel_count": summary["valid_pixel_count"],
            "water_pixel_count": summary["water_pixel_count"],
            "water_fraction_valid": summary["water_fraction_valid"],
            "water_polygon_area_m2": round(polygon_area(polygons), 2) if polygons.exists() else None,
            "green_scale": summary.get("green_scale"),
            "green_offset": summary.get("green_offset"),
            "swir_scale": summary.get("swir_scale"),
            "swir_offset": summary.get("swir_offset"),
            "green_calibration_source": summary.get("green_calibration_source"),
            "swir_calibration_source": summary.get("swir_calibration_source"),
            "quality_mask_used": summary.get("quality_mask_used"),
            "tide_status": summary.get("tide_status"),
            "analysis_status": summary.get("analysis_status"),
        })

    rows.sort(key=lambda row: str(row["date"]))
    if not rows:
        raise SystemExit(f"No water history summaries found under {args.root}")

    fields = list(rows[0])
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    fraction_slope, fraction_r2 = linear_slope(rows, "water_fraction_valid")
    area_slope, area_r2 = linear_slope(rows, "water_polygon_area_m2")
    first = rows[0]
    last = rows[-1]
    payload = {
        "observation_count": len(rows),
        "start_date": first["date"],
        "end_date": last["date"],
        "start_water_fraction_valid": first["water_fraction_valid"],
        "end_water_fraction_valid": last["water_fraction_valid"],
        "delta_water_fraction_valid": round(float(last["water_fraction_valid"]) - float(first["water_fraction_valid"]), 6),
        "start_water_polygon_area_m2": first["water_polygon_area_m2"],
        "end_water_polygon_area_m2": last["water_polygon_area_m2"],
        "delta_water_polygon_area_m2": round(float(last["water_polygon_area_m2"]) - float(first["water_polygon_area_m2"]), 2),
        "linear_water_fraction_slope_per_year": None if fraction_slope is None else round(fraction_slope, 8),
        "linear_water_fraction_r2": None if fraction_r2 is None else round(fraction_r2, 4),
        "linear_water_area_slope_m2_per_year": None if area_slope is None else round(area_slope, 2),
        "linear_water_area_r2": None if area_r2 is None else round(area_r2, 4),
        "tide_status": "unverified" if any(r["tide_status"] != "verified" for r in rows) else "verified",
        "analysis_status": "TIDE_UNVERIFIED_SCREENING" if any(r["tide_status"] != "verified" for r in rows) else "TIDE_VERIFIED_SCREENING",
        "interpretation": "Annual water-edge screening only; do not convert to erosion/accretion rate until tide and classification uncertainty are controlled.",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
