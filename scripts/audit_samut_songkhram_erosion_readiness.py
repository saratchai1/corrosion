#!/usr/bin/env python3
"""Audit readiness for a free-data coastal-erosion claim in Samut Songkhram.

The audit is deliberately conservative. It reports the highest evidence level
supported by versioned satellite, tide, transect, drone, field, intervention,
and control metadata. It never upgrades a claim from greenness alone.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("config/samut_songkhram_erosion_free_data_v1.json")
DEFAULT_MATCHED_CATALOG = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
)
DEFAULT_SOURCE_CATALOG = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes.csv"
)
DEFAULT_SUMMARY = Path("data/processed/project_impact/summary.json")
DEFAULT_DRONE = Path("data/field/samut_songkhram/drone_surveys.csv")
DEFAULT_FIELD = Path("data/field/samut_songkhram/boundary_observations.csv")
DEFAULT_OUTPUT = Path("data/processed/project_impact/erosion_readiness.json")
MATCHED_TIDE_PREFIXES = ("predicted_", "observed_", "modelled_", "matched_")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON not found: {path}")
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def read_csv(path: Path, *, required: bool = True) -> list[dict[str, str]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"CSV not found: {path}")
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader)


def choose_scene_catalog(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if DEFAULT_MATCHED_CATALOG.exists():
        return DEFAULT_MATCHED_CATALOG
    return DEFAULT_SOURCE_CATALOG


def tide_is_matched(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized.startswith(MATCHED_TIDE_PREFIXES)


def unique_years(rows: list[dict[str, str]]) -> list[int]:
    years = set()
    for row in rows:
        text = row.get("acquisition_datetime_utc", "") or row.get(
            "acquisition_datetime_bangkok", ""
        )
        if len(text) >= 4 and text[:4].isdigit():
            years.add(int(text[:4]))
    return sorted(years)


def survey_repeats_by_plot(
    rows: list[dict[str, str]], *, survey_key: str
) -> dict[str, int]:
    values: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(rows, start=1):
        plot_id = row.get("plot_id", "").strip()
        if not plot_id:
            continue
        survey_id = row.get(survey_key, "").strip() or f"row-{index}"
        values[plot_id].add(survey_id)
    return {plot_id: len(surveys) for plot_id, surveys in sorted(values.items())}


def build_readiness(
    config: dict[str, Any],
    scenes: list[dict[str, str]],
    summary: dict[str, Any],
    drone_rows: list[dict[str, str]],
    field_rows: list[dict[str, str]],
    *,
    source_paths: dict[str, str],
) -> dict[str, Any]:
    plot_ids = list(config["scope"]["plot_ids"])
    plot_count = len(plot_ids)
    tide_status_counts = Counter(
        (row.get("tide_status") or "missing").strip() or "missing" for row in scenes
    )
    tide_matched_count = sum(
        count for status, count in tide_status_counts.items() if tide_is_matched(status)
    )
    tide_fraction = tide_matched_count / max(len(scenes), 1)

    boundary = summary.get("post_boundary_evidence", {})
    transect_count = int(boundary.get("transect_count") or 0)
    boundary_period = boundary.get("period")
    covered_plots = sorted(
        item.get("plot_id")
        for item in boundary.get("per_plot", [])
        if item.get("plot_id") and int(item.get("transect_count") or 0) > 0
    )
    uncovered_plots = sorted(set(plot_ids).difference(covered_plots))

    drone_repeats = survey_repeats_by_plot(drone_rows, survey_key="survey_id")
    field_repeats = survey_repeats_by_plot(field_rows, survey_key="observation_id")
    required_drone_repeats = int(
        config["drone"]["minimum_repeat_surveys_per_plot_for_observed_stabilization"]
    )
    drone_ready_plots = sorted(
        plot_id
        for plot_id in plot_ids
        if drone_repeats.get(plot_id, 0) >= required_drone_repeats
    )
    field_ready_plots = sorted(
        plot_id for plot_id in plot_ids if field_repeats.get(plot_id, 0) >= 1
    )

    exact_intervention_date_verified = (
        config["intervention"]["exact_date_status"] == "VERIFIED"
    )
    controls_verified = config["controls"]["status"] == "VERIFIED"
    minimum_tide_fraction = float(
        config["evidence_gates"]["minimum_tide_matched_scene_fraction"]
    )
    minimum_post_years = int(
        config["evidence_gates"]["minimum_post_years_for_comparative_effect"]
    )
    post_years = list(config["analysis_period"]["post_years"])

    satellite_screening = len(scenes) > 0 and transect_count > 0
    tide_aware_screening = satellite_screening and tide_fraction >= minimum_tide_fraction
    observed_stabilization = all(
        [
            tide_aware_screening,
            exact_intervention_date_verified,
            not uncovered_plots,
            len(drone_ready_plots) == plot_count,
            len(field_ready_plots) == plot_count,
        ]
    )
    comparative_effect = all(
        [
            observed_stabilization,
            controls_verified,
            len(post_years) >= minimum_post_years,
        ]
    )

    if comparative_effect:
        evidence_level = "COMPARATIVE_EFFECT"
        allowed_claim = config["claim_language"]["comparative_effect"]
    elif observed_stabilization:
        evidence_level = "OBSERVED_STABILIZATION"
        allowed_claim = config["claim_language"]["observed_stabilization"]
    elif tide_aware_screening:
        evidence_level = "TIDE_AWARE_SCREENING"
        allowed_claim = config["claim_language"]["tide_aware_screening"]
    elif satellite_screening:
        evidence_level = "SATELLITE_SCREENING"
        allowed_claim = config["claim_language"]["satellite_screening"]
    else:
        evidence_level = "INSUFFICIENT_DATA"
        allowed_claim = config["claim_language"]["insufficient_data"]

    blockers = []
    if not exact_intervention_date_verified:
        blockers.append("exact planting date is not verified")
    if tide_fraction < minimum_tide_fraction:
        blockers.append(
            f"tide-matched scene coverage is {tide_fraction:.1%}; "
            f"target is at least {minimum_tide_fraction:.1%}"
        )
    if uncovered_plots:
        blockers.append(
            "boundary transects do not cover: " + ", ".join(uncovered_plots)
        )
    missing_drone = sorted(set(plot_ids).difference(drone_ready_plots))
    if missing_drone:
        blockers.append(
            f"fewer than {required_drone_repeats} repeat drone surveys for: "
            + ", ".join(missing_drone)
        )
    missing_field = sorted(set(plot_ids).difference(field_ready_plots))
    if missing_field:
        blockers.append("no field boundary observation for: " + ", ".join(missing_field))
    if not controls_verified:
        blockers.append("coastal control segments are not verified")
    if len(post_years) < minimum_post_years:
        blockers.append(
            f"only {len(post_years)} configured post years; "
            f"need at least {minimum_post_years}"
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": config["project_id"],
        "evidence_level": evidence_level,
        "allowed_claim_th": allowed_claim,
        "erosion_effect_demonstrated": comparative_effect,
        "satellite": {
            "scene_count": len(scenes),
            "years": unique_years(scenes),
            "tide_matched_scene_count": tide_matched_count,
            "tide_matched_scene_fraction": round(tide_fraction, 5),
            "tide_status_counts": dict(sorted(tide_status_counts.items())),
        },
        "boundary": {
            "indicator": boundary.get("feature"),
            "period": boundary_period,
            "transect_count": transect_count,
            "covered_plot_ids": covered_plots,
            "uncovered_plot_ids": uncovered_plots,
            "tide_status": boundary.get("tide_status"),
            "confidence": boundary.get("confidence"),
        },
        "intervention": {
            "nominal_year": config["intervention"]["nominal_year"],
            "exact_date_status": config["intervention"]["exact_date_status"],
        },
        "controls": {
            "status": config["controls"]["status"],
            "target_count_per_treatment_segment": config["controls"][
                "target_count_per_treatment_segment"
            ],
        },
        "drone": {
            "row_count": len(drone_rows),
            "repeat_surveys_by_plot": drone_repeats,
            "ready_plot_ids": drone_ready_plots,
        },
        "field": {
            "row_count": len(field_rows),
            "observations_by_plot": field_repeats,
            "ready_plot_ids": field_ready_plots,
        },
        "blockers": blockers,
        "prohibited_claims_th": config["claim_language"]["prohibited"],
        "source_paths": source_paths,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scene-catalog", type=Path)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--drone-metadata", type=Path, default=DEFAULT_DRONE)
    parser.add_argument("--field-observations", type=Path, default=DEFAULT_FIELD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scene_catalog = choose_scene_catalog(args.scene_catalog)
    try:
        config = load_json(args.config)
        summary = load_json(args.summary)
        scenes = read_csv(scene_catalog)
        drone_rows = read_csv(args.drone_metadata, required=False)
        field_rows = read_csv(args.field_observations, required=False)
        result = build_readiness(
            config,
            scenes,
            summary,
            drone_rows,
            field_rows,
            source_paths={
                "config": str(args.config),
                "scene_catalog": str(scene_catalog),
                "summary": str(args.summary),
                "drone_metadata": str(args.drone_metadata),
                "field_observations": str(args.field_observations),
            },
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
