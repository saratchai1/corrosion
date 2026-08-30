#!/usr/bin/env python3
"""Classify Samut Songkhram plots for coastal-erosion screening.

The tide-aware edge workflow creates transects from the 2026 image-derived
waterline. A project plot should not be forced into a coastal-erosion analysis
when no coastal waterline is present within the configured analysis range.
This post-processing step distinguishes:

- plots with intersecting coastal transects that are screenable;
- plots with no coastal waterline within the analysis range, which are excluded
  from a coastal-erosion claim but may still be assessed as canal/bank settings
  with UAV or field evidence; and
- plots close to the extracted waterline but lacking an intersecting transect,
  which require manual geometry review.

This classification does not prove erosion reduction. It only defines where the
satellite coastal-frontage comparison is applicable.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[1]
CRS_WEB = "EPSG:4326"
CRS_ANALYSIS = "EPSG:32647"
TO_UTM = Transformer.from_crs(CRS_WEB, CRS_ANALYSIS, always_xy=True)

DEFAULT_PLOTS = Path("data/aoi/samut_songkhram_project_plots.geojson")
DEFAULT_WATERLINE = Path(
    "data/processed/project_tide_aware/waterline/2026.geojson"
)
DEFAULT_SUMMARY = Path("data/processed/project_tide_aware/summary.json")
DEFAULT_WEB_SUMMARY = Path("web/public/data/project_tide_aware/summary.json")
DEFAULT_OUTPUT = Path(
    "data/processed/project_tide_aware/plot_coastal_eligibility.csv"
)
DEFAULT_WEB_OUTPUT = Path(
    "web/public/data/project_tide_aware/plot_coastal_eligibility.csv"
)
DEFAULT_WEB_INDEX = Path("web/public/data/project_tide_aware/index.json")
DEFAULT_MAX_FRONTAGE_DISTANCE_M = 3500.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("plot eligibility output cannot be empty")
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def classify_plot(
    *,
    treatment_transect_count: int,
    distance_to_reference_waterline_m: float,
    maximum_frontage_distance_m: float,
) -> dict[str, str]:
    """Return a conservative coastal-frontage eligibility classification."""
    if treatment_transect_count > 0:
        return {
            "eligibility_status": "COASTAL_FRONTAGE_SCREENABLE",
            "coastal_erosion_scope": "INCLUDED_IN_COASTAL_SCREENING",
            "required_follow_up": (
                "verify candidate controls and validate edge with repeated UAV/field data"
            ),
        }
    if distance_to_reference_waterline_m > maximum_frontage_distance_m:
        return {
            "eligibility_status": "NO_COASTAL_WATERLINE_WITHIN_ANALYSIS_RANGE",
            "coastal_erosion_scope": "EXCLUDED_FROM_COASTAL_SCREENING",
            "required_follow_up": (
                "treat as a possible canal/bank or inland setting; use UAV/field BANK_EDGE "
                "evidence before making any erosion claim"
            ),
        }
    return {
        "eligibility_status": "NO_INTERSECTING_TRANSECT_REVIEW_REQUIRED",
        "coastal_erosion_scope": "MANUAL_REVIEW_REQUIRED",
        "required_follow_up": (
            "review waterline extraction, plot geometry and transect orientation manually"
        ),
    }


def load_reference_waterline(path: Path) -> Any:
    collection = read_json(path)
    geometries = [
        transform(TO_UTM.transform, shape(feature["geometry"]))
        for feature in collection.get("features", [])
    ]
    if not geometries:
        raise ValueError(f"reference waterline contains no features: {path}")
    waterline = unary_union(geometries)
    if waterline.is_empty:
        raise ValueError(f"reference waterline is empty: {path}")
    return waterline


def build_records(
    *,
    plot_collection: dict[str, Any],
    reference_waterline: Any,
    treatment_count_by_plot: dict[str, int],
    maximum_frontage_distance_m: float,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for feature in plot_collection.get("features", []):
        plot_id = str(feature["properties"]["plot_id"])
        geometry_utm = transform(
            TO_UTM.transform, shape(feature["geometry"])
        ).buffer(0)
        if geometry_utm.is_empty:
            raise ValueError(f"empty project geometry for {plot_id}")
        distance = float(geometry_utm.distance(reference_waterline))
        if not math.isfinite(distance):
            raise ValueError(f"non-finite waterline distance for {plot_id}")
        treatment_count = int(treatment_count_by_plot.get(plot_id, 0))
        classification = classify_plot(
            treatment_transect_count=treatment_count,
            distance_to_reference_waterline_m=distance,
            maximum_frontage_distance_m=maximum_frontage_distance_m,
        )
        records.append(
            {
                "plot_id": plot_id,
                "official_participating_area_rai": feature["properties"].get(
                    "official_participating_area_rai"
                ),
                "treatment_transect_count": treatment_count,
                "distance_to_2026_waterline_m": round(distance, 2),
                "maximum_frontage_distance_m": round(
                    maximum_frontage_distance_m, 2
                ),
                **classification,
                "reference_indicator": "2026_TIDE_SCREENED_IMAGE_DERIVED_WATERLINE",
                "confidence": "LOW",
            }
        )
    records.sort(key=lambda row: row["plot_id"])
    return records


def annotate_summary(
    summary: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    maximum_frontage_distance_m: float,
    output_path: Path,
) -> dict[str, Any]:
    by_plot = {row["plot_id"]: row for row in records}
    plot_ids = set(summary.get("plot_ids", []))
    if plot_ids != set(by_plot):
        raise ValueError(
            "plot eligibility does not cover the same plot IDs as summary: "
            f"summary={sorted(plot_ids)}, eligibility={sorted(by_plot)}"
        )

    screenable = sorted(
        row["plot_id"]
        for row in records
        if row["coastal_erosion_scope"] == "INCLUDED_IN_COASTAL_SCREENING"
    )
    excluded = sorted(
        row["plot_id"]
        for row in records
        if row["coastal_erosion_scope"] == "EXCLUDED_FROM_COASTAL_SCREENING"
    )
    review = sorted(
        row["plot_id"]
        for row in records
        if row["coastal_erosion_scope"] == "MANUAL_REVIEW_REQUIRED"
    )

    missing = set(
        summary.get("transects", {}).get(
            "plots_without_treatment_transects", []
        )
    )
    explained = sorted(missing.intersection(excluded))
    unresolved = sorted(missing.difference(excluded))

    summary["coastal_eligibility"] = {
        "method": (
            "plot has at least one transect intersecting the project geometry; "
            "otherwise distance to the 2026 tide-screened image-derived waterline "
            "is compared with the analysis range"
        ),
        "reference_year": 2026,
        "reference_indicator": "WATERLINE",
        "maximum_frontage_distance_m": maximum_frontage_distance_m,
        "screenable_plot_count": len(screenable),
        "screenable_plot_ids": screenable,
        "excluded_plot_count": len(excluded),
        "excluded_plot_ids": excluded,
        "manual_review_plot_count": len(review),
        "manual_review_plot_ids": review,
        "output_csv": str(output_path),
        "scientific_limit": (
            "This is an applicability gate, not evidence that planting reduced erosion. "
            "Excluded plots may require a separate BANK_EDGE analysis using UAV or field data."
        ),
    }

    transects = summary.setdefault("transects", {})
    transects["plots_without_treatment_transects_explained_by_eligibility"] = (
        explained
    )
    transects["unresolved_missing_treatment_plot_ids"] = unresolved

    controls = summary.setdefault("controls", {})
    selected_counts = controls.get("selected_count_by_plot", {})
    controls["screenable_plot_ids"] = screenable
    controls["screenable_plots_without_candidate_controls"] = sorted(
        plot_id for plot_id in screenable if int(selected_counts.get(plot_id, 0)) < 1
    )

    for item in summary.get("per_plot", []):
        plot_id = item.get("plot_id")
        record = by_plot.get(plot_id)
        if record is None:
            continue
        item["coastal_eligibility"] = {
            "eligibility_status": record["eligibility_status"],
            "coastal_erosion_scope": record["coastal_erosion_scope"],
            "treatment_transect_count": record["treatment_transect_count"],
            "distance_to_2026_waterline_m": record[
                "distance_to_2026_waterline_m"
            ],
            "required_follow_up": record["required_follow_up"],
        }

    limitation = (
        "แปลงที่ไม่มีแนวน้ำชายฝั่งภายในระยะวิเคราะห์จะไม่ถูกนำไปรวมในผล"
        "การกัดเซาะชายฝั่ง และต้องประเมินขอบตลิ่งหรือขอบคลองแยกด้วยโดรน/ภาคสนาม"
    )
    limitations = summary.setdefault("limitations", [])
    if limitation not in limitations:
        limitations.append(limitation)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plots", type=Path, default=DEFAULT_PLOTS)
    parser.add_argument("--waterline", type=Path, default=DEFAULT_WATERLINE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--web-summary", type=Path, default=DEFAULT_WEB_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output", type=Path, default=DEFAULT_WEB_OUTPUT)
    parser.add_argument("--web-index", type=Path, default=DEFAULT_WEB_INDEX)
    parser.add_argument(
        "--maximum-frontage-distance-m",
        type=float,
        default=DEFAULT_MAX_FRONTAGE_DISTANCE_M,
    )
    args = parser.parse_args()

    plots_path = ROOT / args.plots
    waterline_path = ROOT / args.waterline
    summary_path = ROOT / args.summary
    web_summary_path = ROOT / args.web_summary
    output_path = ROOT / args.output
    web_output_path = ROOT / args.web_output
    web_index_path = ROOT / args.web_index

    if args.maximum_frontage_distance_m <= 0:
        raise SystemExit("maximum frontage distance must be positive")

    plot_collection = read_json(plots_path)
    summary = read_json(summary_path)
    waterline = load_reference_waterline(waterline_path)
    treatment_counts = {
        str(plot_id): int(count)
        for plot_id, count in summary.get("transects", {})
        .get("treatment_count_by_plot", {})
        .items()
    }
    records = build_records(
        plot_collection=plot_collection,
        reference_waterline=waterline,
        treatment_count_by_plot=treatment_counts,
        maximum_frontage_distance_m=args.maximum_frontage_distance_m,
    )
    write_csv(output_path, records)
    write_csv(web_output_path, records)

    summary = annotate_summary(
        summary,
        records,
        maximum_frontage_distance_m=args.maximum_frontage_distance_m,
        output_path=args.output,
    )
    write_json(summary_path, summary)
    write_json(web_summary_path, summary)

    index = read_json(web_index_path)
    index["plot_coastal_eligibility"] = "plot_coastal_eligibility.csv"
    write_json(web_index_path, index)

    print(
        json.dumps(
            {
                "plot_count": len(records),
                "screenable_plot_ids": summary["coastal_eligibility"][
                    "screenable_plot_ids"
                ],
                "excluded_plot_ids": summary["coastal_eligibility"][
                    "excluded_plot_ids"
                ],
                "manual_review_plot_ids": summary["coastal_eligibility"][
                    "manual_review_plot_ids"
                ],
                "unresolved_missing_treatment_plot_ids": summary["transects"][
                    "unresolved_missing_treatment_plot_ids"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
