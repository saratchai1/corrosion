#!/usr/bin/env python3
"""Apply verified planting-completion dates to Samut Songkhram evidence.

The input evidence currently verifies completion dates for 91-STC, 97-STC and
98-STC.  Planting START dates are intentionally left unknown because the
supplied spreadsheet crop does not show them.  Consequently observations on or
before the completion date are labelled BEFORE_COMPLETION_START_UNKNOWN, never
"pre-plant".

For each verified plot this script:
- labels annual satellite scenes relative to the planting-completion date;
- calculates days from completion to each scene;
- identifies the first and latest confirmed post-completion observations;
- summarizes 2025->2026 post-completion WATERLINE and vegetation-edge changes;
- summarizes the 2024->2025 transition without treating 2024 as pre-plant;
- updates the historical summary note so the web no longer says all planting
  dates are unknown.

All movement metrics remain screening evidence.  No causal claim is promoted.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = Path("data/project/samut_songkhram_planting_completion_evidence.csv")
DEFAULT_HISTORY = Path("data/processed/project_preplanting_history/summary.json")
DEFAULT_WEB_HISTORY = Path("web/public/data/project_preplanting_history/summary.json")
DEFAULT_TIMESERIES = Path("data/processed/project_preplanting_history/indicator_timeseries.csv")
DEFAULT_OUTPUT = Path("data/processed/project_planting_aware/summary.json")
DEFAULT_WEB_OUTPUT = Path("web/public/data/project_planting_aware/summary.json")
DEFAULT_METRICS = Path("data/processed/project_planting_aware/per_plot_metrics.csv")
SCREENING_THRESHOLD_M = 20.0


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_position(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def median_or_none(values: Iterable[float]) -> float | None:
    cleaned = [float(value) for value in values if math.isfinite(float(value))]
    return None if not cleaned else round(float(statistics.median(cleaned)), 2)


def classify(delta_m: float) -> str:
    if delta_m > SCREENING_THRESHOLD_M:
        return "APPARENT_SEAWARD"
    if delta_m < -SCREENING_THRESHOLD_M:
        return "APPARENT_LANDWARD"
    return "WITHIN_20M"


def pair_metrics(
    positions: dict[str, dict[int, float]],
    *,
    start_year: int,
    end_year: int,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    elapsed_years = (end_date - start_date).days / 365.2425
    if elapsed_years <= 0:
        raise ValueError("scene pair must be chronological")
    deltas: list[float] = []
    rates: list[float] = []
    classes: Counter[str] = Counter()
    for values in positions.values():
        start = values.get(start_year)
        end = values.get(end_year)
        if start is None or end is None:
            continue
        delta = float(end) - float(start)
        deltas.append(delta)
        rates.append(delta / elapsed_years)
        classes[classify(delta)] += 1
    return {
        "start_year": start_year,
        "end_year": end_year,
        "start_scene_date": start_date.isoformat(),
        "end_scene_date": end_date.isoformat(),
        "elapsed_days": (end_date - start_date).days,
        "paired_transect_count": len(deltas),
        "median_nsm_m": median_or_none(deltas),
        "median_rate_m_per_year": median_or_none(rates),
        "class_counts": {
            "APPARENT_LANDWARD": classes.get("APPARENT_LANDWARD", 0),
            "WITHIN_20M": classes.get("WITHIN_20M", 0),
            "APPARENT_SEAWARD": classes.get("APPARENT_SEAWARD", 0),
        },
        "screening_threshold_m": SCREENING_THRESHOLD_M,
        "confidence": "LOW",
    }


def write_metrics_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "plot_id",
        "indicator",
        "comparison",
        "start_year",
        "end_year",
        "start_scene_date",
        "end_scene_date",
        "elapsed_days",
        "paired_transect_count",
        "median_nsm_m",
        "median_rate_m_per_year",
        "apparent_landward_count",
        "within_20m_count",
        "apparent_seaward_count",
        "confidence",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--web-history", type=Path, default=DEFAULT_WEB_HISTORY)
    parser.add_argument("--timeseries", type=Path, default=DEFAULT_TIMESERIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output", type=Path, default=DEFAULT_WEB_OUTPUT)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    evidence_rows = read_csv(ROOT / args.evidence)
    history = read_json(ROOT / args.history)
    scene_dates = {
        int(scene["year"]): parse_date(scene["date"])
        for scene in history["scene_selection"]["display_scenes"]
    }
    if 2024 not in scene_dates or 2025 not in scene_dates or 2026 not in scene_dates:
        raise ValueError("history summary must contain 2024, 2025 and 2026 scenes")

    evidence: dict[str, dict[str, Any]] = {}
    for row in evidence_rows:
        plot_id = row["plot_id"].strip()
        completion = parse_date(row["planting_completion_date"])
        evidence[plot_id] = {
            "plot_id": plot_id,
            "province": row["province"],
            "area_rai": float(row["area_rai"]),
            "pdd_area_rai": float(row["pdd_area_rai"]),
            "planting_start_date": row.get("planting_start_date") or None,
            "planting_completion_date": completion.isoformat(),
            "source_type": row["source_type"],
            "source_note": row["source_note"],
            "evidence_status": row["evidence_status"],
        }

    positions: dict[tuple[str, str], dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in read_csv(ROOT / args.timeseries):
        if row.get("role") != "TREATMENT":
            continue
        plot_id = (row.get("plot_id") or "").strip()
        if plot_id not in evidence:
            continue
        indicator = (row.get("indicator") or "").strip()
        transect_id = (row.get("transect_id") or "").strip()
        value = parse_position(row.get("position_m_relative_to_2026_waterline"))
        if not indicator or not transect_id or value is None:
            continue
        positions[(plot_id, indicator)][transect_id][int(row["year"])] = value

    verified_plots: list[dict[str, Any]] = []
    flat_metrics: list[dict[str, Any]] = []
    for plot_id in sorted(evidence):
        item = evidence[plot_id]
        completion = parse_date(item["planting_completion_date"])
        scenes = []
        for year, scene_date in sorted(scene_dates.items()):
            relative_days = (scene_date - completion).days
            phase = (
                "CONFIRMED_POST_COMPLETION"
                if scene_date > completion
                else "BEFORE_COMPLETION_START_UNKNOWN"
            )
            scenes.append(
                {
                    "year": year,
                    "scene_date": scene_date.isoformat(),
                    "phase": phase,
                    "days_from_completion": relative_days,
                    "interpretation_th": (
                        "หลังปลูกเสร็จที่ยืนยันแล้ว"
                        if phase == "CONFIRMED_POST_COMPLETION"
                        else "ก่อนวันปลูกเสร็จ แต่ยังไม่ทราบว่าเริ่มปลูกแล้วหรือยัง"
                    ),
                }
            )

        post = [scene for scene in scenes if scene["phase"] == "CONFIRMED_POST_COMPLETION"]
        if len(post) < 2:
            raise RuntimeError(f"{plot_id} has fewer than two confirmed post-completion scenes")
        first_post = post[0]
        latest_post = post[-1]
        last_pre_completion = max(
            (scene for scene in scenes if scene["phase"] == "BEFORE_COMPLETION_START_UNKNOWN"),
            key=lambda value: value["scene_date"],
        )

        indicators: dict[str, Any] = {}
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
            by_transect = positions.get((plot_id, indicator), {})
            transition = pair_metrics(
                by_transect,
                start_year=int(last_pre_completion["year"]),
                end_year=int(first_post["year"]),
                start_date=parse_date(last_pre_completion["scene_date"]),
                end_date=parse_date(first_post["scene_date"]),
            )
            post_change = pair_metrics(
                by_transect,
                start_year=int(first_post["year"]),
                end_year=int(latest_post["year"]),
                start_date=parse_date(first_post["scene_date"]),
                end_date=parse_date(latest_post["scene_date"]),
            )
            indicators[indicator.lower()] = {
                "transition_before_completion_to_first_post": transition,
                "confirmed_post_completion_change": post_change,
                "scientific_guard_th": (
                    "ช่วงเปลี่ยนผ่านไม่ใช่ before-after planting effect เพราะไม่ทราบวันเริ่มปลูก; "
                    "ช่วงหลังปลูกเสร็จมีเพียง 2 annual observations จึงเป็นแนวโน้ม LOW confidence"
                ),
            }
            for comparison, metrics in (
                ("TRANSITION_BEFORE_COMPLETION_TO_FIRST_POST", transition),
                ("CONFIRMED_POST_COMPLETION", post_change),
            ):
                flat_metrics.append(
                    {
                        "plot_id": plot_id,
                        "indicator": indicator,
                        "comparison": comparison,
                        "start_year": metrics["start_year"],
                        "end_year": metrics["end_year"],
                        "start_scene_date": metrics["start_scene_date"],
                        "end_scene_date": metrics["end_scene_date"],
                        "elapsed_days": metrics["elapsed_days"],
                        "paired_transect_count": metrics["paired_transect_count"],
                        "median_nsm_m": metrics["median_nsm_m"],
                        "median_rate_m_per_year": metrics["median_rate_m_per_year"],
                        "apparent_landward_count": metrics["class_counts"]["APPARENT_LANDWARD"],
                        "within_20m_count": metrics["class_counts"]["WITHIN_20M"],
                        "apparent_seaward_count": metrics["class_counts"]["APPARENT_SEAWARD"],
                        "confidence": metrics["confidence"],
                    }
                )

        verified_plots.append(
            {
                **item,
                "scene_phases": scenes,
                "last_before_completion_observation": last_pre_completion,
                "first_confirmed_post_completion_observation": first_post,
                "latest_confirmed_post_completion_observation": latest_post,
                "indicators": indicators,
            }
        )

    total_area = round(sum(item["area_rai"] for item in verified_plots), 2)
    summary = {
        "title": "Samut Songkhram planting-aware coastal evidence",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "PARTIAL_PLANTING_COMPLETION_DATES_VERIFIED",
        "erosion_effect_conclusion": "NOT_DEMONSTRATED",
        "verified_plot_count": len(verified_plots),
        "verified_area_rai": total_area,
        "verified_plot_ids": [item["plot_id"] for item in verified_plots],
        "plots_without_verified_timing": [
            plot_id for plot_id in [f"{value}-STC" for value in range(91, 99)]
            if plot_id not in evidence
        ],
        "timing_interpretation": {
            "confirmed_post_completion_scene_years": [2025, 2026],
            "2024_scene_date": scene_dates[2024].isoformat(),
            "2024_status": "BEFORE_COMPLETION_START_UNKNOWN",
            "2024_guard_th": (
                "ภาพ 15 ก.พ. 2024 อยู่ก่อนวันปลูกเสร็จของทั้ง 3 แปลง แต่ยังเรียกว่าก่อนปลูกไม่ได้ "
                "เพราะหลักฐานที่ได้รับยังไม่ยืนยันวันเริ่มปลูก"
            ),
            "post_completion_guard_th": (
                "ภาพปี 2025 และ 2026 เป็นหลังวันปลูกเสร็จที่ยืนยันแล้วสำหรับ 91-STC, 97-STC และ 98-STC"
            ),
        },
        "plots": verified_plots,
        "allowed_claim_th": (
            "สำหรับ 91-STC, 97-STC และ 98-STC สามารถยืนยันได้ว่าภาพ 2025 และ 2026 เป็นข้อมูลหลังปลูกเสร็จ "
            "และสามารถรายงานแนวโน้มที่พบในช่วงหลังปลูกเสร็จได้ แต่ยังไม่สามารถระบุว่าแนวโน้มดังกล่าวเกิดจากการปลูก"
        ),
        "not_allowed_claim_th": (
            "ยังห้ามเรียกภาพ 2024 ว่า pre-plant และห้ามกล่าวว่าการปลูกทำให้การกัดเซาะหยุดลง "
            "จนกว่าจะมีวันเริ่มปลูกและตรวจ candidate controls/ปัจจัยรบกวน"
        ),
        "limitations": [
            "วันเริ่มปลูกของ 91-STC, 97-STC และ 98-STC ยังไม่ยืนยันจากหลักฐานที่ได้รับ",
            "วันเริ่มและวันปลูกเสร็จของ 92-STC ถึง 96-STC ยังไม่ยืนยัน",
            "หลังปลูกเสร็จมีภาพ annual ที่ยืนยันได้เพียง 2025 และ 2026 จึงมีเพียงสองจุดเวลา",
            "WATERLINE และ MANGROVE_EDGE_PROXY ยังเป็น satellite screening และมีข้อจำกัดด้านความละเอียด/ระดับน้ำ",
            "candidate controls ยังไม่ได้ยืนยันปัจจัยรบกวน จึงไม่ใช่ causal attribution",
        ],
        "source": str(args.evidence),
    }
    write_json(ROOT / args.output, summary)
    write_json(ROOT / args.web_output, summary)
    write_metrics_csv(ROOT / args.metrics, flat_metrics)

    # Correct the old generic intervention note without changing its scientific claim level.
    history["planting_evidence"] = {
        "status": summary["evidence_level"],
        "verified_plot_ids": summary["verified_plot_ids"],
        "verified_area_rai": summary["verified_area_rai"],
        "summary_path": "data/project_planting_aware/summary.json",
    }
    history["periods"]["intervention_note"] = (
        "ยืนยันวันปลูกเสร็จแล้วสำหรับ 91-STC (24 ก.ย. 2024), 97-STC (20 ก.ย. 2024) "
        "และ 98-STC (15 ก.ย. 2024); วันเริ่มปลูกของสามแปลงยังไม่ยืนยัน และ 92–96-STC ยังขาดข้อมูลเวลา"
    )
    write_json(ROOT / args.history, history)
    write_json(ROOT / args.web_history, history)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
