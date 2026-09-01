#!/usr/bin/env python3
"""Build pre-planting coastal context for the Samut Songkhram plots.

This analysis extends the existing 2023-2026 tide-aware screening backwards.
It preserves the accepted 2023-2026 selected scenes, chooses each earlier
WATERLINE scene against the same target predicted tide, and uses the existing
2026-anchored project transects so historical and recent movements are directly
comparable.

The output answers a narrow question: was there an apparent landward trend
before the project period, and how does that compare with 2023-2026?  It does
not infer that any change in trend was caused by planting.  Historical tide
values are secondary published extrema interpolations, not local observations.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from scripts.build_coastal_change_mvp import (
    build_composite,
    choose_water_mask,
    save_preview,
    write_json,
)
from scripts.build_tide_aware_project_edges import (
    COASTAL_CONTEXT_BUFFER_M,
    POSITIONAL_SCREENING_THRESHOLD_M,
    build_vegetation_proxy,
    finite_ratio,
    position_on_transect,
    project_waterline,
    save_lines,
    save_polygon,
)

ROOT = Path(__file__).resolve().parents[1]
CRS_WEB = "EPSG:4326"
CRS_ANALYSIS = "EPSG:32647"
TO_UTM = Transformer.from_crs(CRS_WEB, CRS_ANALYSIS, always_xy=True)
TO_WEB = Transformer.from_crs(CRS_ANALYSIS, CRS_WEB, always_xy=True)

DEFAULT_CATALOG = Path(
    "data/catalog/project_samut_songkhram_sentinel2_history_2017_2026.csv"
)
DEFAULT_CURRENT_SUMMARY = Path("data/processed/project_tide_aware/summary.json")
DEFAULT_PLOTS = Path("data/aoi/samut_songkhram_project_plots.geojson")
DEFAULT_AOI = Path("data/aoi/samut_songkhram_project_analysis_aoi.geojson")
DEFAULT_TRANSECTS = Path("data/processed/project_tide_aware/transects.geojson")
DEFAULT_CONTROLS = Path("data/processed/project_tide_aware/candidate_controls.csv")
DEFAULT_OUTPUT = Path("data/processed/project_preplanting_history")
DEFAULT_WEB = Path("web/public/data/project_preplanting_history")
DEFAULT_YEARS = tuple(range(2017, 2027))
MAX_HISTORICAL_TIDE_DELTA_M = 0.30
MAX_SECONDARY_BRACKET_MINUTES = 12 * 60


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def year_of(row: dict[str, str]) -> int:
    return int(row["acquisition_datetime_utc"][:4])


def parse_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def cloud_score(row: dict[str, str]) -> tuple[float, float, str, str]:
    return (
        parse_float(row.get("cloud_cover_aoi")) or 999.0,
        parse_float(row.get("cloud_cover_scene")) or 999.0,
        row["acquisition_datetime_utc"],
        row["scene_id"],
    )


def tide_eligible(row: dict[str, str]) -> bool:
    status = (row.get("tide_status") or "").strip()
    level = parse_float(row.get("tide_level"))
    if row.get("tide_datum") != "MSL" or level is None:
        return False
    if status == "predicted_interpolated":
        return True
    if status == "modelled_secondary_extrema_cosine":
        span = parse_float(row.get("tide_bracket_span_minutes"))
        return span is not None and span <= MAX_SECONDARY_BRACKET_MINUTES
    return False


def choose_display_and_waterline_scenes(
    rows: list[dict[str, str]],
    *,
    current_summary: dict[str, Any],
    years: Iterable[int],
    maximum_historical_delta_m: float,
) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]], list[dict[str, Any]]]:
    target = float(current_summary["waterline_scene_selection"]["target_tide_m_msl"])
    fixed_ids = {
        int(item["year"]): item["scene_id"]
        for item in current_summary["waterline_scene_selection"]["selected_scenes"]
    }
    by_year: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("dataset") == "sentinel2":
            by_year[year_of(row)].append(row)

    display: dict[int, dict[str, str]] = {}
    waterline: dict[int, dict[str, str]] = {}
    audit: list[dict[str, Any]] = []
    for year in sorted(set(int(value) for value in years)):
        candidates = sorted(by_year.get(year, []), key=cloud_score)
        if not candidates:
            raise ValueError(f"catalog has no Sentinel-2 candidates for {year}")

        fixed_id = fixed_ids.get(year)
        fixed = next((row for row in candidates if row["scene_id"] == fixed_id), None)
        eligible = [row for row in candidates if tide_eligible(row)]
        eligible.sort(
            key=lambda row: (
                abs(float(row["tide_level"]) - target),
                *cloud_score(row),
            )
        )
        if fixed is not None:
            chosen_display = fixed
            chosen_waterline = fixed
            acceptance = "CURRENT_ACCEPTED_SELECTION_PRESERVED"
        elif eligible:
            candidate = eligible[0]
            delta = abs(float(candidate["tide_level"]) - target)
            chosen_display = candidate
            if delta <= maximum_historical_delta_m:
                chosen_waterline = candidate
                acceptance = "HISTORICAL_TIDE_MATCH_ACCEPTED"
            else:
                chosen_waterline = None
                acceptance = "HISTORICAL_TIDE_DELTA_TOO_LARGE"
        else:
            chosen_display = candidates[0]
            chosen_waterline = None
            acceptance = "NO_VALIDATED_TIDE_METADATA_VISUAL_CONTEXT_ONLY"

        display[year] = chosen_display
        if chosen_waterline is not None:
            waterline[year] = chosen_waterline
        level = parse_float(chosen_display.get("tide_level"))
        audit.append(
            {
                "year": year,
                "scene_id": chosen_display["scene_id"],
                "date": chosen_display["acquisition_datetime_utc"][:10],
                "display_role": (
                    "TIDE_AWARE_WATERLINE_AND_IMAGERY"
                    if chosen_waterline is not None
                    else "VISUAL_AND_VEGETATION_CONTEXT_ONLY"
                ),
                "waterline_acceptance": acceptance,
                "tide_level_m_msl": level,
                "delta_from_current_target_m": (
                    None if level is None else round(level - target, 4)
                ),
                "tide_status": chosen_display.get("tide_status", "unverified"),
                "tide_source_tier": chosen_display.get("tide_source_tier", ""),
                "secondary_bracket_span_minutes": parse_float(
                    chosen_display.get("tide_bracket_span_minutes")
                ),
                "cloud_cover_aoi": parse_float(chosen_display.get("cloud_cover_aoi")),
                "source_url": chosen_display.get("source_url", ""),
            }
        )
    return display, waterline, audit


def load_plots(path: Path) -> tuple[list[dict[str, Any]], Any]:
    collection = read_json(path)
    plots = []
    for feature in collection["features"]:
        plots.append(
            {
                "plot_id": feature["properties"]["plot_id"],
                "properties": feature["properties"],
                "geometry_utm": transform(TO_UTM.transform, shape(feature["geometry"])).buffer(0),
            }
        )
    return plots, unary_union([item["geometry_utm"] for item in plots]).buffer(0)


def load_feature_union(path: Path) -> Any:
    collection = read_json(path)
    return unary_union(
        [transform(TO_UTM.transform, shape(feature["geometry"])) for feature in collection["features"]]
    ).buffer(0)


def load_transects(path: Path) -> list[dict[str, Any]]:
    collection = read_json(path)
    output = []
    for feature in collection["features"]:
        props = dict(feature["properties"])
        props["geometry_utm"] = transform(TO_UTM.transform, shape(feature["geometry"]))
        output.append(props)
    if not output:
        raise ValueError(f"no transects in {path}")
    return output


def load_controls(path: Path) -> dict[str, list[str]]:
    mapping_by_plot: dict[str, list[str]] = defaultdict(list)
    for row in load_csv(path):
        mapping_by_plot[row["plot_id"]].append(row["control_transect_id"])
    return dict(mapping_by_plot)


def regression_rate(values: dict[int, float | None], years: list[int]) -> float | None:
    available = [(year, values.get(year)) for year in years if values.get(year) is not None]
    if len(available) < 2:
        return None
    return float(
        np.polyfit(
            [year for year, _value in available],
            [float(value) for _year, value in available],
            1,
        )[0]
    )


def period_metrics(
    values: dict[int, float | None],
    years: list[int],
    *,
    threshold_m: float = POSITIONAL_SCREENING_THRESHOLD_M,
) -> dict[str, Any]:
    available = [(year, values.get(year)) for year in years if values.get(year) is not None]
    if len(available) < 2:
        return {
            "available_years": [year for year, _value in available],
            "n_observations": len(available),
            "start_year": None,
            "end_year": None,
            "nsm_m": None,
            "epr_m_per_year": None,
            "lrr_m_per_year": None,
            "classification": "INSUFFICIENT_DATA",
        }
    start_year, start_value = available[0]
    end_year, end_value = available[-1]
    nsm = float(end_value) - float(start_value)
    elapsed = end_year - start_year
    lrr = regression_rate(values, [year for year, _value in available])
    if nsm > threshold_m:
        classification = "APPARENT_SEAWARD"
    elif nsm < -threshold_m:
        classification = "APPARENT_LANDWARD"
    else:
        classification = "WITHIN_20M"
    return {
        "available_years": [year for year, _value in available],
        "n_observations": len(available),
        "start_year": start_year,
        "end_year": end_year,
        "nsm_m": round(nsm, 2),
        "epr_m_per_year": None if elapsed <= 0 else round(nsm / elapsed, 2),
        "lrr_m_per_year": None if lrr is None else round(lrr, 2),
        "classification": classification,
    }


def median_or_none(values: Iterable[float | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return None if not cleaned else round(float(np.median(cleaned)), 2)


def aggregate_period(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    classifications = Counter(row[f"{prefix}_classification"] for row in rows)
    available = [row for row in rows if row[f"{prefix}_classification"] != "INSUFFICIENT_DATA"]
    return {
        "transect_count": len(rows),
        "classified_transect_count": len(available),
        "median_nsm_m": median_or_none(row[f"{prefix}_nsm_m"] for row in available),
        "median_epr_m_per_year": median_or_none(
            row[f"{prefix}_epr_m_per_year"] for row in available
        ),
        "median_lrr_m_per_year": median_or_none(
            row[f"{prefix}_lrr_m_per_year"] for row in available
        ),
        "class_counts": dict(sorted(classifications.items())),
    }


def period_columns(prefix: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def add_geometry_output(path: Path, transects: list[dict[str, Any]], metric_rows: dict[tuple[str, str], dict[str, Any]]) -> None:
    features = []
    for transect in transects:
        if transect.get("role") != "TREATMENT":
            continue
        props = {
            key: value
            for key, value in transect.items()
            if key not in {"geometry_utm"}
        }
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
            row = metric_rows.get((transect["transect_id"], indicator))
            if row:
                for key, value in row.items():
                    if key not in {"transect_id", "plot_id", "indicator", "role"}:
                        props[f"{indicator.lower()}_{key}"] = value
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(transform(TO_WEB.transform, transect["geometry_utm"])),
            }
        )
    write_json(path, {"type": "FeatureCollection", "features": features})


def interpret_preplanting(historical: dict[str, Any], recent: dict[str, Any]) -> dict[str, Any]:
    historical_count = max(int(historical["classified_transect_count"]), 1)
    recent_count = max(int(recent["classified_transect_count"]), 1)
    historical_landward = int(historical["class_counts"].get("APPARENT_LANDWARD", 0))
    recent_landward = int(recent["class_counts"].get("APPARENT_LANDWARD", 0))
    historical_fraction = historical_landward / historical_count
    recent_fraction = recent_landward / recent_count
    historical_lrr = historical.get("median_lrr_m_per_year")
    recent_lrr = recent.get("median_lrr_m_per_year")

    if historical_fraction >= recent_fraction + 0.10:
        status = "MORE_APPARENT_LANDWARD_BEFORE_2023"
        headline = "ก่อนปี 2023 มีสัดส่วนแนวที่ปรากฏถอยเข้าฝั่งมากกว่าช่วงล่าสุด"
    elif historical_lrr is not None and recent_lrr is not None and historical_lrr < recent_lrr - 1.0:
        status = "HISTORICAL_TREND_MORE_LANDWARD"
        headline = "แนวโน้มกึ่งกลางก่อนปี 2023 เคลื่อนเข้าฝั่งมากกว่าช่วง 2023–2026"
    elif historical_fraction <= recent_fraction + 0.03:
        status = "NO_BROADLY_STRONGER_HISTORICAL_EROSION_SIGNAL"
        headline = "ยังไม่พบว่าช่วงก่อนปี 2023 มีการถอยร่นกว้างกว่าช่วงล่าสุดอย่างชัดเจน"
    else:
        status = "MIXED_HISTORICAL_SIGNAL"
        headline = "สัญญาณก่อนและหลังปี 2023 แตกต่างกันตามตำแหน่ง"
    return {
        "status": status,
        "headline_th": headline,
        "historical_apparent_landward_fraction": round(historical_fraction, 4),
        "recent_apparent_landward_fraction": round(recent_fraction, 4),
        "historical_median_lrr_m_per_year": historical_lrr,
        "recent_median_lrr_m_per_year": recent_lrr,
        "allowed_interpretation_th": (
            "ใช้ตอบได้เพียงว่าช่วงก่อนปี 2023 มีหรือไม่มีสัญญาณถอยร่นจากภาพมากกว่าช่วงล่าสุด; "
            "ยังใช้ยืนยันไม่ได้ว่าการเปลี่ยนแนวโน้มเกิดจากการปลูก"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--current-summary", type=Path, default=DEFAULT_CURRENT_SUMMARY)
    parser.add_argument("--plots", type=Path, default=DEFAULT_PLOTS)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--transects", type=Path, default=DEFAULT_TRANSECTS)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--web-output", type=Path, default=DEFAULT_WEB)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--max-historical-tide-delta-m", type=float, default=MAX_HISTORICAL_TIDE_DELTA_M)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    years = sorted(set(args.years))
    if 2023 not in years or 2026 not in years:
        raise ValueError("history must include the 2023 hinge and 2026 reference year")
    output = ROOT / args.output
    web_output = ROOT / args.web_output
    for path in (output, web_output):
        path.mkdir(parents=True, exist_ok=True)

    rows = load_csv(ROOT / args.catalog)
    current_summary = read_json(ROOT / args.current_summary)
    display_rows, waterline_rows, selection_audit = choose_display_and_waterline_scenes(
        rows,
        current_summary=current_summary,
        years=years,
        maximum_historical_delta_m=args.max_historical_tide_delta_m,
    )
    write_csv(output / "scene_selection_audit.csv", selection_audit)

    plots, plot_union = load_plots(ROOT / args.plots)
    aoi_utm = load_feature_union(ROOT / args.aoi)
    corridor = plot_union.buffer(COASTAL_CONTEXT_BUFFER_M).intersection(aoi_utm)
    year_rows: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("dataset") == "sentinel2" and year_of(row) in years:
            year_rows[year_of(row)].append(row)

    waterlines: dict[int, Any] = {}
    vegetation_edges: dict[int, Any] = {}
    vegetation_area_ha: dict[int, float] = {}
    waterline_qa: list[dict[str, Any]] = []
    display_scenes: list[dict[str, Any]] = []

    for year in years:
        display = display_rows[year]
        display_composite, display_valid_count, _display_grid = build_composite([display], "sentinel2")
        display_valid = display_valid_count > 0
        save_preview(web_output / "imagery" / f"{year}_selected.webp", display_composite, display_valid)
        display_scenes.append(
            {
                "year": year,
                "date": display["acquisition_datetime_utc"][:10],
                "scene_id": display["scene_id"],
                "image": f"data/project_preplanting_history/imagery/{year}_selected.webp",
                "tide_level_m_msl": parse_float(display.get("tide_level")),
                "tide_status": display.get("tide_status", "unverified"),
                "tide_source_tier": display.get("tide_source_tier", ""),
                "waterline_accepted": year in waterline_rows,
            }
        )

        if year in waterline_rows:
            selected = waterline_rows[year]
            composite, valid_count, grid = build_composite([selected], "sentinel2")
            valid = valid_count > 0
            green, swir1 = composite[1], composite[4]
            mndwi = finite_ratio(green - swir1, green + swir1)
            threshold, method, _ocean_mask, ocean, candidates = choose_water_mask(
                mndwi, valid, grid, aoi_utm
            )
            waterline = project_waterline(
                ocean,
                aoi_utm=aoi_utm,
                plot_union=plot_union,
                resolution_m=grid["resolution"],
            )
            if waterline.is_empty:
                raise RuntimeError(f"historical waterline is empty for {year}")
            waterlines[year] = waterline
            props = {
                "indicator": "WATERLINE",
                "role": "HISTORICAL_AND_RECENT_SCREENING",
                "year": year,
                "scene_id": selected["scene_id"],
                "acquisition_datetime_bangkok": selected["acquisition_datetime_bangkok"],
                "tide_level_m_msl": float(selected["tide_level"]),
                "tide_target_m_msl": current_summary["waterline_scene_selection"]["target_tide_m_msl"],
                "tide_delta_from_target_m": round(
                    float(selected["tide_level"])
                    - float(current_summary["waterline_scene_selection"]["target_tide_m_msl"]),
                    4,
                ),
                "tide_status": selected["tide_status"],
                "tide_source_tier": selected.get("tide_source_tier", ""),
                "mndwi_threshold": round(float(threshold), 5),
                "threshold_method": method,
                "source_resolution_m": grid["resolution"],
                "confidence": "LOW",
                "interpretation": (
                    "image-derived waterline selected near the current tide target; "
                    "screening only, not tide-normalized or surveyed"
                ),
            }
            save_lines(output / "waterline" / f"{year}.geojson", waterline, props)
            save_lines(web_output / "waterline" / f"{year}.geojson", waterline, props)
            waterline_qa.append(
                {
                    "year": year,
                    "scene_id": selected["scene_id"],
                    "tide_level_m_msl": float(selected["tide_level"]),
                    "delta_from_target_m": props["tide_delta_from_target_m"],
                    "mndwi_threshold": round(float(threshold), 5),
                    "threshold_method": method,
                    "valid_fraction": round(float(valid.mean()), 5),
                    "waterline_length_m": round(float(waterline.length), 2),
                    "threshold_candidates": json.dumps(candidates, ensure_ascii=False, sort_keys=True),
                }
            )

        composite, valid_count, grid = build_composite(
            sorted(year_rows[year], key=lambda row: row["acquisition_datetime_utc"]),
            "sentinel2",
        )
        valid = valid_count > 0
        polygon, edge, area_ha = build_vegetation_proxy(
            composite,
            valid,
            grid,
            corridor_utm=corridor,
        )
        vegetation_edges[year] = edge
        vegetation_area_ha[year] = area_ha
        vegetation_props = {
            "indicator": "MANGROVE_EDGE_PROXY",
            "role": "HISTORICAL_AND_RECENT_SCREENING",
            "year": year,
            "ndvi_threshold": 0.35,
            "scene_count": len(year_rows[year]),
            "season_window": "January-April",
            "source_resolution_m": grid["resolution"],
            "confidence": "LOW",
            "classification": "fixed NDVI vegetation proxy; not a validated mangrove inventory",
        }
        save_polygon(
            output / "mangrove_proxy" / f"{year}_polygon.geojson",
            polygon,
            vegetation_props | {"area_ha": round(area_ha, 2)},
        )
        save_lines(
            output / "mangrove_proxy" / f"{year}_seaward_edge.geojson",
            edge,
            vegetation_props,
        )
        save_polygon(
            web_output / "mangrove_proxy" / f"{year}_polygon.geojson",
            polygon,
            vegetation_props | {"area_ha": round(area_ha, 2)},
        )
        save_lines(
            web_output / "mangrove_proxy" / f"{year}_seaward_edge.geojson",
            edge,
            vegetation_props,
        )

    write_csv(output / "waterline_qa.csv", waterline_qa)
    transects = load_transects(ROOT / args.transects)
    controls_by_plot = load_controls(ROOT / args.controls)
    transect_by_id = {item["transect_id"]: item for item in transects}

    waterline_historical_years = sorted(year for year in waterlines if year <= 2023)
    waterline_recent_years = [year for year in (2023, 2024, 2025, 2026) if year in waterlines]
    vegetation_historical_years = [year for year in years if year <= 2023]
    vegetation_recent_years = [year for year in (2023, 2024, 2025, 2026) if year in vegetation_edges]
    if len(waterline_historical_years) < 3:
        raise RuntimeError(
            f"only {waterline_historical_years} accepted historical WATERLINE years; require at least 3"
        )

    timeseries: list[dict[str, Any]] = []
    positions: dict[tuple[str, str, int], float | None] = {}
    for transect in transects:
        for year, geometry in sorted(waterlines.items()):
            position = position_on_transect(transect, geometry, mode="nearest_reference")
            positions[(transect["transect_id"], "WATERLINE", year)] = position
            timeseries.append(
                {
                    "transect_id": transect["transect_id"],
                    "role": transect.get("role", ""),
                    "plot_id": transect.get("plot_id", ""),
                    "indicator": "WATERLINE",
                    "year": year,
                    "position_m_relative_to_2026_waterline": position,
                    "tide_level_m_msl": float(waterline_rows[year]["tide_level"]),
                    "tide_status": waterline_rows[year]["tide_status"],
                    "confidence": "LOW",
                }
            )
        for year, geometry in sorted(vegetation_edges.items()):
            position = position_on_transect(transect, geometry, mode="seaward_most")
            positions[(transect["transect_id"], "MANGROVE_EDGE_PROXY", year)] = position
            timeseries.append(
                {
                    "transect_id": transect["transect_id"],
                    "role": transect.get("role", ""),
                    "plot_id": transect.get("plot_id", ""),
                    "indicator": "MANGROVE_EDGE_PROXY",
                    "year": year,
                    "position_m_relative_to_2026_waterline": position,
                    "tide_level_m_msl": None,
                    "tide_status": "not_applicable_to_same_season_ndvi_proxy",
                    "confidence": "LOW",
                }
            )
    write_csv(output / "indicator_timeseries.csv", timeseries)

    metric_rows: list[dict[str, Any]] = []
    metric_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for transect in transects:
        if transect.get("role") != "TREATMENT":
            continue
        for indicator, historical_years, recent_years in (
            ("WATERLINE", waterline_historical_years, waterline_recent_years),
            ("MANGROVE_EDGE_PROXY", vegetation_historical_years, vegetation_recent_years),
        ):
            values = {
                year: positions.get((transect["transect_id"], indicator, year))
                for year in sorted(set(historical_years + recent_years))
            }
            historical = period_metrics(values, historical_years)
            recent = period_metrics(values, recent_years)
            row = {
                "transect_id": transect["transect_id"],
                "role": transect.get("role", ""),
                "plot_id": transect.get("plot_id", ""),
                "indicator": indicator,
                **period_columns("historical", historical),
                **period_columns("recent", recent),
                "lrr_change_recent_minus_historical_m_per_year": (
                    None
                    if historical["lrr_m_per_year"] is None or recent["lrr_m_per_year"] is None
                    else round(recent["lrr_m_per_year"] - historical["lrr_m_per_year"], 2)
                ),
                "confidence": "LOW",
            }
            metric_rows.append(row)
            metric_lookup[(transect["transect_id"], indicator)] = row
    write_csv(output / "period_transect_metrics.csv", metric_rows)
    add_geometry_output(output / "treatment_transects_periods.geojson", transects, metric_lookup)
    add_geometry_output(web_output / "treatment_transects_periods.geojson", transects, metric_lookup)

    aggregate: dict[str, Any] = {}
    for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
        subset = [row for row in metric_rows if row["indicator"] == indicator]
        aggregate[indicator] = {
            "historical": aggregate_period(subset, "historical"),
            "recent": aggregate_period(subset, "recent"),
        }

    per_plot: list[dict[str, Any]] = []
    for plot in plots:
        plot_id = plot["plot_id"]
        treatment_ids = [
            item["transect_id"]
            for item in transects
            if item.get("role") == "TREATMENT" and item.get("plot_id") == plot_id
        ]
        control_ids = controls_by_plot.get(plot_id, [])
        plot_result: dict[str, Any] = {
            "plot_id": plot_id,
            "treatment_transect_count": len(treatment_ids),
            "candidate_control_count": len(control_ids),
        }
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY"):
            treatment_rows = [metric_lookup[(identifier, indicator)] for identifier in treatment_ids if (identifier, indicator) in metric_lookup]
            control_metrics: list[dict[str, Any]] = []
            historical_years = waterline_historical_years if indicator == "WATERLINE" else vegetation_historical_years
            recent_years = waterline_recent_years if indicator == "WATERLINE" else vegetation_recent_years
            for identifier in control_ids:
                transect = transect_by_id.get(identifier)
                if transect is None:
                    continue
                values = {
                    year: positions.get((identifier, indicator, year))
                    for year in sorted(set(historical_years + recent_years))
                }
                control_metrics.append(
                    {
                        "historical": period_metrics(values, historical_years),
                        "recent": period_metrics(values, recent_years),
                    }
                )
            treatment_historical_lrr = median_or_none(row["historical_lrr_m_per_year"] for row in treatment_rows)
            treatment_recent_lrr = median_or_none(row["recent_lrr_m_per_year"] for row in treatment_rows)
            control_historical_lrr = median_or_none(item["historical"]["lrr_m_per_year"] for item in control_metrics)
            control_recent_lrr = median_or_none(item["recent"]["lrr_m_per_year"] for item in control_metrics)
            historical_difference = (
                None
                if treatment_historical_lrr is None or control_historical_lrr is None
                else round(treatment_historical_lrr - control_historical_lrr, 2)
            )
            recent_difference = (
                None
                if treatment_recent_lrr is None or control_recent_lrr is None
                else round(treatment_recent_lrr - control_recent_lrr, 2)
            )
            plot_result[indicator.lower()] = {
                "historical_median_lrr_m_per_year": treatment_historical_lrr,
                "recent_median_lrr_m_per_year": treatment_recent_lrr,
                "trend_change_recent_minus_historical_m_per_year": (
                    None
                    if treatment_historical_lrr is None or treatment_recent_lrr is None
                    else round(treatment_recent_lrr - treatment_historical_lrr, 2)
                ),
                "candidate_control_historical_median_lrr_m_per_year": control_historical_lrr,
                "candidate_control_recent_median_lrr_m_per_year": control_recent_lrr,
                "historical_treatment_minus_control_lrr_m_per_year": historical_difference,
                "recent_treatment_minus_control_lrr_m_per_year": recent_difference,
                "difference_in_differences_screening_m_per_year": (
                    None
                    if historical_difference is None or recent_difference is None
                    else round(recent_difference - historical_difference, 2)
                ),
                "historical_class_counts": dict(
                    Counter(row["historical_classification"] for row in treatment_rows)
                ),
                "recent_class_counts": dict(
                    Counter(row["recent_classification"] for row in treatment_rows)
                ),
                "confidence": "LOW",
            }
        per_plot.append(plot_result)

    preplanting_answer = interpret_preplanting(
        aggregate["WATERLINE"]["historical"],
        aggregate["WATERLINE"]["recent"],
    )
    accepted_levels = [float(row["tide_level"]) for row in waterline_rows.values()]
    target_tide = float(current_summary["waterline_scene_selection"]["target_tide_m_msl"])
    summary = {
        "title": "Samut Songkhram pre-planting and recent coastal screening",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "TIDE_AWARE_PREPLANTING_CONTEXT",
        "erosion_effect_conclusion": "NOT_DEMONSTRATED",
        "years": years,
        "periods": {
            "historical_preplanting": {
                "waterline_years": waterline_historical_years,
                "mangrove_edge_proxy_years": vegetation_historical_years,
                "label_th": f"ก่อนช่วงดำเนินการ {waterline_historical_years[0]}–2023",
            },
            "recent_monitoring": {
                "waterline_years": waterline_recent_years,
                "mangrove_edge_proxy_years": vegetation_recent_years,
                "label_th": "ช่วงติดตาม 2023–2026",
            },
            "intervention_note": (
                "ใช้ปี 2024 เป็นช่วงดำเนินการที่กำกวม เพราะยังไม่มีวันปลูกและวันปลูกซ่อมรายแปลงที่ยืนยัน"
            ),
        },
        "scene_selection": {
            "current_target_tide_m_msl": target_tide,
            "maximum_historical_delta_from_target_m": args.max_historical_tide_delta_m,
            "accepted_waterline_years": sorted(waterline_rows),
            "visual_context_only_years": sorted(set(years).difference(waterline_rows)),
            "accepted_tide_spread_m": round(max(accepted_levels) - min(accepted_levels), 4),
            "display_scenes": display_scenes,
            "audit_csv": "data/processed/project_preplanting_history/scene_selection_audit.csv",
        },
        "answer_to_preplanting_question": preplanting_answer,
        "indicators": {
            "waterline": {
                "role": "SUPPORTING_ONLY",
                "historical_years": waterline_historical_years,
                "recent_years": waterline_recent_years,
                **aggregate["WATERLINE"],
            },
            "mangrove_edge_proxy": {
                "role": "PRIMARY_SCREENING",
                "historical_years": vegetation_historical_years,
                "recent_years": vegetation_recent_years,
                "area_ha_by_year": {str(year): round(vegetation_area_ha[year], 2) for year in years},
                **aggregate["MANGROVE_EDGE_PROXY"],
            },
        },
        "transects": {
            "treatment_count": sum(item.get("role") == "TREATMENT" for item in transects),
            "reference_geometry": str(args.transects),
            "position_convention": "metres relative to the 2026 accepted waterline; positive is seaward",
            "screening_threshold_m": POSITIONAL_SCREENING_THRESHOLD_M,
        },
        "controls": {
            "source": str(args.controls),
            "status": "CANDIDATE_UNVERIFIED",
            "scientific_limit": (
                "Trend comparisons with candidate controls remain screening only until structures, dredging, reclamation, other planting history and field geomorphology are verified."
            ),
        },
        "per_plot": per_plot,
        "allowed_claim_th": (
            "เปรียบเทียบได้ว่าก่อนปี 2023 มีสัญญาณการถอยร่นจากภาพมากหรือน้อยกว่าช่วง 2023–2026 "
            "แต่ยังสรุปไม่ได้ว่าความแตกต่างเกิดจากการปลูกป่าชายเลน"
        ),
        "limitations": [
            "ระดับน้ำย้อนหลังจาก ThailandTideTables เป็นค่าประมาณระหว่างจุดน้ำขึ้นลงจากแหล่งทุติยภูมิ ไม่ใช่ระดับน้ำที่วัดหน้าแปลง",
            "การเลือกภาพตามระดับน้ำช่วยลดความต่าง แต่ไม่ใช่การปรับ waterline ทุกปีให้เป็น datum แนวราบเดียวกัน",
            "Sentinel-2 วิเคราะห์บนกริด 20 เมตร; การเปลี่ยนแปลงภายใน ±20 เมตรไม่ควรตีความทิศทาง",
            "MANGROVE_EDGE_PROXY เป็นขอบพืชจาก NDVI ไม่ใช่ขอบป่าชายเลนที่ตรวจยืนยันด้วยโดรนหรือ confusion matrix",
            "วันปลูกและวันปลูกซ่อมรายแปลงยังไม่ได้รับการยืนยัน",
            "candidate controls ยังไม่ได้ตรวจโครงสร้างชายฝั่ง การขุดลอก การถม และประวัติปลูก",
            "ผลต่างของแนวโน้มก่อนและหลังไม่ใช่หลักฐานเชิงเหตุผลว่าการปลูกลดการกัดเซาะ",
        ],
        "source_data": {
            "scene_catalog": str(args.catalog),
            "current_tide_aware_summary": str(args.current_summary),
            "plots": str(args.plots),
            "transects": str(args.transects),
            "candidate_controls": str(args.controls),
        },
    }
    write_json(output / "summary.json", summary)
    write_json(web_output / "summary.json", summary)
    write_csv(output / "per_plot_period_comparison.csv", [
        {
            "plot_id": item["plot_id"],
            "indicator": indicator,
            **item[indicator.lower()],
        }
        for item in per_plot
        for indicator in ("WATERLINE", "MANGROVE_EDGE_PROXY")
        if indicator.lower() in item
    ])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
