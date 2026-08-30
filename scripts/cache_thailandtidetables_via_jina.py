#!/usr/bin/env python3
"""Cache ThailandTideTables monthly pages through Jina Reader.

ThailandTideTables returns HTTP 403 to GitHub-hosted runners. Jina Reader can
retrieve the public page and expose its table as Markdown. This utility parses
that Markdown, performs conservative coverage and continuity checks, and writes
a minimal synthetic HTML cache consumed by the secondary tide builder.

A calendar day may legitimately contain no reported extremum at this mixed-tide
station. Therefore completeness is evaluated from event continuity, coverage
near month boundaries, and maximum gaps—not by requiring every date to appear.
The original ThailandTideTables URL remains the data source; Jina is recorded
separately as the retrieval transport.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL_TEMPLATE = (
    "https://www.thailandtidetables.com/"
    "tide-tables-pak-nam-mae-klong-samut-songkhram-year-{year}-{month:02d}-474.php"
)
JINA_TEMPLATES = (
    "https://r.jina.ai/http://www.thailandtidetables.com/"
    "tide-tables-pak-nam-mae-klong-samut-songkhram-year-{year}-{month:02d}-474.php",
    "https://r.jina.ai/https://www.thailandtidetables.com/"
    "tide-tables-pak-nam-mae-klong-samut-songkhram-year-{year}-{month:02d}-474.php",
)
DEFAULT_CACHE = Path(".cache/thailandtidetables/pak_nam_mae_klong")
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
DAY_RE = re.compile(r"^(?:0?[1-9]|[12]\d|3[01])$")
FLOAT_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:\s*m)?$", re.IGNORECASE)
MIN_DAY_COVERAGE_FRACTION = 0.70
MAX_MONTH_EDGE_GAP_DAYS = 2
MAX_EVENT_GAP_HOURS = 72.0


@dataclass(frozen=True)
class Event:
    day: int
    hour: int
    minute: int
    height: float


def normalize(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[[^\]]*\]\([^)]*\)", "", value)
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
            "Accept": "text/plain,text/markdown,*/*",
        }
    )
    return session


def source_url(year: int, month: int) -> str:
    return URL_TEMPLATE.format(year=year, month=month)


def event_datetime(year: int, month: int, event: Event) -> datetime:
    return datetime(year, month, event.day, event.hour, event.minute)


def maximum_event_gap_hours(year: int, month: int, events: list[Event]) -> float:
    values = [event_datetime(year, month, event) for event in events]
    if len(values) < 2:
        return math.inf
    return max(
        (after - before).total_seconds() / 3600
        for before, after in zip(values, values[1:])
    )


def longest_missing_day_run(expected_days: set[int], actual_days: set[int]) -> int:
    longest = 0
    current = 0
    for day in sorted(expected_days):
        if day in actual_days:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def validate_month_events(
    events: list[Event], *, year: int, month: int
) -> dict[str, object]:
    if not events:
        raise ValueError(f"no extrema found for {year}-{month:02d}")
    days_in_month = calendar.monthrange(year, month)[1]
    expected_days = set(range(1, days_in_month + 1))
    actual_days = {event.day for event in events}
    extra_days = sorted(actual_days.difference(expected_days))
    if extra_days:
        raise ValueError(f"invalid days for {year}-{month:02d}: {extra_days}")

    coverage_fraction = len(actual_days) / days_in_month
    first_day = min(actual_days)
    last_day = max(actual_days)
    longest_missing = longest_missing_day_run(expected_days, actual_days)
    max_gap = maximum_event_gap_hours(year, month, events)

    if coverage_fraction < MIN_DAY_COVERAGE_FRACTION:
        raise ValueError(
            f"low day coverage for {year}-{month:02d}: {coverage_fraction:.1%}"
        )
    if first_day > 1 + MAX_MONTH_EDGE_GAP_DAYS:
        raise ValueError(
            f"first reported day too late for {year}-{month:02d}: {first_day}"
        )
    if last_day < days_in_month - MAX_MONTH_EDGE_GAP_DAYS:
        raise ValueError(
            f"last reported day too early for {year}-{month:02d}: {last_day}"
        )
    if longest_missing > MAX_MONTH_EDGE_GAP_DAYS:
        raise ValueError(
            f"too many consecutive dates without extrema for {year}-{month:02d}: "
            f"{longest_missing}"
        )
    if max_gap > MAX_EVENT_GAP_HOURS:
        raise ValueError(
            f"event gap too large for {year}-{month:02d}: {max_gap:.2f} h"
        )
    if len(events) < days_in_month:
        raise ValueError(
            f"too few extrema for {year}-{month:02d}: {len(events)}"
        )

    return {
        "days_in_month": days_in_month,
        "reported_day_count": len(actual_days),
        "day_coverage_fraction": round(coverage_fraction, 5),
        "missing_days": sorted(expected_days.difference(actual_days)),
        "longest_missing_day_run": longest_missing,
        "first_reported_day": first_day,
        "last_reported_day": last_day,
        "maximum_intra_month_event_gap_hours": round(max_gap, 5),
    }


def parse_markdown(markdown: str, *, year: int, month: int) -> tuple[list[Event], dict[str, object]]:
    expected_heading = f"{calendar.month_name[month]} {year}"
    if "Pak Nam Mae Klong" not in markdown or expected_heading not in markdown:
        raise ValueError(
            f"station/month identity missing for {year}-{month:02d}"
        )
    if "Full month view" in markdown:
        markdown = markdown.split("Full month view", 1)[1]

    events: dict[tuple[int, int, int], Event] = {}
    current_day: int | None = None
    for raw_line in markdown.splitlines():
        if "|" not in raw_line:
            continue
        cells = [normalize(cell) for cell in raw_line.strip().strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if DAY_RE.fullmatch(first):
            current_day = int(first)
        time_match = None
        for cell in cells:
            time_match = TIME_RE.search(cell)
            if time_match:
                break
        height = None
        for cell in reversed(cells):
            if FLOAT_RE.fullmatch(cell):
                height = float(cell.lower().removesuffix("m").strip())
                break
        if current_day is None or time_match is None or height is None:
            continue
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        key = (current_day, hour, minute)
        existing = events.get(key)
        if existing is not None and not math.isclose(
            existing.height, height, rel_tol=0.0, abs_tol=0.001
        ):
            raise ValueError(
                f"conflicting duplicate for {year}-{month:02d} {key}: "
                f"{existing.height} vs {height}"
            )
        events[key] = Event(current_day, hour, minute, height)

    output = sorted(events.values(), key=lambda item: (item.day, item.hour, item.minute))
    qa = validate_month_events(output, year=year, month=month)
    return output, qa


def synthetic_html(year: int, month: int, events: list[Event]) -> str:
    lines = [
        "<!doctype html>",
        "<html><head><meta charset=\"utf-8\"></head><body>",
        f"<h1>Pak Nam Mae Klong Tide Tables {calendar.month_name[month]} {year}</h1>",
        "<p>Full month view</p>",
        "<table><thead><tr><th>DAY</th><th>TIME</th><th>HEIGHT</th></tr></thead><tbody>",
    ]
    previous_day = None
    for event in events:
        day_text = f"{event.day:02d}" if event.day != previous_day else ""
        previous_day = event.day
        lines.append(
            "<tr>"
            f"<td>{html.escape(day_text)}</td>"
            f"<td>{event.hour:02d}:{event.minute:02d}</td>"
            f"<td>{event.height:.3f}</td>"
            "</tr>"
        )
    lines.extend(["</tbody></table>", "</body></html>"])
    return "\n".join(lines) + "\n"


def fetch_reader(
    session: requests.Session,
    *,
    year: int,
    month: int,
    timeout_seconds: float,
) -> tuple[str, str, dict[str, object]]:
    attempts = []
    for template in JINA_TEMPLATES:
        retrieval_url = template.format(year=year, month=month)
        response = session.get(retrieval_url, timeout=timeout_seconds)
        attempts.append(
            {
                "retrieval_url": retrieval_url,
                "resolved_url": response.url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(response.content),
            }
        )
        if response.status_code == 200 and "Pak Nam Mae Klong" in response.text:
            return response.text, response.url, {"attempts": attempts}
    raise RuntimeError(
        f"Jina Reader could not retrieve {year}-{month:02d}: {attempts}"
    )


def cache_month(
    session: requests.Session,
    *,
    year: int,
    month: int,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: float,
) -> dict[str, object]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    html_path = cache_dir / f"{year}-{month:02d}.html"
    meta_path = cache_dir / f"{year}-{month:02d}.json"
    markdown_path = cache_dir / f"{year}-{month:02d}.reader.md"
    if not refresh and html_path.exists() and meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))

    markdown, retrieval_url, diagnostics = fetch_reader(
        session, year=year, month=month, timeout_seconds=timeout_seconds
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    events, coverage_qa = parse_markdown(markdown, year=year, month=month)
    rendered = synthetic_html(year, month, events)
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    fetched_at = datetime.now(timezone.utc).isoformat()
    html_path.write_text(rendered, encoding="utf-8")
    metadata = {
        "requested_url": source_url(year, month),
        "resolved_url": source_url(year, month),
        "retrieval_url": retrieval_url,
        "retrieval_method": "jina_reader_markdown_to_validated_synthetic_html",
        "fetched_at_utc": fetched_at,
        "sha256": digest,
        "event_count": len(events),
        "day_count": len({event.day for event in events}),
        "coverage_qa": coverage_qa,
        "minimum_height_m_chart_datum": min(event.height for event in events),
        "maximum_height_m_chart_datum": max(event.height for event in events),
        "reader_diagnostics": diagnostics,
    }
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def cache_years(
    years: Iterable[int],
    *,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: float,
    sleep_seconds: float,
) -> list[dict[str, object]]:
    session = build_session()
    results = []
    for year in sorted(set(years)):
        for month in range(1, 13):
            print(f"Caching {year}-{month:02d} via Jina Reader...", file=sys.stderr)
            result = cache_month(
                session,
                year=year,
                month=month,
                cache_dir=cache_dir,
                refresh=refresh,
                timeout_seconds=timeout_seconds,
            )
            results.append(result)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = cache_years(
        args.years,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        timeout_seconds=args.timeout_seconds,
        sleep_seconds=args.sleep_seconds,
    )
    print(
        json.dumps(
            {
                "cached_months": len(results),
                "years": sorted(set(args.years)),
                "event_count": sum(int(item["event_count"]) for item in results),
                "months_with_missing_calendar_days": sum(
                    bool(item["coverage_qa"]["missing_days"]) for item in results
                ),
                "maximum_event_gap_hours": max(
                    float(item["coverage_qa"]["maximum_intra_month_event_gap_hours"])
                    for item in results
                ),
                "retrieval_methods": sorted(
                    {str(item["retrieval_method"]) for item in results}
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
