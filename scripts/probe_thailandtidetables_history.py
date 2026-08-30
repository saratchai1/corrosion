#!/usr/bin/env python3
"""Probe complete historical Pak Nam Mae Klong tide-table years.

The public ThailandTideTables pages are retrieved through the same Jina Reader
transport used by the existing 2023-2025 recovery workflow. Each requested
calendar year is accepted only when all twelve monthly pages pass the existing
station identity, month identity, coverage, and event-continuity checks.

January and July are checked first. If either sentinel month is unavailable or
invalid, the year cannot satisfy the all-12-month acceptance rule, so the other
months are recorded as not probed rather than wasting repeated network calls.
Missing years are retained in the manifest and are never silently substituted.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cache_thailandtidetables_via_jina import (
    DEFAULT_CACHE,
    build_session,
    cache_month,
)

DEFAULT_OUTPUT = Path(
    "data/tide/samut_songkhram/"
    "pak_nam_mae_klong_historical_availability.json"
)
SENTINEL_MONTHS = (1, 7)


def probe_month(
    session: Any,
    *,
    year: int,
    month: int,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        result = cache_month(
            session,
            year=year,
            month=month,
            cache_dir=cache_dir,
            refresh=refresh,
            timeout_seconds=timeout_seconds,
        )
        return {
            "month": month,
            "status": "AVAILABLE_VALIDATED",
            "event_count": result["event_count"],
            "day_count": result["day_count"],
            "source_url": result["resolved_url"],
            "retrieval_url": result["retrieval_url"],
            "sha256": result["sha256"],
            "coverage_qa": result["coverage_qa"],
        }
    except Exception as exc:  # noqa: BLE001 - evidence manifest must retain failures
        return {
            "month": month,
            "status": "UNAVAILABLE_OR_INVALID",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def probe_year(
    year: int,
    *,
    cache_dir: Path,
    refresh: bool,
    timeout_seconds: float,
    sleep_seconds: float,
) -> dict[str, Any]:
    session = build_session()
    by_month: dict[int, dict[str, Any]] = {}

    for month in SENTINEL_MONTHS:
        by_month[month] = probe_month(
            session,
            year=year,
            month=month,
            cache_dir=cache_dir,
            refresh=refresh,
            timeout_seconds=timeout_seconds,
        )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    sentinel_failed = any(
        by_month[month]["status"] != "AVAILABLE_VALIDATED"
        for month in SENTINEL_MONTHS
    )
    remaining = [month for month in range(1, 13) if month not in SENTINEL_MONTHS]
    if sentinel_failed:
        for month in remaining:
            by_month[month] = {
                "month": month,
                "status": "NOT_PROBED_AFTER_SENTINEL_FAILURE",
                "reason": (
                    "A complete year requires all 12 months; January or July "
                    "was unavailable or invalid."
                ),
            }
    else:
        for month in remaining:
            by_month[month] = probe_month(
                session,
                year=year,
                month=month,
                cache_dir=cache_dir,
                refresh=refresh,
                timeout_seconds=timeout_seconds,
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    months = [by_month[month] for month in range(1, 13)]
    available = [row for row in months if row["status"] == "AVAILABLE_VALIDATED"]
    complete = len(available) == 12
    return {
        "year": year,
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "available_month_count": len(available),
        "missing_or_invalid_months": [
            row["month"] for row in months if row["status"] != "AVAILABLE_VALIDATED"
        ],
        "event_count": sum(int(row.get("event_count", 0)) for row in available),
        "sentinel_months": list(SENTINEL_MONTHS),
        "sentinel_short_circuit_used": sentinel_failed,
        "months": months,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.05)
    parser.add_argument(
        "--require-at-least",
        type=int,
        default=1,
        help="Minimum number of complete years required for success.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = [
        probe_year(
            year,
            cache_dir=args.cache_dir,
            refresh=args.refresh,
            timeout_seconds=args.timeout_seconds,
            sleep_seconds=args.sleep_seconds,
        )
        for year in sorted(set(args.years))
    ]
    complete_years = [row["year"] for row in results if row["status"] == "COMPLETE"]
    incomplete_years = [row["year"] for row in results if row["status"] != "COMPLETE"]
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "station": "Pak Nam Mae Klong",
        "requested_years": sorted(set(args.years)),
        "complete_years": complete_years,
        "incomplete_years": incomplete_years,
        "year_results": results,
        "acceptance_rule": (
            "A year is usable only when all 12 monthly pages pass station/month "
            "identity, event coverage and continuity checks."
        ),
        "probe_strategy": (
            "January and July are probed first; a failure short-circuits the "
            "remaining months because the year cannot meet the all-month rule."
        ),
        "scientific_limit": (
            "Availability of published extrema does not make them observed water "
            "levels. Scene-time values remain screening estimates interpolated "
            "between secondary published extrema."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if len(complete_years) < args.require_at_least:
        raise SystemExit(
            f"only {len(complete_years)} complete historical years; "
            f"require at least {args.require_at_least}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
