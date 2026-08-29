#!/usr/bin/env python3
"""Cross-check MNDWI water masks against Sentinel-2 SCL class 6.

SCL is not treated as ground truth. The comparison is an independent consistency
check that helps identify dates where the MNDWI classification and the provider's
scene classification disagree unusually strongly.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

NODATA_CLASS = 255
SCL_WATER = 6
SCL_INVALID = {0, 1, 3, 8, 9, 10, 11}


def safe_ratio(num: int, den: int) -> float | None:
    return round(num / den, 6) if den else None


def kappa(tp: int, tn: int, fp: int, fn: int) -> float | None:
    total = tp + tn + fp + fn
    if total == 0:
        return None
    observed = (tp + tn) / total
    m_water = tp + fp
    m_nonwater = tn + fn
    s_water = tp + fn
    s_nonwater = tn + fp
    expected = (m_water * s_water + m_nonwater * s_nonwater) / (total * total)
    if math.isclose(expected, 1.0):
        return None
    return round((observed - expected) / (1.0 - expected), 6)


def regrid_scl(
    path: Path, reference: rasterio.io.DatasetReader
) -> tuple[np.ndarray, np.ndarray]:
    with rasterio.open(path) as src:
        raw = src.read(1, masked=True)
        fill = int(src.nodata) if src.nodata is not None else 0
        dst = np.full((reference.height, reference.width), fill, dtype=src.dtypes[0])
        available = np.zeros((reference.height, reference.width), dtype="uint8")
        reproject(
            source=np.asarray(raw.filled(fill)),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=fill,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=fill,
            resampling=Resampling.nearest,
        )
        reproject(
            source=(~np.ma.getmaskarray(raw)).astype("uint8"),
            destination=available,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=0,
            dst_transform=reference.transform,
            dst_crs=reference.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
    return dst, available.astype(bool)


def compare(
    mask_path: Path, scl_path: Path, date: str, scene_id: str
) -> dict[str, object]:
    with rasterio.open(mask_path) as water_src:
        mndwi = water_src.read(1)
        scl, scl_available = regrid_scl(scl_path, water_src)

    valid = (mndwi != NODATA_CLASS) & scl_available & ~np.isin(
        scl, np.array(sorted(SCL_INVALID), dtype=scl.dtype)
    )
    m_water = valid & (mndwi == 1)
    s_water = valid & (scl == SCL_WATER)
    tp = int((m_water & s_water).sum())
    tn = int((valid & ~m_water & ~s_water).sum())
    fp = int((m_water & ~s_water).sum())
    fn = int((~m_water & s_water).sum())
    intersection = tp
    union = int((m_water | s_water).sum())
    valid_count = int(valid.sum())
    m_count = int(m_water.sum())
    s_count = int(s_water.sum())
    return {
        "date": date,
        "scene_id": scene_id,
        "valid_pixel_count": valid_count,
        "mndwi_water_pixel_count": m_count,
        "scl_water_pixel_count": s_count,
        "mndwi_water_fraction": safe_ratio(m_count, valid_count),
        "scl_water_fraction": safe_ratio(s_count, valid_count),
        "water_fraction_difference": (
            round((m_count - s_count) / valid_count, 6) if valid_count else None
        ),
        "intersection_over_union": safe_ratio(intersection, union),
        "precision_vs_scl": safe_ratio(tp, tp + fp),
        "recall_vs_scl": safe_ratio(tp, tp + fn),
        "overall_agreement": safe_ratio(tp + tn, valid_count),
        "cohen_kappa": kappa(tp, tn, fp, fn),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "interpretation": "SCL consistency cross-check only; SCL is not field truth",
    }


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(np.median(np.asarray(values, dtype="float64"))), 6)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--satellite-root", type=Path, required=True)
    parser.add_argument("--water-root", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    with args.catalog.open(newline="", encoding="utf-8") as handle:
        catalog = list(csv.DictReader(handle))

    rows: list[dict[str, object]] = []
    seen_dates: set[str] = set()
    for item in sorted(
        catalog, key=lambda row: (row["acquisition_datetime_utc"], row["scene_id"])
    ):
        date = item["acquisition_datetime_utc"][:10]
        if date in seen_dates:
            continue
        scene_id = item["scene_id"]
        scl = args.satellite_root / date[:4] / scene_id / "SCL_20m.tif"
        mask = args.water_root / date / "water_mask.tif"
        if not scl.exists() or not mask.exists():
            raise FileNotFoundError(
                f"Missing comparison input for {date}: {scl} / {mask}"
            )
        rows.append(compare(mask, scl, date, scene_id))
        seen_dates.add(date)

    if not rows:
        raise SystemExit("No Sentinel-2 dates were audited")

    ious = [
        float(row["intersection_over_union"])
        for row in rows
        if row["intersection_over_union"] is not None
    ]
    agreements = [
        float(row["overall_agreement"])
        for row in rows
        if row["overall_agreement"] is not None
    ]
    kappas = [
        float(row["cohen_kappa"])
        for row in rows
        if row["cohen_kappa"] is not None
    ]
    differences = [
        abs(float(row["water_fraction_difference"]))
        for row in rows
        if row["water_fraction_difference"] is not None
    ]
    outliers = [
        row["date"]
        for row in rows
        if (
            row["intersection_over_union"] is not None
            and float(row["intersection_over_union"]) < 0.50
        )
        or (
            row["water_fraction_difference"] is not None
            and abs(float(row["water_fraction_difference"])) > 0.05
        )
    ]
    summary = {
        "scene_count": len(rows),
        "median_water_iou": median(ious),
        "median_overall_agreement": median(agreements),
        "median_cohen_kappa": median(kappas),
        "median_absolute_water_fraction_difference": median(differences),
        "review_dates": outliers,
        "analysis_status": "SCL_CROSS_CHECK_NOT_GROUND_TRUTH",
        "interpretation": (
            "Agreement with Sentinel-2 SCL class 6 is a consistency diagnostic. "
            "Neither MNDWI nor SCL substitutes for tide-matched field shoreline data."
        ),
        "scenes": rows,
    }
    write_csv(args.csv, rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "scenes"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
