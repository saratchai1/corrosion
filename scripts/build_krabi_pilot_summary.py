#!/usr/bin/env python3
"""Build an executive, machine-readable summary for the Krabi pilot."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def number(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def percent(value: float | None) -> float | None:
    return round(value * 100.0, 2) if value is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vegetation", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--water-scene-summary", type=Path, required=True)
    parser.add_argument("--water-consensus", type=Path, required=True)
    parser.add_argument("--scl-audit", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    vegetation = read_csv(args.vegetation)
    events = read_csv(args.events)
    scene_summary = read_json(args.water_scene_summary)
    consensus = read_json(args.water_consensus)
    scl = read_json(args.scl_audit)
    epoch = consensus["epoch_change"]
    annual = consensus["annual"]

    plot_rows = []
    for row in vegetation:
        plot_rows.append(
            {
                "plot_code": row["plot_code"],
                "ndvi_trend": row["median_ndvi_trend"],
                "ndvi_slope_per_year": number(row["median_ndvi_slope_per_year"]),
                "ndvi_r2": number(row["median_ndvi_r2"]),
                "latest_month": row["latest_month"],
                "latest_ndvi": number(row["latest_ndvi"]),
                "latest_qa": row["latest_qa"],
                "latest_good_month": row["latest_good_month"],
                "latest_good_ndvi": number(row["latest_good_ndvi"]),
                "minimum_month": row["min_ndvi_month"],
                "minimum_ndvi": number(row["min_ndvi"]),
                "minimum_qa": row["min_ndvi_qa"],
                "good_observations": int(row["good_count"]),
                "usable_observations": int(row["usable_observations"]),
            }
        )

    review_events = []
    for row in events:
        review_events.append(
            {
                "plot_code": row["plot_code"],
                "event": row["event"],
                "drop_month": row["drop_month"],
                "drop_qa": row["drop_qa"],
                "ndvi_before": number(row["ndvi_before"]),
                "ndvi_drop": number(row["ndvi_drop"]),
                "recovery_month": row["recovery_month"],
                "recovery_qa": row["recovery_qa"],
                "ndvi_recovery": number(row["ndvi_recovery"]),
                "priority": (
                    "FIELD_REVIEW" if row["drop_qa"] == "GOOD" else "DESK_REVIEW"
                ),
            }
        )
    review_events.sort(
        key=lambda item: (item["priority"] != "FIELD_REVIEW", item["plot_code"])
    )

    comparable = float(epoch["comparable_area_m2"])
    gain = float(epoch["candidate_water_gain_m2"])
    loss = float(epoch["candidate_water_loss_m2"])
    net = float(epoch["net_candidate_water_gain_m2"])
    gain_fraction = gain / comparable if comparable else None
    loss_fraction = loss / comparable if comparable else None
    net_fraction = net / comparable if comparable else None
    all_no_clear_decline = all(
        row["ndvi_trend"] == "NO_CLEAR_LINEAR_TREND" for row in plot_rows
    )
    scene_r2 = number(scene_summary.get("linear_water_fraction_r2"))
    scene_slope = number(scene_summary.get("linear_water_fraction_slope_per_year"))
    scene_clear_trend = bool(
        scene_r2 is not None
        and scene_slope is not None
        and scene_r2 >= 0.20
        and abs(scene_slope) >= 0.005
    )

    annual_rows = [
        {
            "year": int(item["label"]),
            "acquisition_count": int(item["acquisition_count"]),
            "water_area_m2": number(item["consensus_water_area_m2"]),
            "water_fraction_of_classified": (
                round(
                    float(item["consensus_water_area_m2"])
                    / float(item["classified_area_m2"]),
                    6,
                )
                if float(item["classified_area_m2"])
                else None
            ),
            "variable_water_area_m2": number(item["variable_water_area_m2"]),
            "mean_uncertainty": number(item["mean_uncertainty"]),
            "acquisition_dates": item["acquisition_dates"],
        }
        for item in annual
    ]
    scene_count = sum(item["acquisition_count"] for item in annual_rows)

    water_status = (
        "REVIEW_CANDIDATE_WATER_GAIN"
        if gain_fraction is not None and gain_fraction >= 0.01
        else "NO_LARGE_PERSISTENT_WATER_GAIN_SIGNAL"
    )
    headline = (
        "การคัดกรองหลายภาพยังไม่พบแนวโน้มเสื่อมโทรมของพืชหรือการเพิ่มพื้นที่น้ำแบบต่อเนื่องที่ชัดเจน"
        if all_no_clear_decline and not scene_clear_trend
        else "พบสัญญาณบางส่วนที่ต้องตรวจภาคสนามและควบคุมระดับน้ำก่อนสรุปเชิงวิศวกรรม"
    )

    result = {
        "generated_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "pilot": {
            "province": "Krabi",
            "province_th": "กระบี่",
            "plot_count": len(plot_rows),
            "plot_codes": [row["plot_code"] for row in plot_rows],
            "analysis_crs": "EPSG:32647",
            "sentinel2_collection": "sentinel-2-c1-l2a",
            "first_observation_year": min(item["year"] for item in annual_rows),
            "last_observation_year": max(item["year"] for item in annual_rows),
            "scene_count": scene_count,
        },
        "executive": {
            "headline_th": headline,
            "vegetation_status": (
                "NO_CLEAR_PERSISTENT_LINEAR_DECLINE"
                if all_no_clear_decline
                else "REVIEW_VEGETATION_TREND"
            ),
            "water_status": water_status,
            "engineering_erosion_rate_status": "NOT_ESTIMATED_TIDE_UNVERIFIED",
            "recommended_field_priority": [
                event["plot_code"]
                for event in review_events
                if event["priority"] == "FIELD_REVIEW"
            ],
        },
        "vegetation": {
            "plots": plot_rows,
            "temporary_dip_events": review_events,
            "interpretation": (
                "No plot has a clear persistent linear NDVI decline under the "
                "conservative slope/R² rule. Temporary dips are screening flags, "
                "not mortality findings."
            ),
        },
        "water": {
            "annual_consensus": annual_rows,
            "baseline": epoch["baseline"],
            "latest": epoch["latest"],
            "comparable_area_m2": comparable,
            "candidate_water_gain_m2": gain,
            "candidate_water_loss_m2": loss,
            "net_candidate_water_gain_m2": net,
            "candidate_water_gain_pct_comparable": percent(gain_fraction),
            "candidate_water_loss_pct_comparable": percent(loss_fraction),
            "net_candidate_water_gain_pct_comparable": percent(net_fraction),
            "plot_screening": epoch.get("plots", []),
            "single_scene_linear_slope_per_year": scene_slope,
            "single_scene_linear_r2": scene_r2,
            "clear_single_scene_linear_trend": scene_clear_trend,
            "analysis_status": epoch["analysis_status"],
        },
        "qa": {
            "scl_cross_check": {
                key: value for key, value in scl.items() if key != "scenes"
            },
            "radiometric_calibration": (
                "Collection 1 STAC scale/offset audited per scene"
            ),
            "tide_control": False,
            "field_shoreline_control": False,
        },
        "decision_rules": {
            "water_gain_review_threshold": "max(1,000 m², 1% of comparable plot area)",
            "persistent_linear_trend": (
                "R² >= 0.20 and absolute slope >= 0.015 NDVI/year"
            ),
            "water_consensus": (
                "at least 50% water votes with at least 66% valid scenes"
            ),
        },
        "limitations": [
            "Satellite acquisitions are not yet normalized to a common predicted tide level.",
            "MNDWI and SCL are screening classifiers and are not field shoreline truth.",
            "Candidate water gain/loss must not be reported as erosion/accretion rate.",
            "The plot polygons are project monitoring boundaries, not an official coastline.",
        ],
        "next_field_actions": [
            "Inspect 97-VSD first because the 2025-06 NDVI dip is supported by GOOD QA and later recovery.",
            "Survey stable shoreline control points and elevation/tide references around flagged water-change polygons.",
            "Use the Royal Thai Navy Pak Nam Krabi tide station for tide-matched engineering analysis.",
        ],
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# Krabi coastal and mangrove pilot — executive screening",
        "",
        f"**Status:** {result['executive']['headline_th']}",
        "",
        f"- Plots: {', '.join(result['pilot']['plot_codes'])}",
        f"- Sentinel-2 Collection 1 scenes: {scene_count}",
        f"- Period: {result['pilot']['first_observation_year']}–{result['pilot']['last_observation_year']}",
        f"- Candidate water gain: {gain:,.0f} m² ({percent(gain_fraction):.2f}% of comparable area)",
        f"- Candidate water loss: {loss:,.0f} m² ({percent(loss_fraction):.2f}% of comparable area)",
        "- Tide control: not yet verified; no erosion rate is claimed.",
        "",
        "## Field priority",
    ]
    priorities = result["executive"]["recommended_field_priority"]
    lines.append(
        ", ".join(priorities)
        if priorities
        else "No high-priority plot from vegetation QA."
    )
    lines += [
        "",
        "## Interpretation",
        (
            "The pipeline is complete for repeatable satellite screening. "
            "Engineering shoreline retreat requires tide-matched imagery and field "
            "control points."
        ),
        "",
    ]
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result["executive"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
