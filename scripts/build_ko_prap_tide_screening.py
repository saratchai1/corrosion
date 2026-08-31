#!/usr/bin/env python3
"""Build and match Ko Prap tide-extrema data for the Surat Thani MVP.

This script uses the month/year URL pattern supplied for ThailandTideTables
station 466. The source exposes predicted tide extrema (high/low turning
points), not an hourly MSL series. Heights are therefore retained in the
source's own chart/reference datum and are NOT relabelled as MSL.

For each Sentinel-2 scene in the Surat Thani MVP catalog, the script fetches
only the required year/month pages plus adjacent months needed to bracket
month-boundary acquisitions, parses the full-month tide table, and records the
scene's position between the preceding and following tide extrema.

The linear height between extrema is an approximation for screening only. The
primary matching outputs are tide stage (RISING/FALLING) and phase position.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import html
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

BANGKOK = ZoneInfo("Asia/Bangkok")
STATION_NAME = "Ko Prap"
STATION_NAME_TH = "เกาะปราบ"
STATION_ID = "466"
SOURCE_NAME = "ThailandTideTables (source credit: Hydrographic Department, Royal Thai Navy)"
SOURCE_DATUM = "CHART_REFERENCE_DATUM_SOURCE_SITE"
SOURCE_TYPE = "PREDICTED_TIDE_EXTREMA"
URL_TEMPLATE = (
    "https://www.thailandtidetables.com/ไทย/"
    "ตารางน้ำขึ้นน้ำลง-เกาะปราบ-สุราษฎร์ธานี-ปี-{year}-{month:02d}-466.php"
)
DEFAULT_SCENE_CATALOG = Path("data/catalog/surat_thani_mvp_optical_scenes.csv")
DEFAULT_TIDE_CSV = Path("data/tide/surat_thani/ko_prap_tide_extrema.csv")
DEFAULT_MANIFEST = Path("data/tide/surat_thani/ko_prap_tide_extrema_manifest.json")
DEFAULT_MATCHED = Path("data/catalog/surat_thani_mvp_optical_scenes_tide_screened.csv")

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
DAY_RE = re.compile(r"^0?([1-9]|[12]\d|3[01])$")


class TableCollector(HTMLParser):
    """Collect text cells from every HTML table without third-party parsers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []
        elif self._cell_parts is not None and tag == "br":
            self._cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell_parts is not None:
            text = " ".join("".join(self._cell_parts).split())
            assert self._row is not None
            self._row.append(html.unescape(text))
            self._cell_parts = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            if self._row:
                assert self._rows is not None
                self._rows.append(self._row)
            self._row = None
            self._cell_parts = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._rows is not None:
                self.tables.append(self._rows)
                self._rows = None
                self._row = None
                self._cell_parts = None
            self._table_depth -= 1


@dataclass(frozen=True)
class TideEvent:
    when_local: datetime
    height_m: float
    source_url: str
    source_year: int
    source_month: int

    @property
    def when_utc(self) -> datetime:
        return self.when_local.astimezone(timezone.utc)


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def parse_time(value: str) -> tuple[int, int] | None:
    match = TIME_RE.search(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_height(value: str) -> float | None:
    match = FLOAT_RE.search(value.replace(",", "."))
    if not match:
        return None
    number = float(match.group(0))
    if not math.isfinite(number) or number < -10 or number > 20:
        return None
    return number


def table_events(rows: list[list[str]], year: int, month: int, source_url: str) -> list[TideEvent]:
    """Parse a table that may use rowspan for the day column."""
    max_day = calendar.monthrange(year, month)[1]
    current_day: int | None = None
    events: list[TideEvent] = []

    for raw_cells in rows:
        cells = [clean_text(cell) for cell in raw_cells if clean_text(cell)]
        if len(cells) < 2:
            continue

        day: int | None = None
        time_cell: str | None = None
        height_cell: str | None = None

        if len(cells) >= 3:
            day_match = DAY_RE.fullmatch(cells[0])
            if day_match:
                day = int(day_match.group(1))
                current_day = day
                time_cell = cells[1]
                height_cell = cells[2]
            else:
                # Some layouts put decorative/icon text before the time.
                for idx, cell in enumerate(cells):
                    candidate = DAY_RE.fullmatch(cell)
                    if candidate and idx + 2 < len(cells):
                        day = int(candidate.group(1))
                        current_day = day
                        time_cell = cells[idx + 1]
                        height_cell = cells[idx + 2]
                        break
        elif current_day is not None:
            day = current_day
            time_cell, height_cell = cells[0], cells[1]

        if day is None or time_cell is None or height_cell is None or day > max_day:
            continue
        hm = parse_time(time_cell)
        height_m = parse_height(height_cell)
        if hm is None or height_m is None:
            continue
        hour, minute = hm
        when = datetime(year, month, day, hour, minute, tzinfo=BANGKOK)
        events.append(TideEvent(when, height_m, source_url, year, month))

    # Dedupe exact events while preserving a deterministic order.
    by_key: dict[tuple[datetime, float], TideEvent] = {}
    for event in events:
        by_key[(event.when_local, round(event.height_m, 4))] = event
    return sorted(by_key.values(), key=lambda event: event.when_local)


def parse_full_month(html_text: str, year: int, month: int, source_url: str) -> list[TideEvent]:
    parser = TableCollector()
    parser.feed(html_text)
    candidates: list[tuple[int, int, list[TideEvent]]] = []
    for rows in parser.tables:
        events = table_events(rows, year, month, source_url)
        days = {event.when_local.day for event in events}
        candidates.append((len(days), len(events), events))
    if not candidates:
        raise ValueError("no HTML tables found")
    days, count, events = max(candidates, key=lambda item: (item[0], item[1]))
    expected_days = calendar.monthrange(year, month)[1]
    # A full-month table should cover nearly all days. Some days can have no
    # extrema rendered, so allow a small gap rather than requiring all days.
    if days < max(24, expected_days - 5) or count < 40:
        summary = sorted(((d, c) for d, c, _ in candidates), reverse=True)[:5]
        raise ValueError(f"full-month tide table not confidently identified: candidates={summary}")
    return events


def month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def scene_time(row: dict[str, str]) -> datetime:
    value = (row.get("acquisition_datetime_utc") or "").strip()
    if value:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(BANGKOK)
    value = (row.get("acquisition_datetime_bangkok") or "").strip()
    if not value:
        raise ValueError(f"scene {row.get('scene_id', '<unknown>')} has no acquisition datetime")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BANGKOK)
    return parsed.astimezone(BANGKOK)


def read_scenes(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"scene catalog has no header: {path}")
        return list(reader.fieldnames), list(reader)


def required_months(scenes: list[dict[str, str]], min_year: int) -> list[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    for row in scenes:
        if (row.get("dataset") or "").strip().lower() != "sentinel2":
            continue
        when = scene_time(row)
        if when.year < min_year:
            continue
        for delta in (-1, 0, 1):
            months.add(month_shift(when.year, when.month, delta))
    return sorted(months)


def fetch_month(session: requests.Session, year: int, month: int, timeout: float) -> tuple[str, str]:
    url = URL_TEMPLATE.format(year=year, month=month)
    headers = {
        "User-Agent": "corrosion-research/1.0 (+https://github.com/saratchai1/corrosion)",
        "Accept-Language": "th,en;q=0.8",
    }
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
            return response.text, response.url
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.0 * (2**attempt))
    assert last_error is not None
    raise last_error


def event_type(index: int, events: list[TideEvent]) -> str:
    event = events[index]
    before = events[index - 1] if index > 0 else None
    after = events[index + 1] if index + 1 < len(events) else None
    if before and after:
        if event.height_m > before.height_m and event.height_m > after.height_m:
            return "HIGH"
        if event.height_m < before.height_m and event.height_m < after.height_m:
            return "LOW"
    return "TURNING_POINT"


def bracket_scene(when: datetime, events: list[TideEvent]) -> dict[str, str]:
    target = when.timestamp()
    if len(events) < 2:
        return {"tide_screen_status": "UNMATCHED_INSUFFICIENT_EVENTS"}

    lo, hi = 0, len(events)
    while lo < hi:
        mid = (lo + hi) // 2
        if events[mid].when_local.timestamp() < target:
            lo = mid + 1
        else:
            hi = mid
    idx = lo
    if idx == 0 or idx >= len(events):
        return {"tide_screen_status": "UNMATCHED_NO_BRACKET"}

    prev_event = events[idx - 1]
    next_event = events[idx]
    span_minutes = (next_event.when_local - prev_event.when_local).total_seconds() / 60.0
    if span_minutes <= 0:
        return {"tide_screen_status": "UNMATCHED_BAD_ORDER"}
    since_prev = (when - prev_event.when_local).total_seconds() / 60.0
    phase = min(1.0, max(0.0, since_prev / span_minutes))
    stage = "RISING" if next_event.height_m > prev_event.height_m else "FALLING"
    approx_height = prev_event.height_m + phase * (next_event.height_m - prev_event.height_m)
    nearest = "PREVIOUS" if phase <= 0.5 else "NEXT"
    nearest_minutes = min(since_prev, span_minutes - since_prev)
    quality = "GOOD" if span_minutes <= 900 else "LONG_BRACKET_REVIEW"

    return {
        "tide_screen_status": "MATCHED",
        "tide_station": STATION_NAME,
        "tide_station_id": STATION_ID,
        "tide_source_type": SOURCE_TYPE,
        "tide_datum": SOURCE_DATUM,
        "tide_stage": stage,
        "tide_phase_0_1": f"{phase:.4f}",
        "tide_bracket_minutes": f"{span_minutes:.1f}",
        "tide_minutes_from_previous_extremum": f"{since_prev:.1f}",
        "tide_minutes_to_next_extremum": f"{span_minutes - since_prev:.1f}",
        "tide_nearest_extremum": nearest,
        "tide_nearest_extremum_minutes": f"{nearest_minutes:.1f}",
        "tide_previous_datetime_bangkok": prev_event.when_local.isoformat(),
        "tide_previous_height_m_source_datum": f"{prev_event.height_m:.3f}",
        "tide_next_datetime_bangkok": next_event.when_local.isoformat(),
        "tide_next_height_m_source_datum": f"{next_event.height_m:.3f}",
        "tide_estimated_height_m_source_datum": f"{approx_height:.3f}",
        "tide_height_method": "LINEAR_BETWEEN_EXTREMA_SCREENING_ONLY",
        "tide_source_url": prev_event.source_url if prev_event.source_url == next_event.source_url else f"{prev_event.source_url};{next_event.source_url}",
        "tide_match_qa": quality,
    }


MATCH_FIELDS = [
    "tide_screen_status", "tide_station", "tide_station_id", "tide_source_type",
    "tide_datum", "tide_stage", "tide_phase_0_1", "tide_bracket_minutes",
    "tide_minutes_from_previous_extremum", "tide_minutes_to_next_extremum",
    "tide_nearest_extremum", "tide_nearest_extremum_minutes",
    "tide_previous_datetime_bangkok", "tide_previous_height_m_source_datum",
    "tide_next_datetime_bangkok", "tide_next_height_m_source_datum",
    "tide_estimated_height_m_source_datum", "tide_height_method", "tide_source_url",
    "tide_match_qa",
]


def write_tides(path: Path, events: list[TideEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "station_name", "station_name_th", "station_id", "datetime_bangkok",
        "datetime_utc", "event_type", "height_m_source_datum", "datum",
        "source_type", "source_name", "source_url", "source_year", "source_month",
        "qa_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for idx, event in enumerate(events):
            writer.writerow({
                "station_name": STATION_NAME,
                "station_name_th": STATION_NAME_TH,
                "station_id": STATION_ID,
                "datetime_bangkok": event.when_local.isoformat(),
                "datetime_utc": event.when_utc.isoformat().replace("+00:00", "Z"),
                "event_type": event_type(idx, events),
                "height_m_source_datum": f"{event.height_m:.3f}",
                "datum": SOURCE_DATUM,
                "source_type": SOURCE_TYPE,
                "source_name": SOURCE_NAME,
                "source_url": event.source_url,
                "source_year": event.source_year,
                "source_month": f"{event.source_month:02d}",
                "qa_status": "PARSED_FULL_MONTH_TABLE",
            })


def write_matched(path: Path, fields: list[str], scenes: list[dict[str, str]], events: list[TideEvent], min_year: int) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = list(fields)
    for field in MATCH_FIELDS:
        if field not in output_fields:
            output_fields.append(field)
    counts = {"sentinel2_total": 0, "sentinel2_matched": 0, "pre_min_year_or_non_s2": 0}
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        for row in scenes:
            out = dict(row)
            is_s2 = (row.get("dataset") or "").strip().lower() == "sentinel2"
            when = scene_time(row)
            if is_s2 and when.year >= min_year:
                counts["sentinel2_total"] += 1
                match = bracket_scene(when, events)
                out.update(match)
                if match.get("tide_screen_status") == "MATCHED":
                    counts["sentinel2_matched"] += 1
            else:
                counts["pre_min_year_or_non_s2"] += 1
                out["tide_screen_status"] = "NOT_TARGETED_EXTREMA_SCREENING"
            writer.writerow(out)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-catalog", type=Path, default=DEFAULT_SCENE_CATALOG)
    parser.add_argument("--tide-csv", type=Path, default=DEFAULT_TIDE_CSV)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--matched-output", type=Path, default=DEFAULT_MATCHED)
    parser.add_argument("--min-year", type=int, default=2017)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--request-delay", type=float, default=0.20)
    args = parser.parse_args()

    fields, scenes = read_scenes(args.scene_catalog)
    months = required_months(scenes, args.min_year)
    if not months:
        raise SystemExit("No target Sentinel-2 scene months found")

    all_events: list[TideEvent] = []
    pages: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    session = requests.Session()

    for idx, (year, month) in enumerate(months, start=1):
        requested_url = URL_TEMPLATE.format(year=year, month=month)
        try:
            page, final_url = fetch_month(session, year, month, args.timeout)
            events = parse_full_month(page, year, month, final_url)
            all_events.extend(events)
            pages.append({
                "year": year, "month": month, "requested_url": requested_url,
                "final_url": final_url, "event_count": len(events),
                "first_event": events[0].when_local.isoformat(),
                "last_event": events[-1].when_local.isoformat(),
                "status": "OK",
            })
            print(f"[{idx}/{len(months)}] {year}-{month:02d}: {len(events)} extrema")
        except Exception as exc:  # keep a complete manifest before failing QA
            failures.append({"year": year, "month": month, "url": requested_url, "error": str(exc)})
            print(f"[{idx}/{len(months)}] {year}-{month:02d}: FAILED {exc}")
        if args.request_delay:
            time.sleep(args.request_delay)

    # Dedupe overlaps if a source page repeats anything unexpectedly.
    unique: dict[tuple[datetime, float], TideEvent] = {}
    for event in all_events:
        unique[(event.when_local, round(event.height_m, 4))] = event
    events = sorted(unique.values(), key=lambda event: event.when_local)
    if len(events) < 2:
        raise SystemExit("No usable Ko Prap tide-extrema events parsed")

    write_tides(args.tide_csv, events)
    counts = write_matched(args.matched_output, fields, scenes, events, args.min_year)

    manifest = {
        "schema_version": "1.0",
        "station_name": STATION_NAME,
        "station_name_th": STATION_NAME_TH,
        "station_id": STATION_ID,
        "timezone": "Asia/Bangkok",
        "source_type": SOURCE_TYPE,
        "source_name": SOURCE_NAME,
        "url_template": URL_TEMPLATE,
        "datum": SOURCE_DATUM,
        "datum_note": "Do not relabel these heights as MSL. Use stage/phase for scene screening unless an official datum relationship is verified.",
        "height_method_note": "Any scene height in the matched catalog is linear between adjacent extrema and is screening-only, not an hourly harmonic prediction.",
        "scene_catalog": str(args.scene_catalog),
        "min_year": args.min_year,
        "required_months": [f"{year:04d}-{month:02d}" for year, month in months],
        "pages": pages,
        "failures": failures,
        "event_count": len(events),
        "match_counts": counts,
        "outputs": {"tide_csv": str(args.tide_csv), "matched_scene_catalog": str(args.matched_output)},
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"months": len(months), "events": len(events), "failures": len(failures), **counts}, ensure_ascii=False))

    # Required scene months must all parse and every target S2 scene must bracket.
    if failures:
        raise SystemExit(f"Tide source failures: {len(failures)} month(s); see {args.manifest}")
    if counts["sentinel2_total"] == 0 or counts["sentinel2_matched"] != counts["sentinel2_total"]:
        raise SystemExit(f"Incomplete S2 tide matching: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
