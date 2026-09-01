#!/usr/bin/env python3
"""Aggregate Samut Songkhram drone orthomosaic inspection products."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/project/samut_songkhram_drone_drive_manifest.csv"
DEFAULT_RAW = ROOT / "data/processed/samut_songkhram_drone/raw"
DEFAULT_OUTPUT = ROOT / "data/processed/samut_songkhram_drone"
DEFAULT_WEB = ROOT / "web/public/data/project_drone_orthomosaic"
DEFAULT_SCENES = ROOT / "data/processed/project_preplanting_history/summary.json"
DEFAULT_PLANTING = ROOT / "data/processed/project_planting_aware/summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output-dir", type=Path, default=DEFAULT_WEB)
    parser.add_argument("--scene-summary", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--planting-summary", type=Path, default=DEFAULT_PLANTING)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_iso(value: str) -> date:
    return date.fromisoformat(value)


def main() -> int:
    args = parse_args()
    manifest_path = resolve(args.manifest)
    raw_dir = resolve(args.raw_dir)
    output_dir = resolve(args.output_dir)
    web_dir = resolve(args.web_output_dir)
    scene_path = resolve(args.scene_summary)
    planting_path = resolve(args.planting_summary)

    manifest = read_csv(manifest_path)
    expected = [row["plot_id"] for row in manifest]
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for plot_id in expected:
        path = raw_dir / f"{plot_id}.json"
        if not path.exists():
            missing.append(plot_id)
            continue
        records.append(read_json(path))

    if missing:
        raise SystemExit(f"missing inspected drone metadata for: {', '.join(missing)}")
    if len(records) != 9:
        raise SystemExit(f"expected 9 orthomosaics, found {len(records)}")

    scenes = read_json(scene_path) if scene_path.exists() else {}
    scene_rows = scenes.get("scene_selection", {}).get("display_scenes", [])
    scene_dates = [
        {
            "year": int(row["year"]),
            "date": str(row["date"]),
            "waterline_accepted": bool(row.get("waterline_accepted")),
        }
        for row in scene_rows
        if row.get("date")
    ]

    planting = read_json(planting_path) if planting_path.exists() else {}
    planting_by_plot = {row["plot_id"]: row for row in planting.get("plots", [])}

    catalog_rows: list[dict[str, Any]] = []
    footprints: list[dict[str, Any]] = []
    provisional_dates: list[str] = []
    gsd_values: list[float] = []
    crs_values: set[str] = set()
    total_size = 0

    for record in records:
        source = record["source"]
        raster = record["raster"]
        alignment = record["plot_alignment"]
        qa = record["qa"]
        plot_id = record["plot_id"]
        total_size += int(source["actual_size_bytes"])
        if raster.get("mean_gsd_cm") is not None:
            gsd_values.append(float(raster["mean_gsd_cm"]))
        crs_values.add(str(raster["crs"]))
        provisional_dates.append(str(source["folder_date_iso"]))

        folder_date = parse_iso(source["folder_date_iso"])
        nearest_scene = None
        if scene_dates:
            nearest_scene = min(
                scene_dates,
                key=lambda row: abs((parse_iso(row["date"]) - folder_date).days),
            )
            nearest_days = (parse_iso(nearest_scene["date"]) - folder_date).days
        else:
            nearest_days = None

        planting_row = planting_by_plot.get(plot_id)
        days_after_completion = None
        completion_status = "NO_VERIFIED_COMPLETION_DATE"
        if planting_row and planting_row.get("planting_completion_date"):
            completion_date = parse_iso(planting_row["planting_completion_date"])
            days_after_completion = (folder_date - completion_date).days
            completion_status = (
                "PROVISIONAL_POST_COMPLETION_IF_FOLDER_DATE_IS_FLIGHT_DATE"
                if days_after_completion >= 0
                else "PROVISIONAL_PRE_COMPLETION_IF_FOLDER_DATE_IS_FLIGHT_DATE"
            )

        catalog_rows.append(
            {
                "plot_id": plot_id,
                "drive_title": source["drive_title"],
                "drive_file_id": source["drive_file_id"],
                "size_bytes": source["actual_size_bytes"],
                "crs": raster["crs"],
                "width_px": raster["width_px"],
                "height_px": raster["height_px"],
                "band_count": raster["band_count"],
                "mean_gsd_cm": raster["mean_gsd_cm"],
                "bbox_plot_coverage_fraction": alignment["plot_bbox_coverage_fraction"],
                "plot_valid_image_fraction": alignment["plot_valid_image_fraction"],
                "georeference_status": qa["georeference_status"],
                "analysis_readiness": qa["analysis_readiness"],
                "folder_date_iso": source["folder_date_iso"],
                "folder_date_status": source["folder_date_status"],
                "flight_date_verified": source["flight_date_verified"],
                "verified_planting_completion_date": (
                    None if planting_row is None else planting_row.get("planting_completion_date")
                ),
                "provisional_days_from_completion": days_after_completion,
                "provisional_planting_phase": completion_status,
                "nearest_sentinel2_date": None if nearest_scene is None else nearest_scene["date"],
                "nearest_sentinel2_year": None if nearest_scene is None else nearest_scene["year"],
                "nearest_sentinel2_day_gap": nearest_days,
                "nearest_sentinel2_waterline_accepted": (
                    None if nearest_scene is None else nearest_scene["waterline_accepted"]
                ),
                "preview": record["preview"]["preview_path"].replace("web/public/", ""),
            }
        )

        footprint_path = raw_dir / f"{plot_id}.footprint.geojson"
        footprint = read_json(footprint_path)
        footprints.extend(footprint.get("features", []))

    catalog_rows.sort(key=lambda row: row["plot_id"])
    footprints.sort(key=lambda feature: feature.get("properties", {}).get("plot_id", ""))

    all_pass = all(row["georeference_status"] == "PASS" for row in catalog_rows)
    all_cover = all(float(row["bbox_plot_coverage_fraction"] or 0) >= 0.98 for row in catalog_rows)
    all_valid = all(float(row["plot_valid_image_fraction"] or 0) >= 0.95 for row in catalog_rows)
    unique_folder_dates = sorted(set(provisional_dates))

    summary = {
        "title": "Samut Songkhram drone orthomosaic inventory",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "orthomosaic_count": len(catalog_rows),
        "plot_ids": [row["plot_id"] for row in catalog_rows],
        "total_source_size_bytes": total_size,
        "total_source_size_gib": round(total_size / (1024 ** 3), 3),
        "common_crs": sorted(crs_values),
        "gsd_cm_range": [round(min(gsd_values), 4), round(max(gsd_values), 4)] if gsd_values else None,
        "qa": {
            "all_georeference_pass": all_pass,
            "all_plot_bbox_coverage_ge_98pct": all_cover,
            "all_plot_valid_imagery_ge_95pct": all_valid,
            "ready_plot_count": sum(row["analysis_readiness"].startswith("READY") for row in catalog_rows),
        },
        "date_evidence": {
            "folder_labels": unique_folder_dates,
            "status": "UNVERIFIED_AS_FLIGHT_DATE",
            "interpretation": (
                "The shared folder label 25-12-2567 maps to 2024-12-25, but the "
                "workflow does not treat that date as verified acquisition time. "
                "Flight logs, EXIF, photogrammetry project files, or another project "
                "record are required before using it as an intervention-timing claim."
            ),
        },
        "satellite_alignment": {
            "method": "nearest annual Sentinel-2 display scene to the provisional folder date",
            "scientific_guard": (
                "Nearest-date pairing is for visual/geometric cross-checking only. "
                "It is not a same-day radiometric comparison and does not create a "
                "drone-derived erosion rate from a single orthomosaic epoch."
            ),
        },
        "scientific_scope": {
            "can_do_now": [
                "verify CRS, pixel size and spatial coverage of each orthomosaic",
                "use drone imagery as a high-resolution baseline for plot boundary, vegetation-edge and bank-edge review",
                "cross-check Sentinel-2-derived edge positions against the drone baseline",
                "prioritize anomalous satellite transects for manual drone inspection",
            ],
            "cannot_claim_yet": [
                "drone-derived shoreline erosion rate, because only one drone epoch is registered",
                "causal erosion reduction from planting, because repeat drone epochs and verified controls are still required",
                "2024-12-25 as the exact flight date until source timing is independently verified",
            ],
        },
        "plots": catalog_rows,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "footprints.geojson", {"type": "FeatureCollection", "features": footprints})
    write_csv(output_dir / "orthomosaic_catalog.csv", catalog_rows)

    write_json(web_dir / "summary.json", summary)
    write_json(web_dir / "footprints.geojson", {"type": "FeatureCollection", "features": footprints})
    write_csv(web_dir / "orthomosaic_catalog.csv", catalog_rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not all_pass:
        raise SystemExit("one or more drone orthomosaics require georeference review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
