#!/usr/bin/env python3
"""Parse official 2023 Ko Prap high/low tide extrema and match Surat scenes.

Source: Royal Thai Navy Hydrographic Department KP2023.pdf. The table contains
predicted turning-point times/heights above Lowest Low Water (LLW), not hourly
MSL. We therefore use it for tide stage/phase screening of 2023 imagery and do
not relabel the heights as MSL.

The 2023 PDF lays out three months per landscape page, with two day columns per
month (days 1-15 and 16-end). Parsing is coordinate-based so the interleaved PDF
text order does not need to be trusted.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pdfplumber
import requests

BANGKOK = timezone(timedelta(hours=7))
YEAR = 2023
STATION_NAME = "Ko Prap"
DATUM = "LOWEST_LOW_WATER"
SOURCE_URL = "https://www.hydro.navy.mi.th/tide66/KP2023.pdf"
SCENE_CATALOG = Path("data/catalog/surat_thani_mvp_optical_scenes.csv")
OUT_CSV = Path("data/tide/surat_thani/ko_prap_2023_extrema_llw.csv")
OUT_MANIFEST = Path("data/tide/surat_thani/ko_prap_2023_extrema_llw_manifest.json")
OUT_MATCHED = Path("data/catalog/surat_thani_2023_scenes_tide_phase.csv")
CACHE = Path(".cache/rtn_tides/surat_thani/ko_prap_2023.pdf")

TIME_RE = re.compile(r"^([01]\d|2[0-3])[0-5]\d$")
HEIGHT_RE = re.compile(r"^\d+(?:\.\d+)?$")
DAY_RE = re.compile(r"^\d{1,2}$")


@dataclass(frozen=True)
class Event:
    when_local: datetime
    height_m_llw: float
    source_page: int

    @property
    def when_utc(self) -> datetime:
        return self.when_local.astimezone(timezone.utc)


def download_pdf() -> tuple[bytes, str]:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE.exists() and CACHE.read_bytes().startswith(b"%PDF-"):
        return CACHE.read_bytes(), SOURCE_URL
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; corrosion-research/1.0; +https://github.com/saratchai1/corrosion)"
    })
    response = session.get(SOURCE_URL, timeout=90, allow_redirects=True)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise RuntimeError(f"2023 Ko Prap source did not return a PDF: {response.headers.get('content-type')}")
    CACHE.write_bytes(response.content)
    return response.content, response.url


def cluster_rows(words: list[dict[str, Any]], tolerance: float = 3.5) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        top = float(word["top"])
        if not rows or abs(top - centers[-1]) > tolerance:
            rows.append([word])
            centers.append(top)
        else:
            rows[-1].append(word)
            centers[-1] = sum(float(w["top"]) for w in rows[-1]) / len(rows[-1])
    return rows


def text(word: dict[str, Any]) -> str:
    return str(word.get("text", "")).strip().replace("−", "-")


def parse_block(
    page: Any,
    *,
    page_index: int,
    block_index: int,
    month: int,
    first_day: int,
    last_day: int,
) -> list[Event]:
    width = float(page.width)
    height = float(page.height)
    block_width = width / 6.0
    # Slight inward padding prevents words on table rules/neighbouring columns
    # from being assigned to two blocks.
    x0 = block_index * block_width + block_width * 0.015
    x1 = (block_index + 1) * block_width - block_width * 0.015
    words = [
        w for w in page.extract_words(
            x_tolerance=1.2,
            y_tolerance=2.0,
            keep_blank_chars=False,
            use_text_flow=False,
        )
        if x0 <= (float(w["x0"]) + float(w["x1"])) / 2.0 < x1
        and float(w["top"]) > height * 0.11
        and float(w["bottom"]) < height * 0.96
    ]

    # Day numbers sit at the left edge of each sixth-page subtable. Use only
    # the expected day range for this block to avoid mistaking time/height values.
    day_limit_x = x0 + block_width * 0.18
    anchors: list[tuple[int, float]] = []
    for w in words:
        token = text(w)
        if float(w["x0"]) > day_limit_x or not DAY_RE.fullmatch(token):
            continue
        day = int(token)
        if first_day <= day <= last_day:
            anchors.append((day, float(w["top"])))

    # Deduplicate same day labels, retaining the uppermost occurrence.
    anchor_map: dict[int, float] = {}
    for day, top in anchors:
        anchor_map[day] = min(top, anchor_map.get(day, top))
    expected = set(range(first_day, last_day + 1))
    if set(anchor_map) != expected:
        missing = sorted(expected.difference(anchor_map))
        raise ValueError(
            f"page {page_index + 1} month {month} days {first_day}-{last_day}: "
            f"day anchors missing {missing}; found={sorted(anchor_map)}"
        )

    ordered_anchors = sorted(anchor_map.items(), key=lambda item: item[1])
    events: list[Event] = []
    for idx, (day, top) in enumerate(ordered_anchors):
        next_top = ordered_anchors[idx + 1][1] if idx + 1 < len(ordered_anchors) else height * 0.955
        # Include all rows belonging to this day. A small negative tolerance
        # captures the first time/height pair on the same baseline as the day label.
        day_words = [w for w in words if top - 2.5 <= float(w["top"]) < next_top - 1.0]
        pairs: list[tuple[int, int, float]] = []
        for row in cluster_rows(day_words, tolerance=3.0):
            ordered = sorted(row, key=lambda w: float(w["x0"]))
            for pos, w in enumerate(ordered):
                token = text(w)
                if not TIME_RE.fullmatch(token):
                    continue
                # The height is the first plausible decimal/number to the right
                # on the same row within this subtable.
                height_value: float | None = None
                for candidate in ordered[pos + 1 :]:
                    ctext = text(candidate)
                    if not HEIGHT_RE.fullmatch(ctext):
                        continue
                    try:
                        value = float(ctext)
                    except ValueError:
                        continue
                    if 0.0 <= value <= 5.0:
                        height_value = value
                        break
                if height_value is None:
                    continue
                hour = int(token[:2])
                minute = int(token[2:])
                pairs.append((hour, minute, height_value))

        # Some rows can be split by PDF text baselines. If the row-wise pass
        # missed a pair, do a conservative x/y-neighbour fallback.
        if len(pairs) < 1:
            times = [w for w in day_words if TIME_RE.fullmatch(text(w))]
            heights = [
                w for w in day_words
                if HEIGHT_RE.fullmatch(text(w))
                and "." in text(w)
                and 0.0 <= float(text(w)) <= 5.0
            ]
            for tw in times:
                candidates = [
                    hw for hw in heights
                    if float(hw["x0"]) > float(tw["x1"])
                    and abs(float(hw["top"]) - float(tw["top"])) <= 5.0
                ]
                if not candidates:
                    continue
                hw = min(candidates, key=lambda item: float(item["x0"]) - float(tw["x1"]))
                token = text(tw)
                pairs.append((int(token[:2]), int(token[2:]), float(text(hw))))

        unique = sorted(set(pairs))
        if not (1 <= len(unique) <= 4):
            raise ValueError(
                f"page {page_index + 1} month {month} day {day}: "
                f"parsed {len(unique)} extrema pairs {unique}"
            )
        for hour, minute, level in unique:
            events.append(
                Event(
                    when_local=datetime(YEAR, month, day, hour, minute, tzinfo=BANGKOK),
                    height_m_llw=level,
                    source_page=page_index + 1,
                )
            )
    return events


def parse_pdf(content: bytes) -> tuple[list[Event], dict[str, Any]]:
    events: list[Event] = []
    page_reports: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) < 4:
            raise ValueError(f"Ko Prap 2023 PDF has only {len(pdf.pages)} pages")
        for page_index in range(4):
            page = pdf.pages[page_index]
            months = [page_index * 3 + 1, page_index * 3 + 2, page_index * 3 + 3]
            page_events: list[Event] = []
            for month_offset, month in enumerate(months):
                import calendar
                max_day = calendar.monthrange(YEAR, month)[1]
                left_last = min(15, max_day)
                page_events.extend(
                    parse_block(
                        page,
                        page_index=page_index,
                        block_index=month_offset * 2,
                        month=month,
                        first_day=1,
                        last_day=left_last,
                    )
                )
                if max_day >= 16:
                    page_events.extend(
                        parse_block(
                            page,
                            page_index=page_index,
                            block_index=month_offset * 2 + 1,
                            month=month,
                            first_day=16,
                            last_day=max_day,
                        )
                    )
            events.extend(page_events)
            page_reports.append({
                "pdf_page_index_zero_based": page_index,
                "months": months,
                "event_count": len(page_events),
            })

        report = {
            "pdf_page_count": len(pdf.pages),
            "parsed_table_pages": 4,
            "page_reports": page_reports,
        }

    # Dedupe and sort.
    by_key: dict[tuple[datetime, float], Event] = {}
    for event in events:
        by_key[(event.when_local, round(event.height_m_llw, 3))] = event
    events = sorted(by_key.values(), key=lambda e: e.when_local)

    # Every calendar day should have at least one extrema prediction.
    days = {e.when_local.date() for e in events}
    if len(days) != 365:
        raise ValueError(f"parsed extrema cover {len(days)}/365 days")
    if not (650 <= len(events) <= 1200):
        raise ValueError(f"implausible 2023 extrema count: {len(events)}")
    return events, report


def event_kind(index: int, events: list[Event]) -> str:
    event = events[index]
    before = events[index - 1] if index > 0 else None
    after = events[index + 1] if index + 1 < len(events) else None
    if before and after:
        if event.height_m_llw >= before.height_m_llw and event.height_m_llw >= after.height_m_llw:
            return "HIGH"
        if event.height_m_llw <= before.height_m_llw and event.height_m_llw <= after.height_m_llw:
            return "LOW"
    return "TURNING_POINT"


def write_events(path: Path, events: list[Event], resolved_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "datetime_bangkok", "datetime_utc", "tide_height_m_llw", "event_type",
            "station_name", "datum", "source_url", "source_year", "source_page", "qa_status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for idx, event in enumerate(events):
            writer.writerow({
                "datetime_bangkok": event.when_local.isoformat(),
                "datetime_utc": event.when_utc.isoformat().replace("+00:00", "Z"),
                "tide_height_m_llw": f"{event.height_m_llw:.2f}",
                "event_type": event_kind(idx, events),
                "station_name": STATION_NAME,
                "datum": DATUM,
                "source_url": resolved_url,
                "source_year": YEAR,
                "source_page": event.source_page,
                "qa_status": "official_pdf_extrema_coordinate_parser",
            })


def read_scenes() -> tuple[list[str], list[dict[str, str]]]:
    with SCENE_CATALOG.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("scene catalog has no header")
        return list(reader.fieldnames), list(reader)


def parse_scene_time(row: dict[str, str]) -> datetime:
    value = (row.get("acquisition_datetime_bangkok") or "").strip()
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(BANGKOK) if parsed.tzinfo else parsed.replace(tzinfo=BANGKOK)
    value = (row.get("acquisition_datetime_utc") or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(BANGKOK)


def bracket_scene(when: datetime, events: list[Event]) -> dict[str, str]:
    target = when.timestamp()
    timestamps = [e.when_local.timestamp() for e in events]
    import bisect
    idx = bisect.bisect_left(timestamps, target)
    if idx == 0 or idx >= len(events):
        return {"tide_phase_status": "UNMATCHED_NO_BRACKET"}
    before = events[idx - 1]
    after = events[idx]
    span = (after.when_local - before.when_local).total_seconds()
    elapsed = (when - before.when_local).total_seconds()
    if span <= 0 or elapsed < 0 or elapsed > span:
        return {"tide_phase_status": "UNMATCHED_BAD_BRACKET"}
    phase = elapsed / span
    stage = "RISING" if after.height_m_llw > before.height_m_llw else "FALLING"
    return {
        "tide_phase_status": "MATCHED_OFFICIAL_EXTREMA",
        "tide_phase_station": STATION_NAME,
        "tide_phase_datum": DATUM,
        "tide_stage": stage,
        "tide_phase_0_1": f"{phase:.4f}",
        "tide_previous_datetime_bangkok": before.when_local.isoformat(),
        "tide_previous_height_m_llw": f"{before.height_m_llw:.2f}",
        "tide_next_datetime_bangkok": after.when_local.isoformat(),
        "tide_next_height_m_llw": f"{after.height_m_llw:.2f}",
        "tide_bracket_minutes": f"{span / 60.0:.1f}",
        "tide_source_url": SOURCE_URL,
        "tide_height_interpretation": "LLW extrema only; phase/stage screening, not MSL height interpolation",
    }


def write_scene_matches(events: list[Event]) -> dict[str, int]:
    fields, scenes = read_scenes()
    out_fields = list(fields)
    additions = [
        "tide_phase_status", "tide_phase_station", "tide_phase_datum", "tide_stage",
        "tide_phase_0_1", "tide_previous_datetime_bangkok", "tide_previous_height_m_llw",
        "tide_next_datetime_bangkok", "tide_next_height_m_llw", "tide_bracket_minutes",
        "tide_source_url", "tide_height_interpretation",
    ]
    for field in additions:
        if field not in out_fields:
            out_fields.append(field)
    matched = 0
    target = 0
    rows: list[dict[str, str]] = []
    for row in scenes:
        merged = dict(row)
        when = parse_scene_time(row)
        if when.year == YEAR and (row.get("dataset") or "").strip().lower() == "sentinel2":
            target += 1
            result = bracket_scene(when, events)
            merged.update(result)
            if result.get("tide_phase_status") == "MATCHED_OFFICIAL_EXTREMA":
                matched += 1
        else:
            merged["tide_phase_status"] = "NOT_2023_SENTINEL2"
        rows.append(merged)
    OUT_MATCHED.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MATCHED.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {"target_scenes": target, "matched_scenes": matched}


def main() -> int:
    content, resolved_url = download_pdf()
    events, parser_report = parse_pdf(content)
    write_events(OUT_CSV, events, resolved_url)
    match_report = write_scene_matches(events)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "station_name": STATION_NAME,
        "station_coordinates_lon_lat": [99.434444, 9.265],
        "year": YEAR,
        "datum": DATUM,
        "data_kind": "predicted high/low tide extrema",
        "observed": False,
        "source_url": resolved_url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "event_count": len(events),
        "day_count": len({e.when_local.date() for e in events}),
        "minimum_height_m_llw": min(e.height_m_llw for e in events),
        "maximum_height_m_llw": max(e.height_m_llw for e in events),
        "parser": parser_report,
        "scene_match": match_report,
        "outputs": {
            "extrema_csv": str(OUT_CSV),
            "scene_phase_csv": str(OUT_MATCHED),
        },
        "scientific_limit": (
            "2023 extrema are above Lowest Low Water. Use stage/phase for scene screening; "
            "do not compare their numeric heights directly with the 2026 MSL hourly series."
        ),
    }
    OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if match_report["target_scenes"] == 0 or match_report["matched_scenes"] != match_report["target_scenes"]:
        raise SystemExit(f"2023 scene tide-phase matching incomplete: {match_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
