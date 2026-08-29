#!/usr/bin/env python3
"""Run cloud-masked MNDWI water extraction for selected Sentinel-2 catalog scenes."""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXTRACTOR = SCRIPT_DIR / "extract_water_mask.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Process Sentinel-2 scene catalog into annual water masks")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--satellite-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--tide-status", choices=["verified", "unverified"], default="unverified")
    args = parser.parse_args()

    with args.catalog.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    processed_dates: set[str] = set()
    processed = 0
    for row in sorted(rows, key=lambda item: (item["acquisition_datetime_utc"], item["scene_id"])):
        date = row["acquisition_datetime_utc"][:10]
        scene_id = row["scene_id"]
        if date in processed_dates:
            # The Krabi corridor currently fits one Sentinel-2 tile. If a future AOI
            # crosses tiles, mosaic support should be added rather than double-counting.
            print(f"skip duplicate acquisition date {date}: {scene_id}")
            continue

        year = date[:4]
        scene_dir = args.satellite_root / year / scene_id
        green = scene_dir / "B3_10m.tif"
        swir = scene_dir / "B11_20m.tif"
        scl = scene_dir / "SCL_20m.tif"
        missing = [path for path in (green, swir, scl) if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f"Selected scene {scene_id} is missing required bands: "
                + ", ".join(str(path) for path in missing)
            )

        out_dir = args.out_root / date
        cmd = [
            sys.executable,
            str(EXTRACTOR),
            "--green", str(green),
            "--swir", str(swir),
            "--quality-mask", str(scl),
            "--sensor", "sentinel2",
            "--date", date,
            "--out-dir", str(out_dir),
            "--tide-status", args.tide_status,
        ]
        print("run:", " ".join(cmd))
        subprocess.run(cmd, check=True)
        processed_dates.add(date)
        processed += 1

    if processed == 0:
        raise SystemExit("No Sentinel-2 scenes were processed")
    print(f"processed_dates={processed}")


if __name__ == "__main__":
    main()
