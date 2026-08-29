#!/usr/bin/env python3
"""Aggregate multi-date water masks into annual and epoch consensus products.

Input date directories must contain ``water_mask.tif`` encoded as:
0 valid non-water, 1 valid water, 255 invalid/no-data. All masks must share one
projected grid. The script produces frequency, consensus and uncertainty COGs,
vector polygons, an epoch change map, and per-plot summaries.

This is a screening product. It explicitly does not convert water-edge change to
an erosion rate while tide remains unverified.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask, shapes
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

NODATA_CLASS = 255
FLOAT_NODATA = -9999.0


@dataclass(frozen=True)
class MaskRecord:
    acquisition_date: date
    path: Path
    summary: dict[str, object]


@dataclass
class Aggregate:
    label: str
    records: list[MaskRecord]
    water_count: np.ndarray
    valid_count: np.ndarray
    frequency: np.ndarray
    consensus: np.ndarray
    uncertainty: np.ndarray
    min_observations: int


def parse_date_dir(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.name)
    except ValueError:
        return None


def load_records(root: Path) -> list[MaskRecord]:
    records: list[MaskRecord] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        acquisition_date = parse_date_dir(directory)
        if acquisition_date is None:
            continue
        mask_path = directory / "water_mask.tif"
        summary_path = directory / "summary.json"
        if not mask_path.exists() or not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        records.append(MaskRecord(acquisition_date, mask_path, summary))
    if not records:
        raise ValueError(
            f"No date directories with water_mask.tif + summary.json: {root}"
        )
    return records


def assert_same_grid(
    records: Iterable[MaskRecord],
) -> tuple[dict, rasterio.Affine, CRS, int, int]:
    records = list(records)
    with rasterio.open(records[0].path) as src:
        profile = src.profile.copy()
        transform_grid = src.transform
        crs = CRS.from_user_input(src.crs)
        width, height = src.width, src.height
    if not crs.is_projected:
        raise ValueError(f"Consensus area calculation requires projected CRS, got {crs}")
    for record in records[1:]:
        with rasterio.open(record.path) as src:
            if (
                src.width != width
                or src.height != height
                or src.transform != transform_grid
                or CRS.from_user_input(src.crs) != crs
            ):
                raise ValueError(f"Grid mismatch: {record.path}")
    return profile, transform_grid, crs, width, height


def read_mask(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        arr = src.read(1)
    unexpected = np.setdiff1d(
        np.unique(arr), np.array([0, 1, NODATA_CLASS], dtype=arr.dtype)
    )
    if unexpected.size:
        raise ValueError(
            f"Unexpected water mask classes {unexpected.tolist()} in {path}"
        )
    return arr


def aggregate_records(
    label: str,
    records: list[MaskRecord],
    *,
    threshold: float,
    min_fraction_valid: float,
) -> Aggregate:
    if not records:
        raise ValueError(f"No records for aggregate {label}")
    stack = np.stack([read_mask(record.path) for record in records])
    valid = stack != NODATA_CLASS
    water = stack == 1
    valid_count = valid.sum(axis=0).astype("uint16")
    water_count = water.sum(axis=0).astype("uint16")
    frequency = np.full(valid_count.shape, FLOAT_NODATA, dtype="float32")
    np.divide(water_count, valid_count, out=frequency, where=valid_count > 0)

    min_observations = max(1, int(math.ceil(len(records) * min_fraction_valid)))
    enough = valid_count >= min_observations
    consensus = np.full(valid_count.shape, NODATA_CLASS, dtype="uint8")
    consensus[enough] = 0
    consensus[enough & (frequency >= threshold)] = 1

    uncertainty = np.full(valid_count.shape, FLOAT_NODATA, dtype="float32")
    # Bernoulli variance scaled to 0..1. 0 is stable; 1 is maximally variable.
    uncertainty[enough] = 4.0 * frequency[enough] * (1.0 - frequency[enough])
    return Aggregate(
        label=label,
        records=records,
        water_count=water_count,
        valid_count=valid_count,
        frequency=frequency,
        consensus=consensus,
        uncertainty=uncertainty,
        min_observations=min_observations,
    )


def write_cog(
    path: Path,
    data: np.ndarray,
    reference_profile: dict,
    *,
    dtype: str,
    nodata: int | float,
    tags: dict[str, str],
    overview_resampling: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "COG",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": reference_profile["crs"],
        "transform": reference_profile["transform"],
        "nodata": nodata,
        "compress": "DEFLATE",
        "blocksize": 512,
        "overview_resampling": overview_resampling,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)
        dst.update_tags(**tags)


def polygon_features(
    mask: np.ndarray,
    transform_grid: rasterio.Affine,
    crs: CRS,
    *,
    min_area_m2: float,
    properties: dict[str, object],
) -> list[dict]:
    polygons = []
    for geom, value in shapes(
        mask.astype("uint8"), mask=mask, transform=transform_grid
    ):
        if value != 1:
            continue
        poly = shape(geom)
        if poly.area >= min_area_m2:
            polygons.append(poly)
    merged = unary_union(polygons) if polygons else None
    if merged is None or merged.is_empty:
        return []
    to4326 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    return [
        {
            "type": "Feature",
            "properties": {
                **properties,
                "part": index,
                "area_m2_projected": round(float(poly.area), 2),
            },
            "geometry": mapping(transform(to4326, poly)),
        }
        for index, poly in enumerate(parts, 1)
    ]


def aggregate_summary(
    aggregate: Aggregate, pixel_area_m2: float, threshold: float
) -> dict[str, object]:
    enough = aggregate.consensus != NODATA_CLASS
    water = aggregate.consensus == 1
    variable = enough & (aggregate.frequency > 0) & (aggregate.frequency < 1)
    tide_values = {
        str(record.summary.get("tide_status", "unverified"))
        for record in aggregate.records
    }
    tide_status = tide_values.pop() if len(tide_values) == 1 else "mixed"
    return {
        "label": aggregate.label,
        "acquisition_count": len(aggregate.records),
        "acquisition_dates": [
            record.acquisition_date.isoformat() for record in aggregate.records
        ],
        "min_observations_per_pixel": aggregate.min_observations,
        "consensus_threshold": threshold,
        "classified_area_m2": round(float(enough.sum() * pixel_area_m2), 2),
        "consensus_water_area_m2": round(float(water.sum() * pixel_area_m2), 2),
        "variable_water_area_m2": round(float(variable.sum() * pixel_area_m2), 2),
        "mean_water_frequency": (
            round(float(aggregate.frequency[enough].mean()), 6)
            if enough.any()
            else None
        ),
        "mean_uncertainty": (
            round(float(aggregate.uncertainty[enough].mean()), 6)
            if enough.any()
            else None
        ),
        "tide_status": tide_status,
        "analysis_status": (
            "MULTI_SCENE_SCREENING"
            if tide_status == "verified"
            else "MULTI_SCENE_TIDE_UNVERIFIED_SCREENING"
        ),
    }


def write_aggregate(
    aggregate: Aggregate,
    output_dir: Path,
    reference_profile: dict,
    transform_grid: rasterio.Affine,
    crs: CRS,
    *,
    threshold: float,
    min_area_m2: float,
) -> dict[str, object]:
    pixel_area_m2 = abs(transform_grid.a * transform_grid.e)
    status = aggregate_summary(aggregate, pixel_area_m2, threshold)["analysis_status"]
    tags = {
        "aggregate_label": aggregate.label,
        "acquisition_count": str(len(aggregate.records)),
        "min_observations": str(aggregate.min_observations),
        "consensus_threshold": str(threshold),
        "analysis_status": str(status),
        "class_0": "consensus_non_water",
        "class_1": "consensus_water",
        "class_255": "insufficient_observations",
    }
    write_cog(
        output_dir / "water_frequency.tif",
        aggregate.frequency,
        reference_profile,
        dtype="float32",
        nodata=FLOAT_NODATA,
        tags=tags,
        overview_resampling="average",
    )
    write_cog(
        output_dir / "water_consensus.tif",
        aggregate.consensus,
        reference_profile,
        dtype="uint8",
        nodata=NODATA_CLASS,
        tags=tags,
        overview_resampling="nearest",
    )
    write_cog(
        output_dir / "water_uncertainty.tif",
        aggregate.uncertainty,
        reference_profile,
        dtype="float32",
        nodata=FLOAT_NODATA,
        tags=tags,
        overview_resampling="average",
    )
    features = polygon_features(
        aggregate.consensus == 1,
        transform_grid,
        crs,
        min_area_m2=min_area_m2,
        properties={"aggregate": aggregate.label, "analysis_status": status},
    )
    (output_dir / "water_consensus.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )
    summary = aggregate_summary(aggregate, pixel_area_m2, threshold)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def epoch_change(
    baseline: Aggregate,
    latest: Aggregate,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    valid = (baseline.consensus != NODATA_CLASS) & (
        latest.consensus != NODATA_CLASS
    )
    base_water = baseline.consensus == 1
    latest_water = latest.consensus == 1
    classes = np.full(base_water.shape, NODATA_CLASS, dtype="uint8")
    classes[valid & ~base_water & ~latest_water] = 0
    classes[valid & ~base_water & latest_water] = 1
    classes[valid & base_water & ~latest_water] = 2
    classes[valid & base_water & latest_water] = 3
    masks = {
        "valid": valid,
        "water_gain": valid & ~base_water & latest_water,
        "water_loss": valid & base_water & ~latest_water,
        "stable_water": valid & base_water & latest_water,
        "stable_non_water": valid & ~base_water & ~latest_water,
    }
    return classes, masks


def change_features(
    masks: dict[str, np.ndarray],
    transform_grid: rasterio.Affine,
    crs: CRS,
    min_area_m2: float,
    baseline_label: str,
    latest_label: str,
) -> list[dict]:
    features: list[dict] = []
    for change_type in ("water_gain", "water_loss"):
        features.extend(
            polygon_features(
                masks[change_type],
                transform_grid,
                crs,
                min_area_m2=min_area_m2,
                properties={
                    "change_type": change_type,
                    "baseline": baseline_label,
                    "latest": latest_label,
                    "interpretation": (
                        "candidate land-to-water/inundation/erosion signal"
                        if change_type == "water_gain"
                        else "candidate water-to-land/accretion/drying signal"
                    ),
                    "analysis_status": "MULTI_SCENE_TIDE_UNVERIFIED_SCREENING",
                },
            )
        )
    return features


def load_plot_features(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("type") != "FeatureCollection":
        raise ValueError(f"Plots must be a GeoJSON FeatureCollection: {path}")
    return obj.get("features", [])


def per_plot_summary(
    features: list[dict],
    masks: dict[str, np.ndarray],
    classes: np.ndarray,
    transform_grid: rasterio.Affine,
    crs: CRS,
    pixel_area_m2: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, feature in enumerate(features, 1):
        props = feature.get("properties", {})
        code = props.get("plot_code") or props.get("name") or f"plot-{index}"
        geom = feature.get("geometry")
        if not geom:
            continue
        geom_projected = transform_geom("EPSG:4326", crs.to_string(), geom)
        inside = geometry_mask(
            [geom_projected],
            out_shape=classes.shape,
            transform=transform_grid,
            invert=True,
        )
        valid_inside = inside & masks["valid"]
        plot_pixels = int(inside.sum())
        valid_pixels = int(valid_inside.sum())
        values = {
            name: int((inside & mask).sum()) * pixel_area_m2
            for name, mask in masks.items()
            if name != "valid"
        }
        gain = float(values["water_gain"])
        loss = float(values["water_loss"])
        rows.append(
            {
                "plot_code": code,
                "grid_plot_area_m2": round(plot_pixels * pixel_area_m2, 2),
                "comparable_area_m2": round(valid_pixels * pixel_area_m2, 2),
                "comparable_fraction": (
                    round(valid_pixels / plot_pixels, 6) if plot_pixels else None
                ),
                "candidate_water_gain_m2": round(gain, 2),
                "candidate_water_loss_m2": round(loss, 2),
                "net_candidate_water_gain_m2": round(gain - loss, 2),
                "stable_water_m2": round(float(values["stable_water"]), 2),
                "stable_non_water_m2": round(
                    float(values["stable_non_water"]), 2
                ),
                "screening_flag": (
                    "REVIEW_WATER_GAIN"
                    if gain >= max(1000.0, 0.01 * valid_pixels * pixel_area_m2)
                    else "NO_LARGE_WATER_GAIN_SIGNAL"
                ),
                "analysis_status": "MULTI_SCENE_TIDE_UNVERIFIED_SCREENING",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_years(value: str | None) -> list[int] | None:
    if value is None:
        return None
    years = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    if not years:
        raise argparse.ArgumentTypeError("Year list cannot be empty")
    return years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, required=True, help="Date-level water history root"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plots", type=Path)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--min-valid-fraction", type=float, default=0.5)
    parser.add_argument("--min-area-m2", type=float, default=400.0)
    parser.add_argument("--baseline-years", type=parse_years)
    parser.add_argument("--latest-years", type=parse_years)
    args = parser.parse_args()

    if not 0 < args.threshold < 1:
        raise ValueError("--threshold must be between 0 and 1")
    if not 0 < args.min_valid_fraction <= 1:
        raise ValueError("--min-valid-fraction must be in (0, 1]")

    records = load_records(args.root)
    profile, transform_grid, crs, _, _ = assert_same_grid(records)
    profile["transform"] = transform_grid
    profile["crs"] = crs
    pixel_area_m2 = abs(transform_grid.a * transform_grid.e)

    by_year: dict[int, list[MaskRecord]] = {}
    for record in records:
        by_year.setdefault(record.acquisition_date.year, []).append(record)
    years = sorted(by_year)
    if len(years) < 2:
        raise ValueError("At least two years are required for epoch comparison")

    args.out.mkdir(parents=True, exist_ok=True)
    annual_summaries = []
    for year in years:
        aggregate = aggregate_records(
            str(year),
            by_year[year],
            threshold=args.threshold,
            min_fraction_valid=args.min_valid_fraction,
        )
        annual_summaries.append(
            write_aggregate(
                aggregate,
                args.out / "annual" / str(year),
                profile,
                transform_grid,
                crs,
                threshold=args.threshold,
                min_area_m2=args.min_area_m2,
            )
        )

    baseline_years = args.baseline_years or years[: min(3, len(years) // 2)]
    latest_years = args.latest_years or years[-min(3, len(years) // 2) :]
    if set(baseline_years) & set(latest_years):
        raise ValueError("Baseline and latest year sets must not overlap")
    missing_years = (set(baseline_years) | set(latest_years)) - set(years)
    if missing_years:
        raise ValueError(f"Requested years are unavailable: {sorted(missing_years)}")

    baseline_records = [
        record for year in baseline_years for record in by_year[year]
    ]
    latest_records = [record for year in latest_years for record in by_year[year]]
    baseline_label = f"baseline_{min(baseline_years)}_{max(baseline_years)}"
    latest_label = f"latest_{min(latest_years)}_{max(latest_years)}"
    baseline = aggregate_records(
        baseline_label,
        baseline_records,
        threshold=args.threshold,
        min_fraction_valid=args.min_valid_fraction,
    )
    latest = aggregate_records(
        latest_label,
        latest_records,
        threshold=args.threshold,
        min_fraction_valid=args.min_valid_fraction,
    )
    baseline_summary = write_aggregate(
        baseline,
        args.out / "epochs" / baseline_label,
        profile,
        transform_grid,
        crs,
        threshold=args.threshold,
        min_area_m2=args.min_area_m2,
    )
    latest_summary = write_aggregate(
        latest,
        args.out / "epochs" / latest_label,
        profile,
        transform_grid,
        crs,
        threshold=args.threshold,
        min_area_m2=args.min_area_m2,
    )

    classes, masks = epoch_change(baseline, latest)
    change_dir = args.out / "epoch_change"
    tags = {
        "baseline": baseline_label,
        "latest": latest_label,
        "class_0": "stable_non_water",
        "class_1": "candidate_water_gain",
        "class_2": "candidate_water_loss",
        "class_3": "stable_water",
        "class_255": "insufficient_observations",
        "analysis_status": "MULTI_SCENE_TIDE_UNVERIFIED_SCREENING",
    }
    write_cog(
        change_dir / "water_change.tif",
        classes,
        profile,
        dtype="uint8",
        nodata=NODATA_CLASS,
        tags=tags,
        overview_resampling="nearest",
    )
    features = change_features(
        masks,
        transform_grid,
        crs,
        args.min_area_m2,
        baseline_label,
        latest_label,
    )
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "water_change.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )
    change_summary = {
        "baseline": baseline_summary,
        "latest": latest_summary,
        "comparable_area_m2": round(
            float(masks["valid"].sum() * pixel_area_m2), 2
        ),
        "candidate_water_gain_m2": round(
            float(masks["water_gain"].sum() * pixel_area_m2), 2
        ),
        "candidate_water_loss_m2": round(
            float(masks["water_loss"].sum() * pixel_area_m2), 2
        ),
        "net_candidate_water_gain_m2": round(
            float(
                (masks["water_gain"].sum() - masks["water_loss"].sum())
                * pixel_area_m2
            ),
            2,
        ),
        "stable_water_m2": round(
            float(masks["stable_water"].sum() * pixel_area_m2), 2
        ),
        "stable_non_water_m2": round(
            float(masks["stable_non_water"].sum() * pixel_area_m2), 2
        ),
        "analysis_status": "MULTI_SCENE_TIDE_UNVERIFIED_SCREENING",
        "interpretation": (
            "Multi-date consensus reduces cloud and single-scene noise, but candidate "
            "water-edge change is not an erosion/accretion rate until tide and field "
            "reference uncertainty are controlled."
        ),
    }

    plot_rows: list[dict[str, object]] = []
    if args.plots:
        plot_rows = per_plot_summary(
            load_plot_features(args.plots),
            masks,
            classes,
            transform_grid,
            crs,
            pixel_area_m2,
        )
        write_csv(change_dir / "plot_change_summary.csv", plot_rows)
        (change_dir / "plot_change_summary.json").write_text(
            json.dumps(plot_rows, indent=2), encoding="utf-8"
        )
        change_summary["plots"] = plot_rows

    (change_dir / "summary.json").write_text(
        json.dumps(change_summary, indent=2), encoding="utf-8"
    )
    write_csv(args.out / "annual_summary.csv", annual_summaries)
    (args.out / "summary.json").write_text(
        json.dumps(
            {
                "years": years,
                "annual": annual_summaries,
                "epoch_change": change_summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(change_summary, indent=2))


if __name__ == "__main__":
    main()
