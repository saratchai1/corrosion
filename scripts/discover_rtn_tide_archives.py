#!/usr/bin/env python3
"""Recover removed official tide-table PDFs from the Internet Archive.

The Hydrographic Department periodically changes or removes annual download
paths. This utility queries the Internet Archive CDX index for exact and narrow
wildcard matches, validates recovered bytes as PDFs, and places them in the
cache format consumed by ``build_rtn_mae_klong_tide_catalog.py``.

An archived copy remains an official Hydrographic Department document, but the
manifest records both the original official URL and the archive retrieval URL.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

DEFAULT_YEARS = (2023, 2024)
DEFAULT_CACHE = Path(".cache/rtn_tides/samut_songkhram")
DEFAULT_REPORT = Path(
    "data/tide/samut_songkhram/pak_nam_mae_klong_archive_discovery.json"
)
CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WAYBACK_PREFIX = "https://web.archive.org/web"


def official_candidates(year: int) -> list[str]:
    buddhist_short = year - 1957
    return [
        f"https://www.hydro.navy.mi.th/download/Water_lever{buddhist_short:02d}/MSL/KL{year}%20msl.pdf",
        f"http://www.hydro.navy.mi.th/download/Water_lever{buddhist_short:02d}/MSL/KL{year}%20msl.pdf",
        f"https://hydro.navy.mi.th/download/Water_lever{buddhist_short:02d}/MSL/KL{year}%20msl.pdf",
        f"http://hydro.navy.mi.th/download/Water_lever{buddhist_short:02d}/MSL/KL{year}%20msl.pdf",
    ]


def cdx_queries(year: int) -> list[str]:
    values = list(official_candidates(year))
    values.extend(
        [
            f"www.hydro.navy.mi.th/download/*/MSL/KL{year}*",
            f"hydro.navy.mi.th/download/*/MSL/KL{year}*",
            f"www.hydro.navy.mi.th/download/*/*/MK{year}*",
            f"hydro.navy.mi.th/download/*/*/MK{year}*",
        ]
    )
    return list(dict.fromkeys(values))


def is_pdf(content: bytes, content_type: str = "") -> bool:
    return content.startswith(b"%PDF-") or "application/pdf" in content_type.lower()


def query_cdx(
    session: requests.Session, query: str, timeout_seconds: float
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    params = {
        "url": query,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        "filter": ["statuscode:200"],
        "collapse": "digest",
        "from": "2022",
        "to": "2026",
    }
    try:
        response = session.get(CDX_ENDPOINT, params=params, timeout=timeout_seconds)
        report = {
            "query": query,
            "request_url": response.url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "bytes": len(response.content),
        }
        if response.status_code != 200:
            return [], report
        payload = response.json()
        if not payload or len(payload) < 2:
            return [], report
        headers = payload[0]
        rows = [dict(zip(headers, row)) for row in payload[1:]]
        return rows, report
    except (requests.RequestException, ValueError) as exc:
        return [], {
            "query": query,
            "error": type(exc).__name__,
            "detail": str(exc),
        }


def candidate_score(row: dict[str, str], year: int) -> tuple[int, str]:
    original = row.get("original", "")
    lowered = original.lower()
    score = 0
    if f"kl{year}" in lowered:
        score += 100
    if f"mk{year}" in lowered:
        score += 80
    if "/msl/" in lowered:
        score += 50
    if "water_lever" in lowered:
        score += 20
    if lowered.endswith(".pdf"):
        score += 10
    if row.get("mimetype") == "application/pdf":
        score += 5
    return score, row.get("timestamp", "")


def archive_url(row: dict[str, str]) -> str:
    timestamp = row["timestamp"]
    original = row["original"]
    return f"{WAYBACK_PREFIX}/{timestamp}id_/{original}"


def recover_year(
    year: int,
    *,
    session: requests.Session,
    cache_dir: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    queries_report: list[dict[str, Any]] = []
    rows_by_capture: dict[tuple[str, str], dict[str, str]] = {}
    for query in cdx_queries(year):
        rows, report = query_cdx(session, query, timeout_seconds)
        report["result_count"] = len(rows)
        queries_report.append(report)
        for row in rows:
            original = row.get("original", "")
            if str(year) not in original:
                continue
            rows_by_capture[(row.get("timestamp", ""), original)] = row

    candidates = sorted(
        rows_by_capture.values(),
        key=lambda row: candidate_score(row, year),
        reverse=True,
    )
    download_attempts: list[dict[str, Any]] = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    for row in candidates:
        score, _timestamp = candidate_score(row, year)
        if score < 100:
            continue
        retrieval_url = archive_url(row)
        try:
            response = session.get(
                retrieval_url, timeout=timeout_seconds, allow_redirects=True
            )
            attempt = {
                "retrieval_url": retrieval_url,
                "resolved_url": response.url,
                "original_official_url": row.get("original", ""),
                "timestamp": row.get("timestamp", ""),
                "score": score,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(response.content),
            }
            download_attempts.append(attempt)
            if response.status_code != 200 or not is_pdf(
                response.content, response.headers.get("content-type", "")
            ):
                continue
            cache_path = cache_dir / f"pak_nam_mae_klong_{year}_msl.pdf"
            source_path = cache_dir / f"pak_nam_mae_klong_{year}_source.json"
            cache_path.write_bytes(response.content)
            source_path.write_text(
                json.dumps(
                    {
                        "year": year,
                        "source_url": retrieval_url,
                        "original_official_url": row.get("original", ""),
                        "archive_timestamp": row.get("timestamp", ""),
                        "attempted_urls": download_attempts,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return {
                "year": year,
                "status": "RECOVERED_FROM_INTERNET_ARCHIVE",
                "original_official_url": row.get("original", ""),
                "retrieval_url": retrieval_url,
                "archive_timestamp": row.get("timestamp", ""),
                "bytes": len(response.content),
                "cache_path": str(cache_path),
                "queries": queries_report,
                "download_attempts": download_attempts,
            }
        except requests.RequestException as exc:
            download_attempts.append(
                {
                    "retrieval_url": retrieval_url,
                    "original_official_url": row.get("original", ""),
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }
            )

    return {
        "year": year,
        "status": "ARCHIVE_NOT_FOUND",
        "candidate_count": len(candidates),
        "queries": queries_report,
        "download_attempts": download_attempts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="exit non-zero unless every requested year is recovered",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    years = sorted(set(args.years))
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; corrosion-research/1.0; "
                "+https://github.com/saratchai1/corrosion)"
            )
        }
    )
    results = []
    for year in years:
        print(f"Searching Internet Archive for official {year} MSL PDF...", file=sys.stderr)
        result = recover_year(
            year,
            session=session,
            cache_dir=args.cache_dir,
            timeout_seconds=args.timeout_seconds,
        )
        results.append(result)
        print(f"  {year}: {result['status']}", file=sys.stderr)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "recover removed official Hydrographic Department tide-table PDFs",
        "years_requested": years,
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    recovered = sum(
        result["status"] == "RECOVERED_FROM_INTERNET_ARCHIVE" for result in results
    )
    if args.require_all and recovered != len(years):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
