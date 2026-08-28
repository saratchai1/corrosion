#!/usr/bin/env python3
"""Download a bounded historical optical subset for the coastal-change MVP."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


EPOCHS = [
    {"target_year": 1985, "actual_year": 1987, "dataset": "landsat", "count": 2},
    {"target_year": 1990, "actual_year": 1990, "dataset": "landsat", "count": 3},
    {"target_year": 2000, "actual_year": 2000, "dataset": "landsat", "count": 3},
    {
        "target_year": 2010,
        "actual_year": 2009,
        "dataset": "landsat",
        "count": 3,
        "platforms": "landsat-5",
        "quality_pool_multiplier": 4,
    },
    {"target_year": 2018, "actual_year": 2018, "dataset": "sentinel2", "count": 3},
    {"target_year": 2020, "actual_year": 2020, "dataset": "sentinel2", "count": 3},
    {"target_year": 2025, "actual_year": 2025, "dataset": "sentinel2", "count": 3},
    {"target_year": 2026, "actual_year": 2026, "dataset": "sentinel2", "count": 3},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--epochs",
        help="Comma-separated target years; default downloads all MVP epochs",
    )
    parser.add_argument(
        "--catalog", default="data/catalog/mvp_optical_scenes.csv"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    requested = (
        {int(value) for value in args.epochs.split(",")}
        if args.epochs
        else {entry["target_year"] for entry in EPOCHS}
    )
    selected = [entry for entry in EPOCHS if entry["target_year"] in requested]
    missing = requested - {entry["target_year"] for entry in selected}
    if missing:
        parser.error(f"unknown target epoch(s): {sorted(missing)}")

    for entry in selected:
        actual = entry["actual_year"]
        command = [
            sys.executable,
            "-u",
            "scripts/download_satellite_data.py",
            entry["dataset"],
            "--start",
            f"{actual}-01-01",
            "--end",
            f"{actual}-12-31",
            "--per-year",
            str(entry["count"]),
            "--quality-pool-multiplier",
            str(entry.get("quality_pool_multiplier", 1)),
            "--catalog",
            args.catalog,
            "--skip-previews",
        ]
        if entry["dataset"] == "landsat":
            command.extend(["--bands", "BLUE,GREEN,RED,NIR,SWIR1,QA_PIXEL"])
        else:
            command.extend(["--bands", "B2,B3,B4,B8,B11,SCL"])
        if entry.get("platforms"):
            command.extend(["--platforms", str(entry["platforms"])])
        if args.dry_run:
            command.append("--dry-run")
        else:
            command.extend(["--download", "--max-downloads", str(entry["count"])])
        if args.overwrite:
            command.append("--overwrite")
        print(
            f"MVP epoch target={entry['target_year']} actual={actual} "
            f"dataset={entry['dataset']} acquisitions={entry['count']}",
            flush=True,
        )
        subprocess.run(command, check=True)

    metadata_path = Path("data/catalog/mvp_epochs.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "description": "Historical optical epochs for the coastal-change MVP",
                "tide_status": "unverified",
                "epochs": EPOCHS,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
