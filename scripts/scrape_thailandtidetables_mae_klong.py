#!/usr/bin/env python3
"""Collect Pak Nam Mae Klong tide extrema from ThailandTideTables.com.

This is a secondary-source recovery workflow for annual official PDFs that are
no longer available at their former Hydrographic Department URLs. It downloads
all monthly pages for 2023-2025, preserves the published extrema, converts the
published chart-datum heights to a candidate MSL series using the documented
Pak Nam Mae Klong LLW-to-MSL offset (2.14 m), validates that conversion against
the versioned official 2026 hourly table, and optionally fills previously
unmatched Sentinel-2 scene times by cosine interpolation between consecutive
reported extrema.

The output never labels these values as observed water levels or as official
hourly predictions. The source tier remains explicit in every derived row.
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BANGKOK = ZoneInfo("Asia/Bangkok")
STATION_ID = "474"
STATION_NAME = "Pak Nam Mae Klong"
STATION_NAME_TH = "ปากน้ำแม่กลอง"
SITE_LATITUDE = 13.3767
SITE_LONGITUDE = 99.9956
LLW_BELOW_MSL_M = 2.14
URL_TEMPLATE = (
    "https://www.thailandtidetables.com/"
    "tide-tables-pak-nam-mae-klong-samut-songkhram-year-{year}-{month:02d}-474.php"
)
DEFAULT_YEARS = (2023, 2024, 2025)
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
DAY_RE = re.compile(r"^(?:0?[1-9]|[12]\d|3[01])$")
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
FLOAT_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:\s*m)?$", re.IGNORECASE)
MATCHED_PREFIXES = ("predicted_", "observed_", "modelled_", "matched_")


@dataclass(frozen=True)
class TideEvent:
    station_id: str
    station_name: str
    station_name_th: str
    latitude: float
    longitude: float
    datetime_bangkok: str
    datetime_utc: str
    year: int
    month: int
    day: int
    time_bangkok: str
    event_sequence_in_day: int
    event_type_inferred: str
    height_m_chart_datum: float
    height_m_msl_candidate: float
    chart_datum_to_msl_offset_m: float
    msl_conversion_status: str
    source_tier: str
    source_url: str
    source_attribution: str
    page_sha256: str
    fetched_at_utc: str
    qa_status: str


@dataclass(frozen=True)
class ParsedEvent:
    day: int
    hour: int
    minute: int
    height: float


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def build_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; corrosion-research/1.0; "
                "+https://github.com/saratchai1/corrosion)"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
        }
    )
    return session


def page_url(year: int, month: int) -> str:
    return URL_TEMPLATE.format(year=year, month=month)


def fetch_html(
    session: requests.Session,
    *,
    year: int,
    month: int,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: float,
) -> tuple[str, str, str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    html_path = cache_dir / f"{year}-{month:02d}.html"
    meta_path = cache_dir / f"{year}-{month:02d}.json"
    url = page_url(year, month)

    if not refresh and html_path.exists() and meta_path.exists():
        html = html_path.read_text(encoding="utf-8")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return html, str(meta["resolved_url"]), str(meta["fetched_at_utc"]), str(
            meta["sha256"]
        )

    response = session.get(url, timeout=timeout_seconds, allow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and not response.text.lstrip().startswith("<"):
        raise RuntimeError(
            f"unexpected content type for {year}-{month:02d}: {content_type!r}"
        )
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    html = response.text
    if "Pak Nam Mae Klong" not in html:
        raise RuntimeError(f"station name missing from {response.url}")
    digest = hashlib.sha256(response.content).hexdigest()
    fetched_at = datetime.now(timezone.utc).isoformat()
    html_path.write_text(html, encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "requested_url": url,
                "resolved_url": response.url,
                "status_code": response.status_code,
                "content_type": content_type,
                "bytes": len(response.content),
                "sha256": digest,
                "fetched_at_utc": fetched_at,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return html, response.url, fetched_at, digest


def parse_day(text: str) -> int | None:
    text = normalize_text(text)
    if DAY_RE.fullmatch(text):
        value = int(text)
        if 1 <= value <= 31:
            return value
    return None


def parse_time_from_cells(cells: list[str]) -> tuple[int, int] | None:
    for text in cells:
        match = TIME_RE.search(text)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def parse_height_from_cells(cells: list[str]) -> float | None:
    for text in reversed(cells):
        normalized = normalize_text(text)
        if FLOAT_RE.fullmatch(normalized):
            return float(normalized.lower().removesuffix("m").strip())
    return None


def parse_event_table(table: Any) -> list[ParsedEvent]:
    current_day: int | None = None
    rows: list[ParsedEvent] = []
    for tr in table.find_all("tr"):
        cells = [normalize_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
        if not cells:
            continue
        possible_day = parse_day(cells[0])
        if possible_day is not None:
            current_day = possible_day
        parsed_time = parse_time_from_cells(cells)
        height = parse_height_from_cells(cells)
        if current_day is None or parsed_time is None or height is None:
            continue
        hour, minute = parsed_time
        rows.append(
            ParsedEvent(
                day=current_day,
                hour=hour,
                minute=minute,
                height=height,
            )
        )
    return rows


def infer_event_types(events: list[ParsedEvent]) -> list[str]:
    if not events:
        return []
    values = [event.height for event in events]
    result: list[str] = []
    for index, value in enumerate(values):
        previous = values[index - 1] if index else None
        following = values[index + 1] if index + 1 < len(values) else None
        if previous is None and following is not None:
            result.append("LOW" if value < following else "HIGH")
        elif following is None and previous is not None:
            result.append("LOW" if value < previous else "HIGH")
        elif previous is not None and following is not None:
            if value <= previous and value <= following:
                result.append("LOW")
            elif value >= previous and value >= following:
                result.append("HIGH")
            else:
                result.append("EXTREMUM_UNCLASSIFIED")
        else:
            result.append("EXTREMUM_UNCLASSIFIED")
    return result


def parse_month(
    html: str,
    *,
    year: int,
    month: int,
    source_url: str,
    fetched_at_utc: str,
    page_sha256: str,
    conversion_status: str,
) -> list[TideEvent]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = normalize_text(soup.get_text(" ", strip=True))
    expected_heading = f"{calendar.month_name[month]} {year}"
    if expected_heading not in page_text:
        raise ValueError(f"expected heading {expected_heading!r} not found in {source_url}")
    if "Pak Nam Mae Klong" not in page_text:
        raise ValueError(f"station identity not found in {source_url}")

    table_events: list[tuple[int, list[ParsedEvent]]] = []
    for table in soup.find_all("table"):
        rows = parse_event_table(table)
        day_count = len({row.day for row in rows})
        if rows:
            table_events.append((day_count, rows))

    selected = [rows for day_count, rows in table_events if day_count >= 10]
    if not selected and table_events:
        maximum = max(day_count for day_count, _rows in table_events)
        selected = [rows for day_count, rows in table_events if day_count == maximum]
    flattened = [event for rows in selected for event in rows]

    by_timestamp: dict[tuple[int, int, int], ParsedEvent] = {}
    for event in flattened:
        key = (event.day, event.hour, event.minute)
        existing = by_timestamp.get(key)
        if existing is not None and not math.isclose(
            existing.height, event.height, rel_tol=0.0, abs_tol=0.001
        ):
            raise ValueError(
                f"conflicting duplicate {year}-{month:02d}-{event.day:02d} "
                f"{event.hour:02d}:{event.minute:02d}: "
                f"{existing.height} vs {event.height}"
            )
        by_timestamp[key] = event

    parsed = sorted(by_timestamp.values(), key=lambda item: (item.day, item.hour, item.minute))
    expected_days = set(range(1, calendar.monthrange(year, month)[1] + 1))
    actual_days = {event.day for event in parsed}
    if actual_days != expected_days:
        missing = sorted(expected_days.difference(actual_days))
        extra = sorted(actual_days.difference(expected_days))
        raise ValueError(
            f"incomplete month {year}-{month:02d}; missing days={missing}, extra={extra}"
        )
    if len(parsed) < len(expected_days) * 2:
        raise ValueError(
            f"too few extrema for {year}-{month:02d}: {len(parsed)} records"
        )

    inferred_types = infer_event_types(parsed)
    sequence_by_day: defaultdict[int, int] = defaultdict(int)
    output: list[TideEvent] = []
    for event, event_type in zip(parsed, inferred_types):
        sequence_by_day[event.day] += 1
        local_dt = datetime(
            year,
            month,
            event.day,
            event.hour,
            event.minute,
            tzinfo=BANGKOK,
        )
        msl = event.height - LLW_BELOW_MSL_M
        output.append(
            TideEvent(
                station_id=STATION_ID,
                station_name=STATION_NAME,
                station_name_th=STATION_NAME_TH,
                latitude=SITE_LATITUDE,
                longitude=SITE_LONGITUDE,
                datetime_bangkok=local_dt.isoformat(),
                datetime_utc=local_dt.astimezone(timezone.utc).isoformat(),
                year=year,
                month=month,
                day=event.day,
                time_bangkok=f"{event.hour:02d}:{event.minute:02d}",
                event_sequence_in_day=sequence_by_day[event.day],
                event_type_inferred=event_type,
                height_m_chart_datum=round(event.height, 3),
                height_m_msl_candidate=round(msl, 3),
                chart_datum_to_msl_offset_m=LLW_BELOW_MSL_M,
                msl_conversion_status=conversion_status,
                source_tier="secondary_published_extrema",
                source_url=source_url,
                source_attribution=(
                    "Thailand Tide Tables; page states source: World Tides and "
                    "Hydrographic Department, Royal Thai Navy"
                ),
                page_sha256=page_sha256,
                fetched_at_utc=fetched_at_utc,
                qa_status="month_complete_all_calendar_days",
            )
        )
    return output


def collect_years(
    years: Iterable[int],
    *,
    session: requests.Session,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: float,
    sleep_seconds: float,
    conversion_status: str,
) -> tuple[list[TideEvent], list[dict[str, Any]]]:
    events: list[TideEvent] = []
    pages: list[dict[str, Any]] = []
    for year in sorted(set(years)):
        for month in range(1, 13):
            print(f"Fetching {year}-{month:02d}...", file=sys.stderr)
            html, resolved_url, fetched_at, digest = fetch_html(
                session,
                year=year,
                month=month,
                cache_dir=cache_dir,
                refresh=refresh,
                timeout_seconds=timeout_seconds,
            )
            month_events = parse_month(
                html,
                year=year,
                month=month,
                source_url=resolved_url,
                fetched_at_utc=fetched_at,
                page_sha256=digest,
                conversion_status=conversion_status,
            )
            events.extend(month_events)
            pages.append(
                {
                    "year": year,
                    "month": month,
                    "source_url": resolved_url,
                    "page_sha256": digest,
                    "fetched_at_utc": fetched_at,
                    "event_count": len(month_events),
                    "day_count": len({event.day for event in month_events}),
                    "minimum_chart_datum_m": min(
                        event.height_m_chart_datum for event in month_events
                    ),
                    "maximum_chart_datum_m": max(
                        event.height_m_chart_datum for event in month_events
                    ),
                }
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    events.sort(key=lambda item: item.datetime_bangkok)
    return events, pages


def read_official_hourly(path: Path) -> tuple[list[datetime], list[float]]:
    timestamps: list[datetime] = []
    levels: list[float] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dt = datetime.fromisoformat(row["datetime_bangkok"])
            timestamps.append(dt)
            levels.append(float(row["tide_m_msl"]))
    if not timestamps:
        raise ValueError(f"official hourly tide CSV is empty: {path}")
    return timestamps, levels


def linear_hourly_level(
    target: datetime, timestamps: list[datetime], levels: list[float]
) -> float:
    position = bisect.bisect_left(timestamps, target)
    if position == 0 or position >= len(timestamps):
        raise ValueError(f"target outside official tide range: {target.isoformat()}")
    before_dt, after_dt = timestamps[position - 1], timestamps[position]
    before_level, after_level = levels[position - 1], levels[position]
    fraction = (target - before_dt).total_seconds() / (
        after_dt - before_dt
    ).total_seconds()
    return before_level + fraction * (after_level - before_level)


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def validate_2026(
    events: list[TideEvent], official_path: Path
) -> dict[str, Any]:
    timestamps, levels = read_official_hourly(official_path)
    differences: list[float] = []
    samples: list[dict[str, Any]] = []
    for event in events:
        target = datetime.fromisoformat(event.datetime_bangkok)
        official = linear_hourly_level(target, timestamps, levels)
        difference = event.height_m_msl_candidate - official
        differences.append(difference)
        if len(samples) < 24:
            samples.append(
                {
                    "datetime_bangkok": event.datetime_bangkok,
                    "secondary_msl_candidate_m": event.height_m_msl_candidate,
                    "official_hourly_linear_msl_m": round(official, 4),
                    "difference_m": round(difference, 4),
                    "source_url": event.source_url,
                }
            )
    absolute = [abs(value) for value in differences]
    mae = statistics.fmean(absolute)
    rmse = math.sqrt(statistics.fmean(value * value for value in differences))
    bias = statistics.fmean(differences)
    p95 = percentile(absolute, 0.95)
    status = "PASSED" if mae <= 0.20 and p95 <= 0.35 else "FAILED"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation_year": 2026,
        "secondary_event_count": len(events),
        "official_hourly_source": str(official_path),
        "chart_datum_to_msl_offset_m": LLW_BELOW_MSL_M,
        "method": (
            "subtract 2.14 m from secondary chart-datum extrema and compare "
            "with linear interpolation of the official 2026 hourly MSL table"
        ),
        "metrics_m": {
            "mean_absolute_error": round(mae, 5),
            "root_mean_square_error": round(rmse, 5),
            "mean_bias": round(bias, 5),
            "p95_absolute_error": round(p95, 5),
            "maximum_absolute_error": round(max(absolute), 5),
        },
        "acceptance": {
            "mae_max_m": 0.20,
            "p95_absolute_error_max_m": 0.35,
            "status": status,
        },
        "scientific_limit": (
            "Agreement with rounded hourly predictions supports datum consistency "
            "for screening; it does not turn the secondary extrema into observed "
            "local water levels or official hourly predictions."
        ),
        "samples": samples,
    }


def write_events(path: Path, events: list[TideEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(events[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            writer.writerow(asdict(event))


def is_tide_matched(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized.startswith(MATCHED_PREFIXES)


def cosine_between_extrema(
    target: datetime, before: TideEvent, after: TideEvent
) -> float:
    before_dt = datetime.fromisoformat(before.datetime_bangkok)
    after_dt = datetime.fromisoformat(after.datetime_bangkok)
    if not before_dt <= target <= after_dt:
        raise ValueError("target is not bracketed by extrema")
    duration = (after_dt - before_dt).total_seconds()
    if duration <= 0:
        raise ValueError("non-positive extrema interval")
    fraction = (target - before_dt).total_seconds() / duration
    smooth_fraction = (1 - math.cos(math.pi * fraction)) / 2
    return before.height_m_msl_candidate + (
        after.height_m_msl_candidate - before.height_m_msl_candidate
    ) * smooth_fraction


def complete_scene_catalog(
    path: Path,
    *,
    output: Path,
    secondary_events: list[TideEvent],
    validation: dict[str, Any],
) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"scene catalog has no header: {path}")
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    extra_fields = [
        "tide_source_tier",
        "tide_source_validation",
        "tide_bracket_before_bangkok",
        "tide_bracket_after_bangkok",
        "tide_bracket_span_minutes",
        "tide_uncertainty_note",
    ]
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    event_times = [datetime.fromisoformat(event.datetime_bangkok) for event in secondary_events]
    validation_status = validation["acceptance"]["status"]
    validation_mae = validation["metrics_m"]["mean_absolute_error"]
    completed = 0
    preserved = 0
    for row in rows:
        status = (row.get("tide_status") or "").strip()
        if is_tide_matched(status):
            preserved += 1
            row["tide_source_tier"] = (
                "official_hourly_prediction"
                if status.startswith("predicted_")
                else row.get("tide_source_tier", "") or "existing_matched_source"
            )
            row["tide_source_validation"] = "official_source_preserved"
            continue

        local_text = row.get("acquisition_datetime_bangkok", "")
        if not local_text:
            continue
        target = datetime.fromisoformat(local_text.replace("Z", "+00:00"))
        position = bisect.bisect_left(event_times, target)
        if position == 0 or position >= len(secondary_events):
            continue
        before = secondary_events[position - 1]
        after = secondary_events[position]
        if before.year != target.year or after.year != target.year:
            continue
        level = cosine_between_extrema(target, before, after)
        before_dt = datetime.fromisoformat(before.datetime_bangkok)
        after_dt = datetime.fromisoformat(after.datetime_bangkok)
        span_minutes = (after_dt - before_dt).total_seconds() / 60

        row["tide_station"] = STATION_NAME
        row["tide_level"] = f"{level:.4f}"
        row["tide_datum"] = "MSL"
        row["tide_status"] = "modelled_secondary_extrema_cosine"
        row["tide_source_url"] = (
            before.source_url
            if before.source_url == after.source_url
            else f"{before.source_url} | {after.source_url}"
        )
        row["tide_match_method"] = "cosine_between_reported_extrema"
        row["tide_match_gap_minutes"] = f"{min((target-before_dt).total_seconds(), (after_dt-target).total_seconds())/60:.2f}"
        row["tide_prediction_qa"] = (
            "secondary_extrema; chart_datum_minus_2.14m; "
            f"2026_validation={validation_status}; mae_m={validation_mae}"
        )
        row["tide_source_tier"] = "secondary_published_extrema"
        row["tide_source_validation"] = (
            f"2026_official_hourly_comparison_{validation_status.lower()}"
        )
        row["tide_bracket_before_bangkok"] = before.datetime_bangkok
        row["tide_bracket_after_bangkok"] = after.datetime_bangkok
        row["tide_bracket_span_minutes"] = f"{span_minutes:.2f}"
        row["tide_uncertainty_note"] = (
            "Screening estimate only; cosine interpolation between secondary "
            "published extrema, not an observed level and not an official hourly value."
        )
        completed += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "scene_count": len(rows),
        "existing_matched_preserved": preserved,
        "secondary_completed": completed,
        "remaining_unmatched": sum(
            not is_tide_matched((row.get("tide_status") or "")) for row in rows
        ),
        "status_counts": dict(
            sorted(Counter(row.get("tide_status", "missing") for row in rows).items())
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--validation-year", type=int, default=2026)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--validation-output", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--official-2026", type=Path, default=DEFAULT_OFFICIAL_2026)
    parser.add_argument("--scene-catalog", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--scene-output", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--skip-scene-completion", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--require-validation", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    years = sorted(set(args.years))
    if any(year >= args.validation_year for year in years):
        raise SystemExit("secondary years must precede validation year")
    session = build_session()

    validation_events, validation_pages = collect_years(
        [args.validation_year],
        session=session,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        timeout_seconds=args.timeout_seconds,
        sleep_seconds=args.sleep_seconds,
        conversion_status="PENDING_2026_VALIDATION",
    )
    validation = validate_2026(validation_events, args.official_2026)
    args.validation_output.parent.mkdir(parents=True, exist_ok=True)
    args.validation_output.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    validation_status = validation["acceptance"]["status"]
    if args.require_validation and validation_status != "PASSED":
        raise SystemExit(
            "secondary datum validation failed: "
            + json.dumps(validation["metrics_m"], ensure_ascii=False)
        )

    secondary_events, secondary_pages = collect_years(
        years,
        session=session,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        timeout_seconds=args.timeout_seconds,
        sleep_seconds=args.sleep_seconds,
        conversion_status=f"VALIDATED_AGAINST_OFFICIAL_2026_{validation_status}",
    )
    write_events(args.output, secondary_events)

    scene_result = None
    if not args.skip_scene_completion:
        scene_result = complete_scene_catalog(
            args.scene_catalog,
            output=args.scene_output,
            secondary_events=secondary_events,
            validation=validation,
        )

    by_year = Counter(event.year for event in secondary_events)
    by_month = Counter(f"{event.year}-{event.month:02d}" for event in secondary_events)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "station": {
            "station_id": STATION_ID,
            "station_name": STATION_NAME,
            "station_name_th": STATION_NAME_TH,
            "site_coordinates": {
                "latitude": SITE_LATITUDE,
                "longitude": SITE_LONGITUDE,
            },
        },
        "source": {
            "tier": "secondary_published_extrema",
            "domain": "www.thailandtidetables.com",
            "url_template": URL_TEMPLATE,
            "page_attribution": (
                "Thailand Tide Tables; pages state source: World Tides and "
                "Hydrographic Department, Royal Thai Navy"
            ),
            "raw_html_committed": False,
        },
        "years": years,
        "month_count": len(secondary_pages),
        "event_count": len(secondary_events),
        "event_count_by_year": dict(sorted(by_year.items())),
        "event_count_by_month": dict(sorted(by_month.items())),
        "datum": {
            "published_height_reference": "chart datum stated by source page",
            "candidate_output_reference": "MSL",
            "conversion": "height_m_msl_candidate = height_m_chart_datum - 2.14",
            "llw_below_msl_m": LLW_BELOW_MSL_M,
            "offset_basis": (
                "Hydrographic Department 2026 Pak Nam Mae Klong table: Lowest "
                "Low Water is 2.14 m below Mean Sea Level"
            ),
            "validation_file": str(args.validation_output),
            "validation_status": validation_status,
            "validation_metrics_m": validation["metrics_m"],
        },
        "pages": secondary_pages,
        "validation_pages_2026": validation_pages,
        "scene_completion": scene_result,
        "scientific_limit": (
            "The secondary source supplies extrema, not hourly observations. "
            "Interpolated scene levels are screening estimates and must remain "
            "distinguishable from official hourly predictions and local gauges."
        ),
        "output_csv": str(args.output),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
