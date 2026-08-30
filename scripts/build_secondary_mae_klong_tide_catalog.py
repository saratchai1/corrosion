#!/usr/bin/env python3
"""Build the 2023-2025 Mae Klong secondary tide catalog from cached pages.

The cache is created by ``cache_thailandtidetables_via_jina.py`` because the
source website blocks GitHub-hosted runners. This builder preserves every
published extremum, validates year-wide temporal continuity, tests the
chart-datum-to-MSL conversion against the official 2026 hourly table, and fills
only previously unmatched satellite-scene tide fields.

Secondary extrema and cosine-interpolated scene levels remain explicitly
labelled as screening estimates. They are never relabelled as observations or
as official hourly predictions.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup

from scripts import scrape_thailandtidetables_mae_klong as secondary

DEFAULT_YEARS = (2023, 2024, 2025)
DEFAULT_VALIDATION_YEAR = 2026
DEFAULT_CACHE = Path(".cache/thailandtidetables/pak_nam_mae_klong")
DEFAULT_OUTPUT = Path(
    "data/tide/samut_songkhram/"
    "pak_nam_mae_klong_2023_2025_secondary_extrema.csv"
)
DEFAULT_MANIFEST = Path(
    "data/tide/samut_songkhram/"
    "pak_nam_mae_klong_2023_2025_secondary_extrema_manifest.json"
)
DEFAULT_VALIDATION = Path(
    "data/tide/samut_songkhram/"
    "pak_nam_mae_klong_secondary_extrema_2026_validation.json"
)
DEFAULT_OFFICIAL_2026 = Path(
    "data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv"
)
DEFAULT_SCENES = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
)
MAX_CROSS_MONTH_EVENT_GAP_HOURS = 72.0
MAX_YEAR_EDGE_GAP_HOURS = 72.0


def parse_cached_month(
    cache_dir: Path, *, year: int, month: int
) -> tuple[list[secondary.ParsedEvent], dict[str, Any]]:
    html_path = cache_dir / f"{year}-{month:02d}.html"
    meta_path = cache_dir / f"{year}-{month:02d}.json"
    if not html_path.exists() or not meta_path.exists():
        raise FileNotFoundError(
            f"validated cache missing for {year}-{month:02d}: "
            f"{html_path}, {meta_path}"
        )
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    values: dict[tuple[int, int, int], secondary.ParsedEvent] = {}
    for table in soup.find_all("table"):
        for event in secondary.parse_event_table(table):
            key = (event.day, event.hour, event.minute)
            existing = values.get(key)
            if existing is not None and not math.isclose(
                existing.height, event.height, rel_tol=0.0, abs_tol=0.001
            ):
                raise ValueError(
                    f"conflicting cached event {year}-{month:02d} {key}: "
                    f"{existing.height} vs {event.height}"
                )
            values[key] = event
    events = sorted(values.values(), key=lambda item: (item.day, item.hour, item.minute))
    if len(events) != int(metadata["event_count"]):
        raise ValueError(
            f"cache event-count mismatch for {year}-{month:02d}: "
            f"parsed={len(events)}, metadata={metadata['event_count']}"
        )
    if len({event.day for event in events}) != int(metadata["day_count"]):
        raise ValueError(f"cache day-count mismatch for {year}-{month:02d}")
    return events, metadata


def event_datetime(year: int, month: int, event: secondary.ParsedEvent) -> datetime:
    return datetime(
        year,
        month,
        event.day,
        event.hour,
        event.minute,
        tzinfo=secondary.BANGKOK,
    )


def validate_year_continuity(
    year: int,
    raw_events: list[tuple[int, secondary.ParsedEvent, dict[str, Any]]],
) -> dict[str, Any]:
    ordered = sorted(
        raw_events,
        key=lambda item: event_datetime(year, item[0], item[1]),
    )
    if not ordered:
        raise ValueError(f"no cached extrema for {year}")
    datetimes = [event_datetime(year, month, event) for month, event, _meta in ordered]
    gaps = [
        (after - before).total_seconds() / 3600
        for before, after in zip(datetimes, datetimes[1:])
    ]
    max_gap = max(gaps, default=0.0)
    if max_gap > MAX_CROSS_MONTH_EVENT_GAP_HOURS:
        index = gaps.index(max_gap)
        raise ValueError(
            f"year {year} contains an event gap of {max_gap:.2f} h: "
            f"{datetimes[index].isoformat()} to {datetimes[index+1].isoformat()}"
        )

    year_start = datetime(year, 1, 1, tzinfo=secondary.BANGKOK)
    year_end = datetime(year + 1, 1, 1, tzinfo=secondary.BANGKOK)
    start_gap = (datetimes[0] - year_start).total_seconds() / 3600
    end_gap = (year_end - datetimes[-1]).total_seconds() / 3600
    if start_gap > MAX_YEAR_EDGE_GAP_HOURS:
        raise ValueError(f"year {year} begins with a {start_gap:.2f} h gap")
    if end_gap > MAX_YEAR_EDGE_GAP_HOURS:
        raise ValueError(f"year {year} ends with a {end_gap:.2f} h gap")

    return {
        "year": year,
        "event_count": len(ordered),
        "first_event_bangkok": datetimes[0].isoformat(),
        "last_event_bangkok": datetimes[-1].isoformat(),
        "start_edge_gap_hours": round(start_gap, 5),
        "end_edge_gap_hours": round(end_gap, 5),
        "maximum_consecutive_event_gap_hours": round(max_gap, 5),
        "median_consecutive_event_gap_hours": round(statistics.median(gaps), 5),
    }


def build_year_events(
    cache_dir: Path,
    *,
    year: int,
    conversion_status: str,
) -> tuple[list[secondary.TideEvent], list[dict[str, Any]], dict[str, Any]]:
    raw: list[tuple[int, secondary.ParsedEvent, dict[str, Any]]] = []
    pages: list[dict[str, Any]] = []
    for month in range(1, 13):
        events, metadata = parse_cached_month(cache_dir, year=year, month=month)
        raw.extend((month, event, metadata) for event in events)
        pages.append(
            {
                "year": year,
                "month": month,
                "source_url": metadata["resolved_url"],
                "retrieval_url": metadata.get("retrieval_url"),
                "retrieval_method": metadata.get("retrieval_method"),
                "page_sha256": metadata["sha256"],
                "fetched_at_utc": metadata["fetched_at_utc"],
                "event_count": metadata["event_count"],
                "day_count": metadata["day_count"],
                "coverage_qa": metadata["coverage_qa"],
                "minimum_chart_datum_m": metadata[
                    "minimum_height_m_chart_datum"
                ],
                "maximum_chart_datum_m": metadata[
                    "maximum_height_m_chart_datum"
                ],
            }
        )

    continuity = validate_year_continuity(year, raw)
    raw.sort(key=lambda item: event_datetime(year, item[0], item[1]))
    inferred_types = secondary.infer_event_types([item[1] for item in raw])
    sequence_by_day: defaultdict[tuple[int, int], int] = defaultdict(int)
    result: list[secondary.TideEvent] = []
    for (month, event, metadata), event_type in zip(raw, inferred_types):
        sequence_by_day[(month, event.day)] += 1
        local_dt = event_datetime(year, month, event)
        result.append(
            secondary.TideEvent(
                station_id=secondary.STATION_ID,
                station_name=secondary.STATION_NAME,
                station_name_th=secondary.STATION_NAME_TH,
                latitude=secondary.SITE_LATITUDE,
                longitude=secondary.SITE_LONGITUDE,
                datetime_bangkok=local_dt.isoformat(),
                datetime_utc=local_dt.astimezone(timezone.utc).isoformat(),
                year=year,
                month=month,
                day=event.day,
                time_bangkok=f"{event.hour:02d}:{event.minute:02d}",
                event_sequence_in_day=sequence_by_day[(month, event.day)],
                event_type_inferred=event_type,
                height_m_chart_datum=round(event.height, 3),
                height_m_msl_candidate=round(
                    event.height - secondary.LLW_BELOW_MSL_M, 3
                ),
                chart_datum_to_msl_offset_m=secondary.LLW_BELOW_MSL_M,
                msl_conversion_status=conversion_status,
                source_tier="secondary_published_extrema",
                source_url=str(metadata["resolved_url"]),
                source_attribution=(
                    "Thailand Tide Tables; page states source: World Tides and "
                    "Hydrographic Department, Royal Thai Navy"
                ),
                page_sha256=str(metadata["sha256"]),
                fetched_at_utc=str(metadata["fetched_at_utc"]),
                qa_status=(
                    "validated_month_coverage_and_year_event_continuity; "
                    "calendar_days_without_extrema_retained_as_no_event"
                ),
            )
        )
    return result, pages, continuity


def collect_years(
    cache_dir: Path,
    *,
    years: Iterable[int],
    conversion_status: str,
) -> tuple[list[secondary.TideEvent], list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[secondary.TideEvent] = []
    pages: list[dict[str, Any]] = []
    continuity: list[dict[str, Any]] = []
    for year in sorted(set(years)):
        year_events, year_pages, year_continuity = build_year_events(
            cache_dir,
            year=year,
            conversion_status=conversion_status,
        )
        events.extend(year_events)
        pages.extend(year_pages)
        continuity.append(year_continuity)
    events.sort(key=lambda item: item.datetime_bangkok)
    return events, pages, continuity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--validation-year", type=int, default=DEFAULT_VALIDATION_YEAR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--validation-output", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--official-2026", type=Path, default=DEFAULT_OFFICIAL_2026)
    parser.add_argument("--scene-catalog", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--scene-output", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--skip-scene-completion", action="store_true")
    parser.add_argument("--require-validation", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    years = sorted(set(args.years))
    if any(year >= args.validation_year for year in years):
        raise SystemExit("secondary years must precede validation year")

    validation_events, validation_pages, validation_continuity = collect_years(
        args.cache_dir,
        years=[args.validation_year],
        conversion_status="PENDING_2026_VALIDATION",
    )
    validation = secondary.validate_2026(validation_events, args.official_2026)
    validation["cache_continuity"] = validation_continuity
    validation["page_count"] = len(validation_pages)
    args.validation_output.parent.mkdir(parents=True, exist_ok=True)
    args.validation_output.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    validation_status = validation["acceptance"]["status"]
    if args.require_validation and validation_status != "PASSED":
        raise SystemExit(
            "secondary datum validation failed: "
            + json.dumps(validation["metrics_m"], ensure_ascii=False)
        )

    events, pages, continuity = collect_years(
        args.cache_dir,
        years=years,
        conversion_status=f"VALIDATED_AGAINST_OFFICIAL_2026_{validation_status}",
    )
    secondary.write_events(args.output, events)

    scene_result = None
    if not args.skip_scene_completion:
        scene_result = secondary.complete_scene_catalog(
            args.scene_catalog,
            output=args.scene_output,
            secondary_events=events,
            validation=validation,
        )

    by_year = Counter(event.year for event in events)
    by_month = Counter(f"{event.year}-{event.month:02d}" for event in events)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "station": {
            "station_id": secondary.STATION_ID,
            "station_name": secondary.STATION_NAME,
            "station_name_th": secondary.STATION_NAME_TH,
            "site_coordinates": {
                "latitude": secondary.SITE_LATITUDE,
                "longitude": secondary.SITE_LONGITUDE,
            },
        },
        "source": {
            "tier": "secondary_published_extrema",
            "domain": "www.thailandtidetables.com",
            "url_template": secondary.URL_TEMPLATE,
            "page_attribution": (
                "Thailand Tide Tables; pages state source: World Tides and "
                "Hydrographic Department, Royal Thai Navy"
            ),
            "retrieval_transport": "Jina Reader because source returns HTTP 403 to GitHub runners",
            "raw_reader_markdown_committed": False,
        },
        "years": years,
        "month_count": len(pages),
        "event_count": len(events),
        "event_count_by_year": dict(sorted(by_year.items())),
        "event_count_by_month": dict(sorted(by_month.items())),
        "year_continuity_qa": continuity,
        "datum": {
            "published_height_reference": "chart datum stated by source page",
            "candidate_output_reference": "MSL",
            "conversion": "height_m_msl_candidate = height_m_chart_datum - 2.14",
            "llw_below_msl_m": secondary.LLW_BELOW_MSL_M,
            "offset_basis": (
                "Hydrographic Department Pak Nam Mae Klong table: Lowest Low "
                "Water is 2.14 m below Mean Sea Level"
            ),
            "validation_file": str(args.validation_output),
            "validation_status": validation_status,
            "validation_metrics_m": validation["metrics_m"],
        },
        "pages": pages,
        "validation_pages_2026": validation_pages,
        "scene_completion": scene_result,
        "scientific_limit": (
            "The secondary source supplies extrema, not hourly observations. "
            "Interpolated scene levels are screening estimates and remain "
            "distinguishable from official hourly predictions and local gauges."
        ),
        "output_csv": str(args.output),
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
