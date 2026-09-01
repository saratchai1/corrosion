#!/usr/bin/env python3
"""Build plot-level before/after indicators for the 2024 planting project.

This analysis intentionally separates spectral evidence from causal claims.
Sentinel-2 plot metrics can show greenness and wetness changes, but they cannot
by themselves prove reduced coastal erosion while tide and planting dates are
unverified.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from build_coastal_change_mvp import (
    build_composite,
    load_json,
    row_coverage,
    save_preview,
    write_composite,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
CRS_WEB = "EPSG:4326"
CRS_ANALYSIS = "EPSG:32647"
TO_UTM = Transformer.from_crs(CRS_WEB, CRS_ANALYSIS, always_xy=True)
TO_WEB = Transformer.from_crs(CRS_ANALYSIS, CRS_WEB, always_xy=True)
DEFAULT_YEARS = [2023, 2024, 2025, 2026]
VEGETATION_NDVI_THRESHOLD = 0.35
STRONG_VEGETATION_NDVI_THRESHOLD = 0.50
WATER_MNDWI_THRESHOLD = 0.0


def finite_ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.divide(
        a,
        b,
        out=np.full_like(a, np.nan, dtype="float32"),
        where=np.isfinite(a) & np.isfinite(b) & (np.abs(b) > 1e-6),
    )


def load_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def scene_rows(
    catalog: list[dict[str, str]], year: int
) -> list[dict[str, str]]:
    rows = []
    for row in catalog:
        if row.get("dataset") != "sentinel2" or not row.get("local_path"):
            continue
        if not row.get("acquisition_datetime_utc", "").startswith(str(year)):
            continue
        month = int(row["acquisition_datetime_utc"][5:7])
        if month not in {1, 2, 3, 4} or row_coverage(row) < 0.95:
            continue
        paths = [ROOT / value for value in row["local_path"].split(";")]
        if paths and all(path.exists() for path in paths):
            rows.append(row)
    rows.sort(key=lambda row: row["acquisition_datetime_utc"])
    return rows


def load_plots(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    collection = load_json(path)
    records = []
    for feature in collection["features"]:
        geometry_web = shape(feature["geometry"])
        geometry_utm = transform(TO_UTM.transform, geometry_web)
        records.append(
            {
                "properties": dict(feature["properties"]),
                "geometry_web": geometry_web,
                "geometry_utm": geometry_utm,
            }
        )
    if len(records) != 9:
        raise ValueError(f"expected 9 Samut Songkhram plots, found {len(records)}")
    return collection, records


def percentile(values: np.ndarray, value: float) -> float | None:
    return float(np.percentile(values, value)) if values.size else None


def round_value(value: float | None, digits: int = 5) -> float | None:
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def statistics_for_mask(
    ndvi: np.ndarray,
    mndwi: np.ndarray,
    valid: np.ndarray,
    mask: np.ndarray,
) -> dict[str, Any]:
    inside = mask & valid & np.isfinite(ndvi) & np.isfinite(mndwi)
    values_ndvi = ndvi[inside]
    values_mndwi = mndwi[inside]
    total_pixels = int(np.count_nonzero(mask))
    valid_pixels = int(values_ndvi.size)
    return {
        "total_pixel_count": total_pixels,
        "valid_pixel_count": valid_pixels,
        "valid_fraction": round(valid_pixels / max(total_pixels, 1), 5),
        "mean_ndvi": round_value(float(np.mean(values_ndvi)) if values_ndvi.size else None),
        "median_ndvi": round_value(percentile(values_ndvi, 50)),
        "ndvi_p25": round_value(percentile(values_ndvi, 25)),
        "ndvi_p75": round_value(percentile(values_ndvi, 75)),
        "vegetation_fraction_ndvi_gte_0_35": round_value(
            float(np.mean(values_ndvi >= VEGETATION_NDVI_THRESHOLD))
            if values_ndvi.size
            else None
        ),
        "strong_vegetation_fraction_ndvi_gte_0_50": round_value(
            float(np.mean(values_ndvi >= STRONG_VEGETATION_NDVI_THRESHOLD))
            if values_ndvi.size
            else None
        ),
        "mean_mndwi": round_value(float(np.mean(values_mndwi)) if values_mndwi.size else None),
        "median_mndwi": round_value(percentile(values_mndwi, 50)),
        "water_fraction_mndwi_gt_0": round_value(
            float(np.mean(values_mndwi > WATER_MNDWI_THRESHOLD))
            if values_mndwi.size
            else None
        ),
        "pixel_confidence": "INSUFFICIENT" if valid_pixels < 9 else "LOW",
    }


def mask_for_geometry(geometry: Any, grid: dict[str, Any]) -> np.ndarray:
    return geometry_mask(
        [mapping(geometry)],
        out_shape=(grid["height"], grid["width"]),
        transform=grid["transform"],
        invert=True,
    )


def metric_delta(
    rows_by_year: dict[int, dict[str, Any]], metric: str, start: int, end: int
) -> float | None:
    first = rows_by_year.get(start, {}).get(metric)
    last = rows_by_year.get(end, {}).get(metric)
    if first is None or last is None:
        return None
    return round(float(last) - float(first), 5)


def post_boundary_evidence(
    plots: list[dict[str, Any]], output: Path
) -> dict[str, Any]:
    """Summarize the existing 2025-2026 boundary transects crossing STC plots."""
    transect_path = ROOT / "data/processed/statistics/transect_summary.geojson"
    yearly_path = ROOT / "data/processed/statistics/transect_yearly.csv"
    if not transect_path.exists() or not yearly_path.exists():
        return {"status": "unavailable", "reason": "province transect products missing"}
    positions: dict[tuple[str, int], float | None] = {}
    with yearly_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get("position_m", "")
            positions[(row["transect_id"], int(row["year"]))] = (
                None if value == "" else float(value)
            )
    stc_plots = {
        item["properties"]["plot_id"]: item["geometry_utm"]
        for item in plots
        if item["properties"]["plot_id"].endswith("-STC")
    }
    rows = []
    for feature in load_json(transect_path)["features"]:
        transect_id = feature["properties"]["transect_id"]
        geometry = transform(TO_UTM.transform, shape(feature["geometry"]))
        intersections = [
            (geometry.intersection(plot).length, plot_id)
            for plot_id, plot in stc_plots.items()
            if geometry.intersects(plot)
        ]
        if not intersections:
            continue
        plot_id = max(intersections)[1]
        first = positions.get((transect_id, 2025))
        last = positions.get((transect_id, 2026))
        movement = None if first is None or last is None else round(last - first, 2)
        rows.append(
            {
                "transect_id": transect_id,
                "plot_id": plot_id,
                "movement_2025_2026_m": movement,
                "class_20m": (
                    "insufficient_data"
                    if movement is None
                    else (
                        "apparent_inland"
                        if movement < -20
                        else ("apparent_seaward" if movement > 20 else "within_20m")
                    )
                ),
                "tide_status": "unverified",
                "confidence": "LOW",
            }
        )
    if rows:
        with (output / "post_boundary_transects.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    values = [
        float(row["movement_2025_2026_m"])
        for row in rows
        if row["movement_2025_2026_m"] is not None
    ]
    per_plot = []
    for plot_id in stc_plots:
        plot_values = [
            float(row["movement_2025_2026_m"])
            for row in rows
            if row["plot_id"] == plot_id
            and row["movement_2025_2026_m"] is not None
        ]
        per_plot.append(
            {
                "plot_id": plot_id,
                "transect_count": len(plot_values),
                "median_movement_m": round(float(np.median(plot_values)), 2)
                if plot_values
                else None,
                "mean_movement_m": round(float(np.mean(plot_values)), 2)
                if plot_values
                else None,
                "apparent_inland_count": sum(value < -20 for value in plot_values),
                "within_20m_count": sum(abs(value) <= 20 for value in plot_values),
                "apparent_seaward_count": sum(value > 20 for value in plot_values),
            }
        )
    return {
        "status": "available_for_91_to_98_STC_only",
        "feature": "image-derived water-land boundary; not a surveyed or tide-normalized shoreline",
        "period": "2025-2026",
        "transect_count": len(values),
        "median_movement_m": round(float(np.median(values)), 2) if values else None,
        "mean_movement_m": round(float(np.mean(values)), 2) if values else None,
        "apparent_inland_count": sum(value < -20 for value in values),
        "within_20m_count": sum(abs(value) <= 20 for value in values),
        "apparent_seaward_count": sum(value > 20 for value in values),
        "per_plot": per_plot,
        "unavailable_plot_ids": ["87-VSD"],
        "unavailable_reason": "87-VSD lies outside the provisional province-wide transect AOI; plot spectral metrics are available",
        "tide_status": "unverified",
        "confidence": "LOW",
    }


def pixel_polygons(
    mask: np.ndarray, grid: dict[str, Any], clip_geometry: Any
) -> Any:
    polygons = [
        shape(geometry)
        for geometry, value in shapes(
            mask.astype("uint8"),
            mask=mask,
            transform=grid["transform"],
            connectivity=8,
        )
        if value == 1
    ]
    return unary_union(polygons).intersection(clip_geometry).buffer(0) if polygons else clip_geometry.buffer(0).difference(clip_geometry)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plots", default="data/aoi/samut_songkhram_project_plots.geojson"
    )
    parser.add_argument(
        "--catalog",
        default="data/catalog/project_samut_songkhram_sentinel2_scenes.csv",
    )
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument(
        "--output", default="data/processed/project_impact"
    )
    args = parser.parse_args()
    years = sorted({int(value) for value in args.years.split(",") if value.strip()})
    if years != DEFAULT_YEARS:
        raise ValueError(f"project assessment currently requires {DEFAULT_YEARS}")

    plot_collection, plots = load_plots(ROOT / args.plots)
    catalog = load_catalog(ROOT / args.catalog)
    output = ROOT / args.output
    (output / "optical").mkdir(parents=True, exist_ok=True)
    (output / "imagery").mkdir(parents=True, exist_ok=True)
    (output / "vegetation").mkdir(parents=True, exist_ok=True)

    plot_union = unary_union([item["geometry_utm"] for item in plots]).buffer(0)
    per_plot_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []
    arrays: dict[int, dict[str, Any]] = {}
    grid_signature = None

    for year in years:
        rows = scene_rows(catalog, year)
        if len(rows) < 2:
            raise RuntimeError(f"{year} has only {len(rows)} usable January-April scenes")
        composite, valid_count, grid = build_composite(rows, "sentinel2")
        signature = (
            str(grid["crs"]),
            tuple(grid["transform"]),
            grid["height"],
            grid["width"],
        )
        if grid_signature is None:
            grid_signature = signature
        elif signature != grid_signature:
            raise RuntimeError("project composites do not share one aligned grid")
        valid = valid_count > 0
        red, green, nir, swir1 = composite[2], composite[1], composite[3], composite[4]
        ndvi = finite_ratio(nir - red, nir + red)
        mndwi = finite_ratio(green - swir1, green + swir1)
        dates = [row["acquisition_datetime_utc"][:10] for row in rows]
        sensors = sorted({row["sensor"] for row in rows})
        write_composite(
            output / "optical" / f"{year}_composite.tif",
            composite,
            grid,
            {
                "project": "Samut Songkhram 2024 planting assessment",
                "target_year": year,
                "actual_year": year,
                "scene_dates": ",".join(dates),
                "sensor": ", ".join(sensors),
                "season_window": "January-April",
                "tide_status": "unverified",
            },
        )
        save_preview(output / "imagery" / f"{year}.webp", composite, valid)
        arrays[year] = {
            "ndvi": ndvi,
            "mndwi": mndwi,
            "valid": valid,
            "grid": grid,
            "dates": dates,
            "sensors": sensors,
        }

        aggregate_mask = mask_for_geometry(plot_union, grid)
        aggregate = statistics_for_mask(ndvi, mndwi, valid, aggregate_mask)
        aggregate.update(
            {
                "year": year,
                "period_role": "pre" if year == 2023 else ("intervention_ambiguous" if year == 2024 else "post"),
                "scene_dates": ";".join(dates),
                "scene_count": len(rows),
                "sensor": ";".join(sensors),
            }
        )
        aggregate_rows.append(aggregate)

        vegetation_features = []
        for item in plots:
            props = item["properties"]
            plot_mask = mask_for_geometry(item["geometry_utm"], grid)
            stats = statistics_for_mask(ndvi, mndwi, valid, plot_mask)
            row = {
                "plot_id": props["plot_id"],
                "province": props["province"],
                "official_participating_area_rai": props[
                    "official_participating_area_rai"
                ],
                "geometry_area_rai": props["geometry_area_rai"],
                "year": year,
                "period_role": aggregate["period_role"],
                "scene_dates": aggregate["scene_dates"],
                **stats,
            }
            per_plot_rows.append(row)
            vegetation = pixel_polygons(
                valid & (ndvi >= VEGETATION_NDVI_THRESHOLD) & plot_mask,
                grid,
                item["geometry_utm"],
            )
            vegetation_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "plot_id": props["plot_id"],
                        "year": year,
                        "ndvi_threshold": VEGETATION_NDVI_THRESHOLD,
                        "classification": "Sentinel-2 vegetation proxy, not verified mangrove canopy",
                        "tide_status": "unverified",
                    },
                    "geometry": mapping(transform(TO_WEB.transform, vegetation)),
                }
            )
        write_json(
            output / "vegetation" / f"{year}_plot_vegetation_proxy.geojson",
            {"type": "FeatureCollection", "features": vegetation_features},
        )

    # Local observational controls: 200-1,200 m from every project polygon.
    # These are context,
    # not randomized or field-verified controls.
    grid = arrays[2023]["grid"]
    control_geometry = plot_union.buffer(1200).difference(plot_union.buffer(200)).buffer(0)
    impact_mask = mask_for_geometry(plot_union, grid)
    control_mask = mask_for_geometry(control_geometry, grid)
    common_valid = np.logical_and.reduce([arrays[year]["valid"] for year in years])
    baseline_ndvi = arrays[2023]["ndvi"]
    baseline_mndwi = arrays[2023]["mndwi"]
    baseline_impact = impact_mask & common_valid & np.isfinite(baseline_ndvi) & np.isfinite(baseline_mndwi)
    impact_ndvi_values = baseline_ndvi[baseline_impact]
    impact_mndwi_values = baseline_mndwi[baseline_impact]
    if not impact_ndvi_values.size or not impact_mndwi_values.size:
        raise RuntimeError("no common valid baseline pixels inside project plots")
    ndvi_low, ndvi_high = np.percentile(impact_ndvi_values, [5, 95])
    mndwi_low, mndwi_high = np.percentile(impact_mndwi_values, [5, 95])
    matched_control = (
        control_mask
        & common_valid
        & np.isfinite(baseline_ndvi)
        & np.isfinite(baseline_mndwi)
        & (baseline_ndvi >= ndvi_low)
        & (baseline_ndvi <= ndvi_high)
        & (baseline_mndwi >= mndwi_low)
        & (baseline_mndwi <= mndwi_high)
    )
    comparison_rows = []
    for year in years:
        impact = statistics_for_mask(
            arrays[year]["ndvi"], arrays[year]["mndwi"], common_valid, baseline_impact
        )
        control = statistics_for_mask(
            arrays[year]["ndvi"], arrays[year]["mndwi"], common_valid, matched_control
        )
        comparison_rows.append(
            {
                "year": year,
                "period_role": "pre" if year == 2023 else ("intervention_ambiguous" if year == 2024 else "post"),
                "impact_mean_ndvi": impact["mean_ndvi"],
                "control_mean_ndvi": control["mean_ndvi"],
                "impact_vegetation_fraction": impact[
                    "vegetation_fraction_ndvi_gte_0_35"
                ],
                "control_vegetation_fraction": control[
                    "vegetation_fraction_ndvi_gte_0_35"
                ],
                "impact_water_fraction": impact["water_fraction_mndwi_gt_0"],
                "control_water_fraction": control["water_fraction_mndwi_gt_0"],
                "impact_pixel_count": impact["valid_pixel_count"],
                "matched_control_pixel_count": control["valid_pixel_count"],
            }
        )

    comparison_by_year = {row["year"]: row for row in comparison_rows}
    baseline = comparison_by_year[2023]
    did = []
    for year in [2025, 2026]:
        post = comparison_by_year[year]
        did.append(
            {
                "post_year": year,
                "ndvi_difference_in_differences": round(
                    (post["impact_mean_ndvi"] - baseline["impact_mean_ndvi"])
                    - (post["control_mean_ndvi"] - baseline["control_mean_ndvi"]),
                    5,
                ),
                "vegetation_fraction_difference_in_differences": round(
                    (post["impact_vegetation_fraction"] - baseline["impact_vegetation_fraction"])
                    - (post["control_vegetation_fraction"] - baseline["control_vegetation_fraction"]),
                    5,
                ),
                "water_fraction_difference_in_differences": round(
                    (post["impact_water_fraction"] - baseline["impact_water_fraction"])
                    - (post["control_water_fraction"] - baseline["control_water_fraction"]),
                    5,
                ),
            }
        )

    rows_by_plot: dict[str, dict[int, dict[str, Any]]] = {}
    for row in per_plot_rows:
        rows_by_plot.setdefault(row["plot_id"], {})[int(row["year"])] = row
    plot_changes = []
    for plot_id, rows_by_year in rows_by_plot.items():
        plot_changes.append(
            {
                "plot_id": plot_id,
                "valid_pixels_2023": rows_by_year[2023]["valid_pixel_count"],
                "ndvi_change_2023_2025": metric_delta(rows_by_year, "mean_ndvi", 2023, 2025),
                "ndvi_change_2023_2026": metric_delta(rows_by_year, "mean_ndvi", 2023, 2026),
                "vegetation_fraction_change_2023_2025": metric_delta(
                    rows_by_year, "vegetation_fraction_ndvi_gte_0_35", 2023, 2025
                ),
                "vegetation_fraction_change_2023_2026": metric_delta(
                    rows_by_year, "vegetation_fraction_ndvi_gte_0_35", 2023, 2026
                ),
                "water_fraction_change_2023_2025": metric_delta(
                    rows_by_year, "water_fraction_mndwi_gt_0", 2023, 2025
                ),
                "water_fraction_change_2023_2026": metric_delta(
                    rows_by_year, "water_fraction_mndwi_gt_0", 2023, 2026
                ),
                "confidence": "INSUFFICIENT" if rows_by_year[2023]["valid_pixel_count"] < 9 else "LOW",
            }
        )

    def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output / "plot_yearly_metrics.csv", per_plot_rows)
    write_csv(output / "project_yearly_metrics.csv", aggregate_rows)
    write_csv(output / "matched_control_comparison.csv", comparison_rows)
    write_csv(output / "plot_change_summary.csv", plot_changes)
    boundary_evidence = post_boundary_evidence(plots, output)
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary = {
        "title": "Samut Songkhram 2024 mangrove planting exploratory impact indicators",
        "generated_at_utc": generated,
        "plot_count": 9,
        "plot_ids": [item["properties"]["plot_id"] for item in plots],
        "official_participating_area_rai": plot_collection["metadata"][
            "official_participating_area_rai"
        ],
        "years": years,
        "design": {
            "pre": [2023],
            "intervention_ambiguous": [2024],
            "post": [2025, 2026],
            "season_window": "January-April",
            "matched_control": "200-1200 m context ring filtered to the central 90% of project baseline NDVI and MNDWI",
        },
        "project_yearly_metrics": aggregate_rows,
        "matched_control_comparison": comparison_rows,
        "difference_in_differences": did,
        "plot_change_summary": plot_changes,
        "post_boundary_evidence": boundary_evidence,
        "erosion_effect_conclusion": "NOT_DEMONSTRATED",
        "conclusion_th": "ข้อมูลนี้ยังไม่พิสูจน์ว่าการปลูกปี 2024 ลดการกัดเซาะชายฝั่ง; เป็นเพียงสัญญาณพืชพรรณและสัดส่วนผิวน้ำภายในแปลงจาก Sentinel-2",
        "confidence": "LOW",
        "limitations": [
            "ไม่มีวันปลูกที่ยืนยัน จึงถือปี 2024 เป็นช่วงดำเนินการที่กำกวม",
            "tide_status=unverified; สัดส่วนผิวน้ำและขอบเขตน้ำ–แผ่นดินอาจเปลี่ยนตามน้ำขึ้นลง",
            "ไม่มีการวัดคลื่น ตะกอน ระดับพื้นดิน หรืออัตรารอดตายภาคสนาม",
            "Sentinel-2 วิเคราะห์ที่ 20 เมตร; กล้าไม้เล็กและแปลงแคบอาจเล็กกว่าพิกเซล",
            "พื้นที่เปรียบเทียบเป็น observational matched context ไม่ใช่พื้นที่ควบคุมที่สุ่มหรือยืนยันภาคสนาม",
            "NDVI proxy ไม่ใช่การจำแนกป่าชายเลนที่ผ่าน confusion-matrix validation",
        ],
        "source_data": {
            "plots": args.plots,
            "catalog": args.catalog,
            "tide_status": "unverified",
        },
    }
    write_json(output / "summary.json", summary)

    web_project = ROOT / "web/public/data/project"
    web_project.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / args.plots, web_project / "plots.geojson")
    shutil.copy2(output / "summary.json", web_project / "summary.json")
    shutil.copy2(output / "plot_change_summary.csv", web_project / "plot_change_summary.csv")
    if (output / "post_boundary_transects.csv").exists():
        shutil.copy2(
            output / "post_boundary_transects.csv",
            web_project / "post_boundary_transects.csv",
        )
    for year in years:
        shutil.copy2(output / "imagery" / f"{year}.webp", web_project / f"{year}.webp")
        shutil.copy2(
            output / "vegetation" / f"{year}_plot_vegetation_proxy.geojson",
            web_project / f"{year}_plot_vegetation_proxy.geojson",
        )
    print(
        f"built plot impact indicators for {len(plots)} plots and {len(years)} years "
        f"under {output.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
