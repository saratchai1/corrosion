#!/usr/bin/env python3
"""Download same-season Sentinel-2 inputs for the 2024 planting assessment."""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path


YEARS = [2023, 2024, 2025, 2026]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--catalog",
        default="data/catalog/project_samut_songkhram_sentinel2_scenes.csv",
    )
    args = parser.parse_args()
    combined_rows = []
    fieldnames = None
    with tempfile.TemporaryDirectory(prefix="project-impact-catalog-") as temp_dir:
        for year in YEARS:
            year_catalog = Path(temp_dir) / f"{year}.csv"
            command = [
                sys.executable,
                "-u",
                "scripts/download_satellite_data.py",
                "sentinel2",
                "--aoi",
                "data/aoi/samut_songkhram_project_analysis_aoi.geojson",
                "--start",
                f"{year}-01-01",
                "--end",
                f"{year}-04-30",
                "--per-year",
                "3",
                "--quality-pool-multiplier",
                "4",
                "--bands",
                "B2,B3,B4,B8,B11,SCL",
                "--catalog",
                str(year_catalog),
                "--output-root",
                "data/satellite/project_samut_songkhram",
                "--skip-previews",
            ]
            if args.dry_run:
                command.append("--dry-run")
            else:
                command.extend(["--download", "--max-downloads", "3"])
            if args.overwrite:
                command.append("--overwrite")
            subprocess.run(command, check=True)
            with year_catalog.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames
                combined_rows.extend(reader)
    if not fieldnames:
        raise RuntimeError("no project scene catalog rows were generated")
    combined_rows.sort(
        key=lambda row: (row["acquisition_datetime_utc"], row["scene_id"])
    )
    output = Path(args.catalog)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(combined_rows)


if __name__ == "__main__":
    main()
