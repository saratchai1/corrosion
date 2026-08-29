#!/usr/bin/env python3
"""Summarize QA-weighted Krabi PDD22 spectral trends and temporary NDVI dips.

This script deliberately treats the reused Sentinel-2 metrics as screening data.
It does not infer shoreline displacement, erosion, mortality, salinity damage, or
storm damage from plot-level spectral summaries.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "regions/krabi/data/reuse/pdd22_krabi_coverage.csv"
OUT_DIR = REPO_ROOT / "regions/krabi/analysis"
TREND_OUT = OUT_DIR / "vegetation_trends.csv"
EVENT_OUT = OUT_DIR / "events.csv"

QA_WEIGHT = {"GOOD": 1.0, "PARTIAL": 0.6, "LOW_QA": 0.25, "NO_DATA": 0.0}
METRICS = ("median_ndvi", "median_ndre", "median_mndwi")


def month_to_years(value: str, origin: datetime) -> float:
    dt = datetime.strptime(value + "-01", "%Y-%m-%d")
    return (dt - origin).days / 365.2425


def load_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with SOURCE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["coverage_pct"] = float(row["coverage_pct"])
            for key in METRICS:
                row[key] = float(row[key]) if row[key] else math.nan
            row["weight"] = QA_WEIGHT[row["qa"]] * float(row["coverage_pct"]) / 100.0
            rows.append(row)
    return rows


def weighted_slope(rows: list[dict[str, object]], metric: str) -> tuple[float, float]:
    origin = datetime(2023, 9, 1)
    pts = [
        (month_to_years(str(r["month"]), origin), float(r[metric]), float(r["weight"]))
        for r in rows
        if float(r["weight"]) > 0 and not math.isnan(float(r[metric]))
    ]
    if len(pts) < 3:
        return math.nan, math.nan
    sw = sum(w for _, _, w in pts)
    xbar = sum(x * w for x, _, w in pts) / sw
    ybar = sum(y * w for _, y, w in pts) / sw
    denom = sum(w * (x - xbar) ** 2 for x, _, w in pts)
    slope = sum(w * (x - xbar) * (y - ybar) for x, y, w in pts) / denom
    intercept = ybar - slope * xbar
    sse = sum(w * (y - (intercept + slope * x)) ** 2 for x, y, w in pts)
    sst = sum(w * (y - ybar) ** 2 for _, y, w in pts)
    r2 = 1.0 - sse / sst if sst else math.nan
    return slope, r2


def trend_label(slope: float, r2: float) -> str:
    # Conservative threshold: avoid turning weak seasonal scatter into a trend claim.
    if math.isnan(slope) or math.isnan(r2):
        return "INSUFFICIENT"
    if r2 < 0.20 or abs(slope) < 0.015:
        return "NO_CLEAR_LINEAR_TREND"
    return "INCREASING" if slope > 0 else "DECREASING"


def detect_temporary_dip(rows: list[dict[str, object]]) -> dict[str, object] | None:
    usable = sorted((r for r in rows if float(r["weight"]) > 0), key=lambda r: str(r["month"]))
    for i in range(1, len(usable) - 1):
        prev, cur = usable[i - 1], usable[i]
        if float(prev["median_ndvi"]) - float(cur["median_ndvi"]) < 0.10:
            continue
        for rec in usable[i + 1 :]:
            if float(rec["median_ndvi"]) - float(cur["median_ndvi"]) >= 0.10:
                return {
                    "plot_code": cur["plot_code"],
                    "event": "TEMPORARY_NDVI_DIP",
                    "drop_month": cur["month"],
                    "drop_qa": cur["qa"],
                    "ndvi_before": f'{float(prev["median_ndvi"]):.4f}',
                    "ndvi_drop": f'{float(cur["median_ndvi"]):.4f}',
                    "recovery_month": rec["month"],
                    "recovery_qa": rec["qa"],
                    "ndvi_recovery": f'{float(rec["median_ndvi"]):.4f}',
                    "note": (
                        "screening flag only; may reflect season, water, cloud residual, "
                        "or vegetation stress"
                    ),
                }
    return None


def main() -> None:
    rows = load_rows()
    by_plot: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_plot.setdefault(str(row["plot_code"]), []).append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trend_fields = ["plot_code"]
    for metric in METRICS:
        trend_fields += [f"{metric}_slope_per_year", f"{metric}_r2", f"{metric}_trend"]
    trend_fields += [
        "observations", "usable_observations", "good_count", "partial_count",
        "low_qa_count", "no_data_count", "min_ndvi_month", "min_ndvi",
        "min_ndvi_qa", "latest_month", "latest_ndvi", "latest_qa",
        "latest_good_month", "latest_good_ndvi",
    ]

    summaries: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    for plot_code, plot_rows in sorted(by_plot.items()):
        plot_rows.sort(key=lambda r: str(r["month"]))
        summary: dict[str, object] = {"plot_code": plot_code}
        for metric in METRICS:
            slope, r2 = weighted_slope(plot_rows, metric)
            summary[f"{metric}_slope_per_year"] = f"{slope:.6f}"
            summary[f"{metric}_r2"] = f"{r2:.4f}"
            summary[f"{metric}_trend"] = trend_label(slope, r2)

        usable = [r for r in plot_rows if float(r["weight"]) > 0]
        good = [r for r in plot_rows if r["qa"] == "GOOD"]
        minimum = min(usable, key=lambda r: float(r["median_ndvi"]))
        latest = usable[-1]
        latest_good = good[-1] if good else latest
        summary.update(
            observations=len(plot_rows),
            usable_observations=len(usable),
            good_count=sum(r["qa"] == "GOOD" for r in plot_rows),
            partial_count=sum(r["qa"] == "PARTIAL" for r in plot_rows),
            low_qa_count=sum(r["qa"] == "LOW_QA" for r in plot_rows),
            no_data_count=sum(r["qa"] == "NO_DATA" for r in plot_rows),
            min_ndvi_month=minimum["month"],
            min_ndvi=f'{float(minimum["median_ndvi"]):.4f}',
            min_ndvi_qa=minimum["qa"],
            latest_month=latest["month"],
            latest_ndvi=f'{float(latest["median_ndvi"]):.4f}',
            latest_qa=latest["qa"],
            latest_good_month=latest_good["month"],
            latest_good_ndvi=f'{float(latest_good["median_ndvi"]):.4f}',
        )
        summaries.append(summary)
        event = detect_temporary_dip(plot_rows)
        if event:
            events.append(event)

    with TREND_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=trend_fields)
        writer.writeheader()
        writer.writerows(summaries)

    event_fields = [
        "plot_code", "event", "drop_month", "drop_qa", "ndvi_before",
        "ndvi_drop", "recovery_month", "recovery_qa", "ndvi_recovery", "note",
    ]
    with EVENT_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows(events)

    print(f"wrote {TREND_OUT.relative_to(REPO_ROOT)}")
    print(f"wrote {EVENT_OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
