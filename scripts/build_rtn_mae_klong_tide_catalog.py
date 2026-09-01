#!/usr/bin/env python3
"""Download and parse official Pak Nam Mae Klong hourly MSL tide tables.

The Royal Thai Navy Hydrographic Department publishes one station PDF per year.
This script resolves archived URL variants, validates each PDF, extracts the last
12 monthly tables using word coordinates, and writes a fully cited hourly CSV.

The output contains *predicted* tide heights, not observed water levels.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pdfplumber
import requests

BANGKOK = timezone(timedelta(hours=7))
DEFAULT_YEARS = (2023, 2024, 2025, 2026)
DEFAULT_OUTPUT = Path(
    "data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv"
)
DEFAULT_MANIFEST = Path(
    "data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl_manifest.json"
)
DEFAULT_CACHE = Path(".cache/rtn_tides/samut_songkhram")
STATION_NAME = "Pak Nam Mae Klong"
DATUM = "MSL"
OFFICIAL_LANDING_PAGE = "https://hydro.navy.mi.th/waterlaveltable"
NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class DownloadedPdf:
    year: int
    source_url: str
    content: bytes
    attempted_urls: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class HourlyPrediction:
    when_local: datetime
    level_m_msl: float
    source_url: str
    source_year: int
    qa_status: str


def year_url_candidates(year: int) -> list[str]:
    known = {
        2026: [
            "https://hydro.navy.mi.th/storage/frontend/article/23009/file/th/MK2026mls.pdf"
        ],
        2025: [
            "https://www.hydro.navy.mi.th/download/Water_lever68/MSL/KL2025%20msl.pdf"
        ],
        2024: [
            "https://www.hydro.navy.mi.th/download/Water_lever67/MSL/KL2024%20msl.pdf"
        ],
    }
    urls = list(known.get(year, []))
    buddhist_short = year - 1957
    hosts = ("www.hydro.navy.mi.th", "hydro.navy.mi.th")
    folder_stems = ("Water_lever", "Water_level")
    datum_folders = ("MSL", "msl")
    filenames = (
        f"KL{year}%20msl.pdf",
        f"KL{year}%20MSL.pdf",
        f"KL{year}msl.pdf",
        f"KL{year}MSL.pdf",
        f"KL{year}.pdf",
        f"MK{year}mls.pdf",
        f"MK{year}msl.pdf",
    )
    for host in hosts:
        for folder_stem in folder_stems:
            for datum_folder in datum_folders:
                for filename in filenames:
                    urls.append(
                        f"https://{host}/download/{folder_stem}{buddhist_short:02d}/"
                        f"{datum_folder}/{filename}"
                    )
    return list(dict.fromkeys(urls))


def is_pdf_response(response: requests.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    return response.content.startswith(b"%PDF-") or "application/pdf" in content_type


def download_year_pdf(
    year: int,
    *,
    cache_dir: Path,
    timeout_seconds: float,
    session: requests.Session,
) -> DownloadedPdf:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"pak_nam_mae_klong_{year}_msl.pdf"
    source_path = cache_dir / f"pak_nam_mae_klong_{year}_source.json"
    if cache_path.exists() and source_path.exists():
        content = cache_path.read_bytes()
        if content.startswith(b"%PDF-"):
            source = json.loads(source_path.read_text(encoding="utf-8"))
            return DownloadedPdf(
                year=year,
                source_url=source["source_url"],
                content=content,
                attempted_urls=tuple(source.get("attempted_urls", [])),
            )

    attempts: list[dict[str, Any]] = []
    for url in year_url_candidates(year):
        try:
            response = session.get(url, timeout=timeout_seconds, allow_redirects=True)
            attempt = {
                "url": url,
                "resolved_url": response.url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(response.content),
            }
            attempts.append(attempt)
            if response.status_code != 200 or not is_pdf_response(response):
                continue
            content = response.content
            cache_path.write_bytes(content)
            source_path.write_text(
                json.dumps(
                    {
                        "year": year,
                        "source_url": response.url,
                        "attempted_urls": attempts,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return DownloadedPdf(
                year=year,
                source_url=response.url,
                content=content,
                attempted_urls=tuple(attempts),
            )
        except requests.RequestException as exc:
            attempts.append({"url": url, "error": type(exc).__name__, "detail": str(exc)})

    compact = "; ".join(
        f"{item.get('status_code', item.get('error', 'unknown'))}: {item['url']}"
        for item in attempts
    )
    raise RuntimeError(f"no official MSL tide PDF found for {year}; attempts: {compact}")


def cluster_words_by_row(
    words: list[dict[str, Any]], tolerance: float = 3.5
) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        if not rows or abs(top - centers[-1]) > tolerance:
            rows.append([word])
            centers.append(top)
        else:
            rows[-1].append(word)
            centers[-1] = sum(float(item["top"]) for item in rows[-1]) / len(rows[-1])
    return rows


def numeric_word(word: dict[str, Any]) -> tuple[float, str] | None:
    text = str(word.get("text", "")).strip().replace("−", "-")
    if not NUMBER_RE.fullmatch(text):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value, text


def parse_page_rows(page: Any, *, expected_days: int) -> dict[int, list[float]]:
    words = page.extract_words(
        x_tolerance=1.5,
        y_tolerance=2.0,
        keep_blank_chars=False,
        use_text_flow=False,
    )
    parsed: dict[int, list[float]] = {}
    width = float(page.width)
    for row in cluster_words_by_row(words):
        ordered = sorted(row, key=lambda item: float(item["x0"]))
        numeric = [
            (float(word["x0"]), *value)
            for word in ordered
            if (value := numeric_word(word)) is not None
        ]
        day_candidates = [
            (x0, int(value))
            for x0, value, text in numeric
            if x0 < width * 0.16 and text.isdigit() and 1 <= int(value) <= expected_days
        ]
        if not day_candidates:
            continue
        day_x, day = day_candidates[0]
        levels = [
            value
            for x0, value, _text in numeric
            if x0 > max(day_x + 8.0, width * 0.12)
        ]
        if len(levels) == 24:
            parsed[day] = levels

    if len(parsed) != expected_days:
        missing = sorted(set(range(1, expected_days + 1)).difference(parsed))
        raise ValueError(
            f"parsed {len(parsed)}/{expected_days} daily rows from PDF page; "
            f"missing days: {missing}"
        )
    for day, levels in parsed.items():
        if len(levels) != 24:
            raise ValueError(f"day {day} has {len(levels)} values instead of 24")
        if any(level < -8 or level > 8 for level in levels):
            raise ValueError(f"day {day} contains an implausible MSL tide value")
    return parsed


def extract_predictions(
    download: DownloadedPdf,
) -> tuple[list[HourlyPrediction], dict[str, Any]]:
    predictions: list[HourlyPrediction] = []
    with pdfplumber.open(io.BytesIO(download.content)) as pdf:
        if len(pdf.pages) < 12:
            raise ValueError(f"{download.year} PDF has only {len(pdf.pages)} pages")
        monthly_pages = pdf.pages[-12:]
        month_reports = []
        for month, page in enumerate(monthly_pages, start=1):
            expected_days = calendar.monthrange(download.year, month)[1]
            rows = parse_page_rows(page, expected_days=expected_days)
            for day in range(1, expected_days + 1):
                for hour, level in enumerate(rows[day]):
                    predictions.append(
                        HourlyPrediction(
                            when_local=datetime(
                                download.year, month, day, hour, tzinfo=BANGKOK
                            ),
                            level_m_msl=float(level),
                            source_url=download.source_url,
                            source_year=download.year,
                            qa_status="official_pdf_parsed_word_coordinates",
                        )
                    )
            month_reports.append(
                {
                    "month": month,
                    "pdf_page_index_zero_based": len(pdf.pages) - 12 + month - 1,
                    "day_count": expected_days,
                    "hour_count": expected_days * 24,
                }
            )
        report = {
            "year": download.year,
            "source_url": download.source_url,
            "pdf_page_count": len(pdf.pages),
            "sha256": hashlib.sha256(download.content).hexdigest(),
            "bytes": len(download.content),
            "hour_count": len(predictions),
            "minimum_msl_m": min(item.level_m_msl for item in predictions),
            "maximum_msl_m": max(item.level_m_msl for item in predictions),
            "months": month_reports,
            "attempted_urls": list(download.attempted_urls),
        }
    expected_hours = 8784 if calendar.isleap(download.year) else 8760
    if len(predictions) != expected_hours:
        raise ValueError(
            f"{download.year}: parsed {len(predictions)} hours, expected {expected_hours}"
        )
    return predictions, report


def write_csv(path: Path, predictions: Iterable[HourlyPrediction]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime_bangkok",
                "tide_m_msl",
                "station_name",
                "datum",
                "source_url",
                "source_year",
                "qa_status",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for item in sorted(predictions, key=lambda value: value.when_local):
            writer.writerow(
                {
                    "datetime_bangkok": item.when_local.isoformat(),
                    "tide_m_msl": f"{item.level_m_msl:.1f}",
                    "station_name": STATION_NAME,
                    "datum": DATUM,
                    "source_url": item.source_url,
                    "source_year": item.source_year,
                    "qa_status": item.qa_status,
                }
            )
            count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--refresh", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    years = sorted(set(args.years))
    if not years:
        raise SystemExit("at least one year is required")
    if args.refresh and args.cache_dir.exists():
        for path in args.cache_dir.glob("pak_nam_mae_klong_*"):
            path.unlink()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; corrosion-research/1.0; "
                "+https://github.com/saratchai1/corrosion)"
            )
        }
    )
    all_predictions: list[HourlyPrediction] = []
    year_reports = []
    for year in years:
        print(
            f"Downloading official Pak Nam Mae Klong MSL tide table for {year}...",
            file=sys.stderr,
        )
        downloaded = download_year_pdf(
            year,
            cache_dir=args.cache_dir,
            timeout_seconds=args.timeout_seconds,
            session=session,
        )
        predictions, report = extract_predictions(downloaded)
        all_predictions.extend(predictions)
        year_reports.append(report)
        print(
            f"  parsed {len(predictions)} hourly predictions from {report['source_url']}",
            file=sys.stderr,
        )

    row_count = write_csv(args.output, all_predictions)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "station_name": STATION_NAME,
        "datum": DATUM,
        "timezone": "Asia/Bangkok (UTC+07:00)",
        "data_kind": "hourly harmonic tide prediction",
        "observed": False,
        "official_landing_page": OFFICIAL_LANDING_PAGE,
        "years": years,
        "row_count": row_count,
        "output_csv": str(args.output),
        "parser": {
            "library": "pdfplumber",
            "monthly_page_rule": "last 12 PDF pages, January through December",
            "row_rule": "day plus exactly 24 numeric values grouped by word coordinates",
        },
        "sources": year_reports,
        "scientific_limit": (
            "Predicted station tide improves scene comparability but is not an observed "
            "water level at each planting plot."
        ),
    }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
