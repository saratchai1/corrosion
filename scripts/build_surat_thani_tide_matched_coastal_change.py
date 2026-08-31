#!/usr/bin/env python3
"""Run a secondary single-scene tide-stage sensitivity analysis for Surat Thani 37-STC.

This intentionally does not overwrite the three-scene baseline MVP. It reuses the tested
coastal-change engine but permits one selected Sentinel-2 acquisition per 2023-2026 epoch.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, mapping

import build_coastal_change_mvp as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/surat_thani_tide_matched"
PUBLISH_ROOT = ROOT / "web/public/data/surat_thani/tide_matched"

core.AOI_PATH = ROOT / "data/aoi/surat_thani_37_stc_analysis_aoi.geojson"
core.CATALOG_PATH = ROOT / "data/catalog/surat_thani_tide_matched_optical_scenes.csv"
core.EPOCH_PATH = ROOT / "data/catalog/surat_thani_tide_matched_epochs.json"
core.OUT = OUT
core.WEB_DATA = OUT / "web"
core.TIDE_STATUS = "SCENE_STAGE_CONSTRAINED_NOT_FULLY_TIDE_NORMALIZED"
core.COAST_GUIDE_WGS84 = LineString(
    [
        (99.207, 9.329),
        (99.215, 9.334),
        (99.223, 9.339),
        (99.231, 9.343),
        (99.239, 9.348),
        (99.247, 9.353),
        (99.254, 9.358),
    ]
)


def process_epoch_allow_single(entry, catalog, aoi_utm):
    target_year = int(entry["target_year"])
    actual_year = int(entry["actual_year"])
    dataset = str(entry["dataset"])
    rows = core.scene_rows(
        catalog,
        dataset,
        actual_year,
        start=entry.get("start"),
        end=entry.get("end"),
        count=int(entry["count"]) if entry.get("count") is not None else None,
    )
    if len(rows) < 1:
        raise RuntimeError(f"tide-matched epoch {target_year} has no usable full-coverage scene")

    composite, valid_count, grid = core.build_composite(rows, dataset)
    valid = valid_count > 0
    dates = [row["acquisition_datetime_utc"][:10] for row in rows]
    sensors = sorted({row["sensor"] for row in rows})
    sensor = ", ".join(sensors)
    period = f"{dates[0]} to {dates[-1]}"

    composite_path = core.OUT / "optical" / f"{target_year}_composite.tif"
    core.write_composite(
        composite_path,
        composite,
        grid,
        {
            "target_year": target_year,
            "actual_year": actual_year,
            "sensor": sensor,
            "acquisition_period": period,
            "scene_count": len(rows),
            "method": "single tide-stage-constrained quality-masked surface reflectance scene",
            "tide_status": core.TIDE_STATUS,
            "boundary_interpretation": "spectral water-land boundary; not surveyed shoreline",
        },
    )
    preview_path = core.WEB_DATA / "imagery" / f"{target_year}.webp"
    core.save_preview(preview_path, composite, valid)

    green, swir = composite[1], composite[4]
    mndwi = np.divide(
        green - swir,
        green + swir,
        out=np.full_like(green, np.nan),
        where=np.abs(green + swir) > 1e-6,
    )
    threshold, threshold_method, ocean_mask, ocean, threshold_candidates = core.choose_water_mask(
        mndwi, valid, grid, aoi_utm
    )
    boundary = core.coastal_boundary(ocean, aoi_utm, grid["resolution"])
    boundary_path = core.OUT / "water_boundary" / f"{target_year}_water_land_boundary.geojson"
    core.save_boundary(
        boundary_path,
        boundary,
        {
            "year": target_year,
            "target_year": target_year,
            "actual_year": actual_year,
            "sensor": sensor,
            "actual_acquisition_period": period,
            "acquisition_period": period,
            "scene_count": len(rows),
            "method": f"MNDWI {threshold_method}, single tide-stage-constrained scene, conservative morphology, edge-connected ocean exterior, corridor-guided continuous trace",
            "threshold": round(threshold, 5),
            "mndwi_threshold": round(threshold, 5),
            "threshold_candidates": threshold_candidates,
            "tide_status": core.TIDE_STATUS,
            "source_resolution_m": grid["resolution"],
            "interpretation": "image-derived water-land boundary, not a true/surveyed shoreline",
            "qa_status": "tide-stage sensitivity extraction; visual review required",
        },
    )

    vegetation, vegetation_threshold, vegetation_area_ha = core.vegetation_proxy(
        composite, valid, ocean, boundary, grid
    )
    vegetation_path = core.OUT / "vegetation" / f"{target_year}_coastal_vegetation_proxy.geojson"
    core.write_json(
        vegetation_path,
        core.feature_collection([
            {
                "type": "Feature",
                "properties": {
                    "target_year": target_year,
                    "actual_year": actual_year,
                    "sensor": sensor,
                    "method": "NDVI threshold within provisional coastal corridor and image-derived land",
                    "ndvi_threshold": round(vegetation_threshold, 5),
                    "area_ha": round(vegetation_area_ha, 2),
                    "interpretation": "coastal vegetation spectral proxy; not a verified mangrove inventory",
                    "tide_status": core.TIDE_STATUS,
                },
                "geometry": mapping(core.project_geom(vegetation, core.TO_WEB)),
            }
        ]),
    )

    valid_fraction = float(valid.mean())
    ocean_fraction = float(ocean.area / max(aoi_utm.area, 1))
    print(
        f"tide-matched epoch={target_year} scene={dates[0]} valid={valid_fraction:.3f} "
        f"water={ocean_fraction:.3f} boundary_km={boundary.length / 1000:.2f}",
        flush=True,
    )
    return core.EpochResult(
        target_year=target_year,
        actual_year=actual_year,
        dataset=dataset,
        sensor=sensor,
        resolution_m=grid["resolution"],
        dates=dates,
        composite_path=composite_path,
        preview_path=preview_path,
        boundary_path=boundary_path,
        vegetation_path=vegetation_path,
        threshold=threshold,
        vegetation_threshold=vegetation_threshold,
        valid_fraction=valid_fraction,
        ocean_fraction=ocean_fraction,
        vegetation_area_ha=vegetation_area_ha,
        boundary_utm=boundary,
        ocean_utm=ocean,
        image_coordinates=core.image_coordinates(grid["bounds"]),
    )


core.process_epoch = process_epoch_allow_single
_original_copytree = core.shutil.copytree


def _routed_copytree(src, dst, *args, **kwargs):
    if Path(dst) == ROOT / "web/public/data":
        dst = PUBLISH_ROOT
    return _original_copytree(src, dst, *args, **kwargs)


core.shutil.copytree = _routed_copytree


def patch_outputs() -> None:
    for path in [
        OUT / "statistics/summary.json",
        OUT / "web/summary.json",
        PUBLISH_ROOT / "summary.json",
    ]:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            obj["title"] = "Surat Thani 37-STC tide-stage constrained coastal sensitivity"
            obj["analysis_role"] = "SECONDARY_TIDE_STAGE_SENSITIVITY_ANALYSIS"
            obj["baseline_comparison"] = "web/public/data/surat_thani/project_frontage_summary.json"
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for path in [OUT / "web/index.json", PUBLISH_ROOT / "index.json"]:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            obj["title"] = "Surat Thani 37-STC Tide-Stage Sensitivity"
            obj["aoi"] = "37-STC and surrounding Chaiya coast (derived analytical AOI)"
            obj["analysis_role"] = "SECONDARY_TIDE_STAGE_SENSITIVITY_ANALYSIS"
            obj["scene_selection_file"] = "../../../../data/analysis/surat_thani/tide_matched_scene_selection.json"
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    core.main()
    patch_outputs()


if __name__ == "__main__":
    main()
