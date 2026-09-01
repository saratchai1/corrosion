#!/usr/bin/env python3
"""Match satellite acquisition times to free hourly tide predictions.

The script does not download or infer tide data. It joins a scene catalog to an
explicit, cited hourly tide CSV and preserves whether each value was an exact
hour or a linear interpolation between two predictions.

Expected tide CSV columns:
    datetime_bangkok,tide_m_msl,station_name,datum,source_url,source_year,qa_status

Only ``datetime_bangkok`` and ``tide_m_msl`` are required. Naive tide times are
interpreted as Asia/Bangkok; scene times must be ISO-8601 UTC or offset-aware.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

BANGKOK = ZoneInfo("Asia/Bangkok")
DEFAULT_SCENE_CATALOG = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes.csv"
)
DEFAULT_TIDE_CSV = Path(
    "data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv"
)
DEFAULT_OUTPUT = Path(
    "data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv"
)
REQUIRED_TIDE_COLUMNS = {"datetime_bangkok", "tide_m_msl"}
TIDE_METADATA_COLUMNS = [
    "tide_source_url",
    "tide_match_method",
    "tide_match_gap_minutes",
    "tide_prediction_qa",
]


@dataclass(frozen=True)
class TidePoint:
    when_utc: datetime
    level_m_msl: float
    station_name: str
    datum: str
    source_url: str
    qa_status: str

    @property
    def epoch_seconds(self) -> float:
        return self.when_utc.timestamp()


def parse_datetime(value: str, *, naive_timezone: ZoneInfo | None = None) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("empty datetime")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        if naive_timezone is None:
            raise ValueError(f"timezone missing from datetime: {value!r}")
        parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(timezone.utc)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def load_tides(
    path: Path,
    *,
    default_station: str,
    default_datum: str,
    default_source_url: str,
) -> list[TidePoint]:
    fieldnames, rows = read_csv(path)
    missing = REQUIRED_TIDE_COLUMNS.difference(fieldnames)
    if missing:
        raise ValueError(
            f"tide CSV is missing required columns: {', '.join(sorted(missing))}"
        )

    by_timestamp: dict[float, TidePoint] = {}
    for line_number, row in enumerate(rows, start=2):
        try:
            when_utc = parse_datetime(
                row["datetime_bangkok"], naive_timezone=BANGKOK
            )
            level = float(row["tide_m_msl"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid tide row {line_number}: {exc}") from exc
        if not math.isfinite(level):
            raise ValueError(f"non-finite tide value at row {line_number}")

        point = TidePoint(
            when_utc=when_utc,
            level_m_msl=level,
            station_name=(row.get("station_name") or default_station).strip(),
            datum=(row.get("datum") or default_datum).strip(),
            source_url=(row.get("source_url") or default_source_url).strip(),
            qa_status=(row.get("qa_status") or "source_table_transcribed").strip(),
        )
        key = point.epoch_seconds
        previous = by_timestamp.get(key)
        if previous and not math.isclose(
            previous.level_m_msl, point.level_m_msl, abs_tol=1e-9
        ):
            raise ValueError(
                "duplicate tide timestamp with conflicting values at "
                f"{point.when_utc.isoformat()}"
            )
        by_timestamp[key] = point

    points = sorted(by_timestamp.values(), key=lambda item: item.when_utc)
    if len(points) < 2:
        raise ValueError("tide CSV must contain at least two unique hourly predictions")
    return points


def scene_datetime(row: dict[str, str]) -> datetime:
    value = row.get("acquisition_datetime_utc", "").strip()
    if value:
        return parse_datetime(value)
    value = row.get("acquisition_datetime_bangkok", "").strip()
    if value:
        return parse_datetime(value, naive_timezone=BANGKOK)
    raise ValueError(
        f"scene {row.get('scene_id', '<unknown>')} has no acquisition datetime"
    )


def match_tide(
    when_utc: datetime,
    points: list[TidePoint],
    timestamps: list[float],
    *,
    max_gap_minutes: float,
) -> dict[str, str]:
    target = when_utc.timestamp()
    index = bisect.bisect_left(timestamps, target)

    if index < len(points) and math.isclose(
        timestamps[index], target, abs_tol=1e-6
    ):
        point = points[index]
        return {
            "tide_station": point.station_name,
            "tide_level": f"{point.level_m_msl:.3f}",
            "tide_datum": point.datum,
            "tide_status": "predicted_exact",
            "tide_source_url": point.source_url,
            "tide_match_method": "exact_hour",
            "tide_match_gap_minutes": "0.0",
            "tide_prediction_qa": point.qa_status,
        }

    if index == 0 or index == len(points):
        return unmatched_result("unmatched_no_bracket")

    before = points[index - 1]
    after = points[index]
    before_gap = (target - before.epoch_seconds) / 60.0
    after_gap = (after.epoch_seconds - target) / 60.0
    largest_gap = max(before_gap, after_gap)
    if before_gap < 0 or after_gap < 0:
        raise RuntimeError("tide points are not sorted")
    if largest_gap > max_gap_minutes:
        return unmatched_result("unmatched_gap", largest_gap)

    span = after.epoch_seconds - before.epoch_seconds
    if span <= 0:
        raise RuntimeError("invalid tide bracketing interval")
    fraction = (target - before.epoch_seconds) / span
    level = before.level_m_msl + fraction * (
        after.level_m_msl - before.level_m_msl
    )
    source_urls = sorted(
        value for value in {before.source_url, after.source_url} if value
    )
    qa_values = sorted(
        value for value in {before.qa_status, after.qa_status} if value
    )
    station = before.station_name or after.station_name
    datum = before.datum or after.datum
    if before.station_name and after.station_name and before.station_name != after.station_name:
        return unmatched_result("unmatched_station_change", largest_gap)
    if before.datum and after.datum and before.datum != after.datum:
        return unmatched_result("unmatched_datum_change", largest_gap)

    return {
        "tide_station": station,
        "tide_level": f"{level:.3f}",
        "tide_datum": datum,
        "tide_status": "predicted_interpolated",
        "tide_source_url": ";".join(source_urls),
        "tide_match_method": "linear_between_predictions",
        "tide_match_gap_minutes": f"{largest_gap:.1f}",
        "tide_prediction_qa": ";".join(qa_values),
    }


def unmatched_result(status: str, gap_minutes: float | None = None) -> dict[str, str]:
    return {
        "tide_station": "",
        "tide_level": "",
        "tide_datum": "",
        "tide_status": status,
        "tide_source_url": "",
        "tide_match_method": "",
        "tide_match_gap_minutes": (
            "" if gap_minutes is None else f"{gap_minutes:.1f}"
        ),
        "tide_prediction_qa": "",
    }


def ordered_output_fields(input_fields: Iterable[str]) -> list[str]:
    fields = list(input_fields)
    for field in (
        "tide_station",
        "tide_level",
        "tide_datum",
        "tide_status",
        *TIDE_METADATA_COLUMNS,
    ):
        if field not in fields:
            fields.append(field)
    return fields


def match_catalog(
    scene_catalog: Path,
    tide_csv: Path,
    output: Path,
    *,
    max_gap_minutes: float,
    default_station: str,
    default_datum: str,
    default_source_url: str,
) -> dict[str, object]:
    scene_fields, scenes = read_csv(scene_catalog)
    tides = load_tides(
        tide_csv,
        default_station=default_station,
        default_datum=default_datum,
        default_source_url=default_source_url,
    )
    timestamps = [point.epoch_seconds for point in tides]
    statuses: dict[str, int] = {}
    matched_rows: list[dict[str, str]] = []

    for row in scenes:
        result = match_tide(
            scene_datetime(row),
            tides,
            timestamps,
            max_gap_minutes=max_gap_minutes,
        )
        merged = dict(row)
        merged.update(result)
        matched_rows.append(merged)
        status = result["tide_status"]
        statuses[status] = statuses.get(status, 0) + 1

    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ordered_output_fields(scene_fields)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(matched_rows)

    matched_count = sum(
        count for status, count in statuses.items() if status.startswith("predicted_")
    )
    return {
        "scene_catalog": str(scene_catalog),
        "tide_csv": str(tide_csv),
        "output": str(output),
        "scene_count": len(scenes),
        "matched_count": matched_count,
        "matched_fraction": round(matched_count / max(len(scenes), 1), 5),
        "status_counts": statuses,
        "max_gap_minutes": max_gap_minutes,
        "tide_range_utc": [
            tides[0].when_utc.isoformat(),
            tides[-1].when_utc.isoformat(),
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-catalog", type=Path, default=DEFAULT_SCENE_CATALOG)
    parser.add_argument("--tide-csv", type=Path, default=DEFAULT_TIDE_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-gap-minutes", type=float, default=90.0)
    parser.add_argument("--station-name", default="Pak Nam Mae Klong")
    parser.add_argument("--datum", default="MSL")
    parser.add_argument(
        "--source-url",
        default="https://hydro.navy.mi.th/waterlaveltable",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_gap_minutes <= 0:
        raise SystemExit("--max-gap-minutes must be positive")
    try:
        report = match_catalog(
            args.scene_catalog,
            args.tide_csv,
            args.output,
            max_gap_minutes=args.max_gap_minutes,
            default_station=args.station_name,
            default_datum=args.datum,
            default_source_url=args.source_url,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
