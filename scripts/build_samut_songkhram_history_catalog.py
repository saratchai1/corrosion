#!/usr/bin/env python3
"""Build the versioned Sentinel-2 catalog for pre-planting history.

Historical 2017-2022 candidates are reused from the existing versioned MVP
catalog, while the already tide-matched 2023-2026 project rows are preserved
verbatim.  Historical output paths are rewritten into a project-specific
namespace so that GitHub Actions can re-download and clip the exact STAC items
to the verified project analysis AOI.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SOURCE = Path("data/catalog/mvp_optical_scenes.csv")
DEFAULT_CURRENT = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
)
DEFAULT_OUTPUT = Path(
    "data/catalog/project_samut_songkhram_sentinel2_history_2017_2026.csv"
)
DEFAULT_MANIFEST = Path(
    "data/catalog/project_samut_songkhram_sentinel2_history_2017_2026_manifest.json"
)
DEFAULT_HISTORICAL_YEARS = tuple(range(2017, 2023))
DEFAULT_CURRENT_YEARS = tuple(range(2023, 2027))
BAND_RESOLUTION = {
    "B2": "10m",
    "B3": "10m",
    "B4": "10m",
    "B8": "10m",
    "B11": "20m",
    "SCL": "20m",
}
TIDE_EXTRA_FIELDS = [
    "tide_source_url",
    "tide_match_method",
    "tide_match_gap_minutes",
    "tide_prediction_qa",
    "tide_source_tier",
    "tide_source_validation",
    "tide_bracket_before_bangkok",
    "tide_bracket_after_bangkok",
    "tide_bracket_span_minutes",
    "tide_uncertainty_note",
]


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"catalog has no header: {path}")
        return list(reader.fieldnames), list(reader)


def acquisition_year(row: dict[str, str]) -> int:
    return int(row["acquisition_datetime_utc"][:4])


def acquisition_month(row: dict[str, str]) -> int:
    return int(row["acquisition_datetime_utc"][5:7])


def as_float(value: str | None, fallback: float) -> float:
    try:
        return float(value or "")
    except ValueError:
        return fallback


def history_local_paths(year: int, scene_id: str, bands: str) -> str:
    values = []
    for band in [item.strip().upper() for item in bands.split(";") if item.strip()]:
        resolution = BAND_RESOLUTION.get(band)
        if resolution is None:
            raise ValueError(f"unsupported historical band {band!r} for {scene_id}")
        values.append(
            "data/satellite/project_samut_songkhram/history/sentinel2/"
            f"{year}/{scene_id}/{band}_{resolution}.tif"
        )
    return ";".join(values)


def select_historical_rows(
    rows: list[dict[str, str]],
    *,
    years: tuple[int, ...],
    candidates_per_year: int,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for year in years:
        candidates = [
            row
            for row in rows
            if row.get("dataset") == "sentinel2"
            and acquisition_year(row) == year
            and acquisition_month(row) in {1, 2, 3, 4}
            and row.get("source_url")
            and row.get("bands")
        ]
        candidates.sort(
            key=lambda row: (
                as_float(row.get("cloud_cover_aoi"), 999.0),
                as_float(row.get("cloud_cover_scene"), 999.0),
                row["acquisition_datetime_utc"],
                row["scene_id"],
            )
        )
        chosen = candidates[:candidates_per_year]
        if len(chosen) < 2:
            raise ValueError(
                f"historical year {year} has only {len(chosen)} suitable Sentinel-2 rows"
            )
        for source in chosen:
            row = dict(source)
            row["local_path"] = history_local_paths(year, row["scene_id"], row["bands"])
            row["file_size_bytes"] = ""
            row["sha256"] = ""
            row["tide_station"] = ""
            row["tide_level"] = ""
            row["tide_datum"] = ""
            row["tide_status"] = "unverified"
            row["qa_status"] = "historical-project-candidate"
            row["selection_reason"] = (
                (row.get("selection_reason") or "")
                + "; reused for project pre-planting history; exact STAC item; "
                + f"historical candidate rank={len([item for item in selected if acquisition_year(item) == year]) + 1}"
            ).strip("; ")
            for field in TIDE_EXTRA_FIELDS:
                row[field] = ""
            selected.append(row)
    return selected


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--historical-years", nargs="+", type=int, default=list(DEFAULT_HISTORICAL_YEARS))
    parser.add_argument("--current-years", nargs="+", type=int, default=list(DEFAULT_CURRENT_YEARS))
    parser.add_argument("--candidates-per-year", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source_fields, source_rows = load_csv(args.source)
    current_fields, current_rows = load_csv(args.current)
    historical_years = tuple(sorted(set(args.historical_years)))
    current_years = tuple(sorted(set(args.current_years)))

    historical = select_historical_rows(
        source_rows,
        years=historical_years,
        candidates_per_year=args.candidates_per_year,
    )
    current = [
        dict(row)
        for row in current_rows
        if row.get("dataset") == "sentinel2" and acquisition_year(row) in current_years
    ]
    if not current:
        raise ValueError("current project catalog supplied no 2023-2026 Sentinel-2 rows")

    fields: list[str] = []
    for field in current_fields + source_fields + TIDE_EXTRA_FIELDS:
        if field not in fields:
            fields.append(field)
    rows = sorted(
        historical + current,
        key=lambda row: (row["acquisition_datetime_utc"], row["scene_id"]),
    )
    for row in rows:
        for field in fields:
            row.setdefault(field, "")

    by_year = Counter(acquisition_year(row) for row in rows)
    expected_years = set(historical_years).union(current_years)
    if set(by_year) != expected_years:
        raise ValueError(f"catalog year mismatch: {dict(by_year)}")
    if len({row["scene_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate scene_id in historical project catalog")

    write_csv(args.output, fields, rows)
    manifest: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(args.output),
        "source_historical_catalog": str(args.source),
        "source_current_catalog": str(args.current),
        "historical_years": list(historical_years),
        "current_years": list(current_years),
        "candidate_count_per_year": dict(sorted(by_year.items())),
        "scene_count": len(rows),
        "historical_scene_count": len(historical),
        "current_scene_count": len(current),
        "selection_rule": (
            "For 2017-2022, choose up to three January-April Sentinel-2 rows "
            "from the existing versioned MVP catalog, ranked by AOI cloud and "
            "scene cloud. Preserve the existing 2023-2026 project catalog rows."
        ),
        "scientific_limit": (
            "This file only versions candidate imagery. Historical WATERLINE use "
            "still requires validated tide metadata and per-year acceptance."
        ),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
