#!/usr/bin/env python3
"""Recover removed official tide-table PDFs from Common Crawl WARC files.

Search-engine indexes still expose text from some Hydrographic Department PDFs
whose original download URLs now return HTTP 404. Common Crawl is a separate,
open web archive and may retain the original response bytes. This script:

1. queries a bounded set of Common Crawl monthly URL indexes;
2. retrieves matching WARC byte ranges;
3. decodes the archived HTTP response with ``warcio``;
4. accepts only payloads that begin with the PDF signature; and
5. writes the cache files consumed by ``build_rtn_mae_klong_tide_catalog.py``.

The original Hydrographic Department URL remains the scientific source. The
Common Crawl index, WARC filename, offset, length and retrieval URL are retained
as recovery provenance. No tide values are inferred by this utility.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from warcio.archiveiterator import ArchiveIterator

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
DATA_PREFIX = "https://data.commoncrawl.org/"
DEFAULT_YEARS = (2023, 2024, 2025)
DEFAULT_CACHE = Path(".cache/rtn_tides/samut_songkhram")
DEFAULT_REPORT = Path(
    "data/tide/samut_songkhram/pak_nam_mae_klong_commoncrawl_recovery.json"
)


def legacy_paths(year: int) -> list[str]:
    buddhist_short = year - 1957
    filenames = (
        f"KL{year}%20msl.pdf",
        f"KL{year}%20MSL.pdf",
        f"KL{year}msl.pdf",
        f"KL{year}MSL.pdf",
        f"KL{year}.pdf",
    )
    paths = []
    for host in ("www.hydro.navy.mi.th", "hydro.navy.mi.th"):
        for filename in filenames:
            paths.append(
                f"{host}/download/Water_lever{buddhist_short:02d}/MSL/{filename}"
            )
            paths.append(
                f"{host}/download/Water_level{buddhist_short:02d}/MSL/{filename}"
            )
    return list(dict.fromkeys(paths))


def wildcard_queries(year: int) -> list[str]:
    buddhist_short = year - 1957
    return [
        f"www.hydro.navy.mi.th/download/Water_lever{buddhist_short:02d}/MSL/KL{year}*",
        f"hydro.navy.mi.th/download/Water_lever{buddhist_short:02d}/MSL/KL{year}*",
        f"www.hydro.navy.mi.th/download/Water_level{buddhist_short:02d}/MSL/KL{year}*",
        f"hydro.navy.mi.th/download/Water_level{buddhist_short:02d}/MSL/KL{year}*",
        f"hydro.navy.mi.th/storage/frontend/article/*/file/*/*{year}*",
    ]


def crawl_priority(crawl_id: str, year: int) -> tuple[int, str]:
    try:
        crawl_year = int(crawl_id.split("-")[2])
    except (IndexError, ValueError):
        crawl_year = 0
    distance = abs(crawl_year - year)
    same_or_next = 0 if crawl_year in {year, year + 1} else 1
    return same_or_next * 100 + distance, crawl_id


def select_crawls(colls: list[dict[str, Any]], year: int, limit: int) -> list[dict[str, Any]]:
    eligible = []
    for coll in colls:
        crawl_id = str(coll.get("id", ""))
        if not crawl_id.startswith("CC-MAIN-"):
            continue
        try:
            crawl_year = int(crawl_id.split("-")[2])
        except (IndexError, ValueError):
            continue
        if year - 1 <= crawl_year <= 2026:
            eligible.append(coll)
    eligible.sort(key=lambda item: crawl_priority(str(item["id"]), year))
    return eligible[:limit]


def read_ndjson(response: requests.Response) -> list[dict[str, Any]]:
    rows = []
    for line in response.text.splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def query_index(
    session: requests.Session,
    endpoint: str,
    url_pattern: str,
    *,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = {
        "url": url_pattern,
        "output": "json",
        "filter": ["status:200"],
        "matchType": "prefix" if url_pattern.endswith("*") else "exact",
    }
    try:
        response = session.get(endpoint, params=params, timeout=timeout_seconds)
        report = {
            "endpoint": endpoint,
            "url_pattern": url_pattern,
            "request_url": response.url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "bytes": len(response.content),
        }
        if response.status_code != 200:
            return [], report
        rows = read_ndjson(response)
        report["result_count"] = len(rows)
        return rows, report
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        return [], {
            "endpoint": endpoint,
            "url_pattern": url_pattern,
            "error": type(exc).__name__,
            "detail": str(exc),
        }


def record_score(record: dict[str, Any], year: int) -> tuple[int, str]:
    url = str(record.get("url", ""))
    lowered = url.lower()
    score = 0
    if f"kl{year}" in lowered:
        score += 100
    if "/msl/" in lowered:
        score += 50
    if "water_lever" in lowered:
        score += 20
    if lowered.endswith(".pdf"):
        score += 10
    mime = str(record.get("mime-detected") or record.get("mime") or "").lower()
    if "pdf" in mime:
        score += 10
    if str(record.get("status", "")) == "200":
        score += 5
    timestamp = str(record.get("timestamp", ""))
    return score, timestamp


def warc_retrieval_url(record: dict[str, Any]) -> str:
    filename = str(record["filename"])
    offset = int(record["offset"])
    length = int(record["length"])
    return f"{DATA_PREFIX}{filename}#offset={offset}&length={length}"


def extract_pdf_from_warc(blob: bytes) -> tuple[bytes | None, dict[str, Any]]:
    record_reports = []
    try:
        iterator = ArchiveIterator(io.BytesIO(blob), arc2warc=True)
        for record in iterator:
            report = {
                "rec_type": record.rec_type,
                "target_uri": record.rec_headers.get_header("WARC-Target-URI"),
                "content_type": record.http_headers.get_header("Content-Type")
                if record.http_headers
                else "",
            }
            if record.rec_type != "response":
                record_reports.append(report)
                continue
            try:
                payload = record.content_stream().read()
            except Exception as exc:  # warcio may reject corrupt archived encodings
                report["decode_error"] = f"{type(exc).__name__}: {exc}"
                record_reports.append(report)
                continue
            report["payload_bytes"] = len(payload)
            report["payload_sha256"] = hashlib.sha256(payload).hexdigest()
            record_reports.append(report)
            if payload.startswith(b"%PDF-"):
                return payload, {"records": record_reports}
    except Exception as exc:
        return None, {
            "records": record_reports,
            "warc_error": f"{type(exc).__name__}: {exc}",
        }
    return None, {"records": record_reports}


def retrieve_record(
    session: requests.Session,
    record: dict[str, Any],
    *,
    timeout_seconds: float,
) -> tuple[bytes | None, dict[str, Any]]:
    filename = str(record.get("filename", ""))
    offset = int(record.get("offset", 0))
    length = int(record.get("length", 0))
    if not filename or length <= 0:
        return None, {"status": "INVALID_INDEX_RECORD", "record": record}
    url = f"{DATA_PREFIX}{filename}"
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
    try:
        response = session.get(url, headers=headers, timeout=timeout_seconds)
        report = {
            "status": "DOWNLOADED_WARC_RANGE",
            "warc_url": url,
            "range": headers["Range"],
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "bytes": len(response.content),
            "record": record,
        }
        if response.status_code not in {200, 206}:
            return None, report
        payload, parse_report = extract_pdf_from_warc(response.content)
        report["parse"] = parse_report
        if payload is None:
            report["status"] = "NO_PDF_PAYLOAD"
            return None, report
        report["status"] = "PDF_RECOVERED"
        report["pdf_bytes"] = len(payload)
        report["pdf_sha256"] = hashlib.sha256(payload).hexdigest()
        return payload, report
    except requests.RequestException as exc:
        return None, {
            "status": "REQUEST_ERROR",
            "warc_url": url,
            "range": headers["Range"],
            "error": type(exc).__name__,
            "detail": str(exc),
            "record": record,
        }


def recover_year(
    year: int,
    *,
    session: requests.Session,
    colls: list[dict[str, Any]],
    cache_dir: Path,
    crawl_limit: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    crawls = select_crawls(colls, year, crawl_limit)
    query_reports = []
    records_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    # Prefix queries normally cover encoded filename variants. Exact paths are
    # attempted only against the most relevant crawls if no prefix result exists.
    for coll in crawls:
        endpoint = str(coll["cdx-api"])
        for pattern in wildcard_queries(year):
            records, report = query_index(
                session, endpoint, pattern, timeout_seconds=timeout_seconds
            )
            report["crawl_id"] = coll["id"]
            query_reports.append(report)
            for record in records:
                key = (
                    str(record.get("filename", "")),
                    str(record.get("offset", "")),
                    str(record.get("length", "")),
                )
                records_by_key[key] = record
        if records_by_key:
            break

    if not records_by_key:
        for coll in crawls[:3]:
            endpoint = str(coll["cdx-api"])
            for path in legacy_paths(year)[:4]:
                records, report = query_index(
                    session, endpoint, path, timeout_seconds=timeout_seconds
                )
                report["crawl_id"] = coll["id"]
                query_reports.append(report)
                for record in records:
                    key = (
                        str(record.get("filename", "")),
                        str(record.get("offset", "")),
                        str(record.get("length", "")),
                    )
                    records_by_key[key] = record
            if records_by_key:
                break

    records = sorted(
        records_by_key.values(),
        key=lambda item: record_score(item, year),
        reverse=True,
    )
    retrieval_reports = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    for record in records[:10]:
        score, _timestamp = record_score(record, year)
        if score < 100:
            continue
        pdf, report = retrieve_record(
            session, record, timeout_seconds=timeout_seconds * 2
        )
        report["score"] = score
        retrieval_reports.append(report)
        if pdf is None:
            continue
        original_url = str(record.get("url", ""))
        if not original_url.startswith(("http://", "https://")):
            original_url = f"https://{original_url}"
        cache_path = cache_dir / f"pak_nam_mae_klong_{year}_msl.pdf"
        source_path = cache_dir / f"pak_nam_mae_klong_{year}_source.json"
        cache_path.write_bytes(pdf)
        source_path.write_text(
            json.dumps(
                {
                    "year": year,
                    "source_url": original_url,
                    "recovery_method": "COMMON_CRAWL_WARC",
                    "commoncrawl_index_record": record,
                    "commoncrawl_retrieval_url": warc_retrieval_url(record),
                    "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                    "attempted_urls": retrieval_reports,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "year": year,
            "status": "RECOVERED_FROM_COMMON_CRAWL",
            "original_official_url": original_url,
            "commoncrawl_retrieval_url": warc_retrieval_url(record),
            "pdf_bytes": len(pdf),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "cache_path": str(cache_path),
            "crawl_ids_queried": [item["id"] for item in crawls],
            "query_reports": query_reports,
            "retrieval_reports": retrieval_reports,
        }

    return {
        "year": year,
        "status": "COMMON_CRAWL_COPY_NOT_FOUND",
        "candidate_record_count": len(records),
        "crawl_ids_queried": [item["id"] for item in crawls],
        "official_paths_considered": legacy_paths(year),
        "query_reports": query_reports,
        "retrieval_reports": retrieval_reports,
    }


def load_collections(
    session: requests.Session, *, timeout_seconds: float
) -> list[dict[str, Any]]:
    response = session.get(COLLINFO_URL, timeout=timeout_seconds)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, list):
        raise ValueError("Common Crawl collection listing is not a list")
    return [item for item in value if isinstance(item, dict) and item.get("cdx-api")]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--crawl-limit", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--require-all", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    years = sorted(set(args.years))
    if args.crawl_limit <= 0 or args.timeout_seconds <= 0:
        raise SystemExit("crawl limit and timeout must be positive")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; corrosion-research/1.0; "
                "+https://github.com/saratchai1/corrosion)"
            )
        }
    )
    colls = load_collections(session, timeout_seconds=args.timeout_seconds)
    results = []
    for year in years:
        print(f"Searching Common Crawl for official {year} MSL PDF...", file=sys.stderr)
        result = recover_year(
            year,
            session=session,
            colls=colls,
            cache_dir=args.cache_dir,
            crawl_limit=args.crawl_limit,
            timeout_seconds=args.timeout_seconds,
        )
        results.append(result)
        print(f"  {year}: {result['status']}", file=sys.stderr)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "recover removed official Hydrographic Department tide-table PDFs",
        "archive": "Common Crawl",
        "years_requested": years,
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    recovered = sum(
        item["status"] == "RECOVERED_FROM_COMMON_CRAWL" for item in results
    )
    if args.require_all and recovered != len(years):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
