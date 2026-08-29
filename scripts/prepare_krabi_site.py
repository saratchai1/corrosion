#!/usr/bin/env python3
"""Package generated Krabi pilot outputs into a self-contained static site."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGION = REPO_ROOT / "regions" / "krabi"


def copy_required(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Required site input is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_optional(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def read_csv_json(path: Path) -> list[dict[str, object]]:
    numeric_fields = {
        "pdd_area_rai",
        "scene_count",
        "inside_pixel_count",
        "valid_pixel_count",
        "coverage_pct",
        "mean_ndvi",
        "median_ndvi",
        "median_ndre",
        "median_mndwi",
        "median_mfi",
    }
    integer_fields = {"scene_count", "inside_pixel_count", "valid_pixel_count"}
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for source in csv.DictReader(handle):
            row: dict[str, object] = dict(source)
            for key in numeric_fields:
                raw = source.get(key, "")
                if raw == "":
                    row[key] = None
                elif key in integer_fields:
                    row[key] = int(raw)
                else:
                    row[key] = float(raw)
            rows.append(row)
    return rows


def catalog_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return sorted(
            list(csv.DictReader(handle)),
            key=lambda row: (row["acquisition_datetime_utc"], row["scene_id"]),
        )


def find_preview(region: Path, scene_id: str, suffix: str) -> Path | None:
    matches = sorted(
        path
        for path in (region / "data" / "previews" / "sentinel2").rglob("*.png")
        if scene_id in path.name and path.name.endswith(suffix)
    )
    return matches[0] if matches else None


def copy_preview(
    region: Path,
    site: Path,
    row: dict[str, str],
    role: str,
    suffix: str,
) -> dict[str, object] | None:
    source = find_preview(region, row["scene_id"], suffix)
    if source is None:
        return None
    date = row["acquisition_datetime_utc"][:10]
    extension = source.suffix.lower()
    destination = site / "assets" / f"{role}_{date}_{suffix.removeprefix('_').removesuffix('.png')}{extension}"
    copy_required(source, destination)
    return {
        "role": role,
        "date": date,
        "scene_id": row["scene_id"],
        "kind": suffix.removeprefix("_").removesuffix(".png"),
        "path": destination.relative_to(site).as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", type=Path, default=DEFAULT_REGION)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    region = args.region.resolve()
    site = (args.out or region / "site").resolve()
    web = region / "web"
    if not web.exists():
        raise FileNotFoundError(f"Static web source is missing: {web}")

    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(web, site)
    (site / "data").mkdir(parents=True, exist_ok=True)
    (site / "downloads").mkdir(parents=True, exist_ok=True)
    (site / "assets").mkdir(parents=True, exist_ok=True)

    required_data = {
        region / "analysis" / "pilot_summary.json": site / "data" / "pilot_summary.json",
        region / "data" / "aoi" / "krabi_pdd_plots.geojson": site / "data" / "plots.geojson",
        region / "analysis" / "water_consensus" / "epoch_change" / "water_change.geojson": site / "data" / "water_change.geojson",
        region / "analysis" / "water_consensus" / "summary.json": site / "data" / "water_consensus_summary.json",
        region / "analysis" / "scl_water_audit.json": site / "data" / "scl_water_audit.json",
    }
    for source, destination in required_data.items():
        copy_required(source, destination)

    coverage_source = region / "data" / "reuse" / "pdd22_krabi_coverage.csv"
    coverage = read_csv_json(coverage_source)
    (site / "data" / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    download_specs = [
        ("pilot_summary.json", region / "analysis" / "pilot_summary.json", "Executive summary (JSON)"),
        ("pilot_summary.md", region / "analysis" / "pilot_summary.md", "Executive summary (Markdown)"),
        ("vegetation_trends.csv", region / "analysis" / "vegetation_trends.csv", "Vegetation trend table"),
        ("vegetation_events.csv", region / "analysis" / "events.csv", "Vegetation screening events"),
        ("water_history.csv", region / "analysis" / "water_history.csv", "Scene-level water history"),
        ("water_history_summary.json", region / "analysis" / "water_history_summary.json", "Filtered water-history summary"),
        ("scl_water_audit.csv", region / "analysis" / "scl_water_audit.csv", "MNDWI versus SCL audit"),
        ("scl_water_audit.json", region / "analysis" / "scl_water_audit.json", "MNDWI versus SCL audit summary"),
        ("annual_water_consensus.csv", region / "analysis" / "water_consensus" / "annual_summary.csv", "Annual consensus summary"),
        ("water_consensus_summary.json", region / "analysis" / "water_consensus" / "summary.json", "Full consensus summary"),
        ("epoch_change_summary.json", region / "analysis" / "water_consensus" / "epoch_change" / "summary.json", "Epoch change summary"),
        ("plot_change_summary.csv", region / "analysis" / "water_consensus" / "epoch_change" / "plot_change_summary.csv", "Per-plot water screening"),
        ("water_change.geojson", region / "analysis" / "water_consensus" / "epoch_change" / "water_change.geojson", "Candidate water-change polygons"),
        ("plots.geojson", region / "data" / "aoi" / "krabi_pdd_plots.geojson", "Project plot polygons"),
        ("shoreline_corridor_500m.geojson", region / "data" / "aoi" / "krabi_shoreline_corridor_500m.geojson", "500 m analysis corridor"),
        ("sentinel2_scene_catalog.csv", region / "data" / "catalog" / "sentinel2_scenes.csv", "Selected Sentinel-2 Collection 1 scenes"),
        ("calibration_audit.json", region / "data" / "analysis" / "sentinel2_calibration_audit.json", "Radiometric calibration audit"),
    ]
    downloads = []
    for filename, source, label in download_specs:
        destination = site / "downloads" / filename
        if copy_optional(source, destination):
            downloads.append(
                {
                    "label": label,
                    "path": destination.relative_to(site).as_posix(),
                    "filename": filename,
                }
            )

    catalog = catalog_rows(region / "data" / "catalog" / "sentinel2_scenes.csv")
    preview_rows = []
    if catalog:
        for role, row in (("earliest", catalog[0]), ("latest", catalog[-1])):
            for suffix in ("_rgb.png", "_ndvi.png"):
                copied = copy_preview(region, site, row, role, suffix)
                if copied:
                    preview_rows.append(copied)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "branch": os.getenv("GITHUB_REF_NAME", "data/krabi-satellite-v1"),
        "title": "Krabi coastal and mangrove screening pilot",
        "data": {
            "pilot_summary": "data/pilot_summary.json",
            "plots": "data/plots.geojson",
            "water_change": "data/water_change.geojson",
            "water_consensus": "data/water_consensus_summary.json",
            "coverage": "data/coverage.json",
            "scl_audit": "data/scl_water_audit.json",
        },
        "previews": preview_rows,
        "downloads": downloads,
    }
    (site / "data" / "site_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (site / ".nojekyll").write_text("", encoding="utf-8")

    expected = [
        site / "index.html",
        site / "app.js",
        site / "styles.css",
        site / "data" / "pilot_summary.json",
        site / "data" / "coverage.json",
        site / "data" / "plots.geojson",
        site / "data" / "water_change.geojson",
        site / "data" / "site_manifest.json",
    ]
    missing = [str(path) for path in expected if not path.exists() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError("Static site package is incomplete: " + ", ".join(missing))
    print(
        json.dumps(
            {
                "site": str(site),
                "file_count": sum(1 for path in site.rglob("*") if path.is_file()),
                "download_count": len(downloads),
                "preview_count": len(preview_rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
