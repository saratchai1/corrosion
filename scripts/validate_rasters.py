#!/usr/bin/env python3
"""Validate AOI COGs, acquisition metadata, previews, and checksums."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_geom
from shapely.geometry import box, shape

ANALYSIS_CRS = CRS.from_epsg(32647)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_aoi(path: Path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("type") != "FeatureCollection" or not obj.get("features"):
        raise ValueError("AOI must be a non-empty FeatureCollection")
    geom = obj["features"][0]["geometry"]
    shp = shape(geom)
    if shp.is_empty or not shp.is_valid:
        raise ValueError("AOI geometry is empty or invalid")
    return geom


def existing_checksums(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        checksum, filename = line.split(maxsplit=1)
        result[filename.strip()] = checksum
    return result


def preview_sidecars(scene_id: str) -> list[Path]:
    return [
        path
        for path in Path("data/previews").rglob("*.json")
        if scene_id in path.name
    ] if Path("data/previews").exists() else []


def validate(path: Path, aoi4326: dict, known_checksums: dict[str, str]) -> dict:
    record = {
        "path": str(path),
        "sha256": "",
        "size": 0,
        "errors": [],
        "warnings": [],
        "flags": [],
    }
    if not path.exists():
        record["errors"].append("file does not exist")
        record["qa_status"] = "fail"
        return record
    record["size"] = path.stat().st_size
    if record["size"] == 0:
        record["errors"].append("file is empty")
        record["qa_status"] = "fail"
        return record
    record["sha256"] = digest(path)
    expected = known_checksums.get(str(path))
    if expected and expected != record["sha256"]:
        record["errors"].append("checksum differs from existing manifest")
    try:
        with rasterio.open(path) as src:
            tags = src.tags()
            record.update(
                driver=src.driver,
                crs=str(src.crs),
                bounds=list(src.bounds),
                resolution=[abs(src.transform.a), abs(src.transform.e)],
                width=src.width,
                height=src.height,
                band_count=src.count,
                nodata=src.nodata,
                dtype=list(src.dtypes),
                tiled=bool(src.profile.get("tiled")),
                tags=tags,
            )
            if not src.crs:
                record["errors"].append("missing CRS")
            elif src.crs != ANALYSIS_CRS:
                record["errors"].append("analysis raster is not EPSG:32647")
            if src.width <= 0 or src.height <= 0 or src.count <= 0:
                record["errors"].append("empty raster dimensions")
            if src.count != 1:
                record["warnings"].append("expected one native-resolution band per COG")
            if src.nodata is None:
                record["errors"].append("nodata is unset")
            if src.crs:
                aoi_in_raster = shape(
                    transform_geom("EPSG:4326", src.crs, aoi4326)
                )
                footprint = box(*src.bounds)
                if not footprint.intersects(aoi_in_raster):
                    record["errors"].append("raster footprint does not overlap AOI")
                overlap = footprint.intersection(aoi_in_raster).area
                record["aoi_overlap_fraction"] = (
                    overlap / aoi_in_raster.area if aoi_in_raster.area else 0
                )
                if record["aoi_overlap_fraction"] < 0.95:
                    record["warnings"].append(
                        f"raster covers only {record['aoi_overlap_fraction']:.3f} of AOI"
                    )
            try:
                mask = src.read_masks(
                    1, out_shape=(min(512, src.height), min(512, src.width))
                )
                if not mask.any():
                    record["errors"].append("sample mask contains no valid pixels")
            except Exception as exc:
                record["warnings"].append(f"mask sample failed: {exc}")

            for key in ("dataset", "scene_id", "band", "acquisition_datetime_utc"):
                if not tags.get(key):
                    record["errors"].append(f"missing raster metadata tag: {key}")
            if tags.get("acquisition_datetime_utc"):
                try:
                    datetime.fromisoformat(
                        tags["acquisition_datetime_utc"].replace("Z", "+00:00")
                    )
                except ValueError:
                    record["errors"].append("invalid acquisition_datetime_utc tag")
            expected_resolution = tags.get("native_resolution_m")
            if expected_resolution:
                try:
                    expected_value = float(expected_resolution)
                    actual = max(abs(src.transform.a), abs(src.transform.e))
                    if abs(actual - expected_value) > 0.01:
                        record["errors"].append(
                            f"resolution {actual} differs from tagged native/output "
                            f"resolution {expected_value}"
                        )
                except ValueError:
                    record["errors"].append("invalid native_resolution_m tag")
            scene_id = tags.get("scene_id", "")
            sidecars = preview_sidecars(scene_id) if scene_id else []
            if not sidecars:
                record["warnings"].append("no preview sidecar found for scene")
            else:
                matches = False
                for sidecar in sidecars:
                    payload = json.loads(sidecar.read_text(encoding="utf-8"))
                    if str(path) in payload.get("source_rasters", []):
                        matches = True
                        preview_path = Path(payload.get("preview", ""))
                        if not preview_path.exists() or preview_path.stat().st_size == 0:
                            record["errors"].append(
                                f"preview missing/empty: {preview_path}"
                            )
                if not matches:
                    record["warnings"].append(
                        "scene preview exists but does not reference this raster"
                    )
    except Exception as exc:
        record["errors"].append(f"{type(exc).__name__}: {exc}")

    try:
        from rio_cogeo.cogeo import cog_validate

        valid, errors, warnings = cog_validate(str(path), strict=True)
        record["cog_valid"] = bool(valid)
        if not valid:
            record["errors"].extend(f"COG: {x}" for x in errors)
        record["warnings"].extend(f"COG: {x}" for x in warnings)
    except Exception as exc:
        record["errors"].append(f"COG validation failed: {type(exc).__name__}: {exc}")

    lower = path.name.lower()
    if "qa_pixel" in lower:
        record["flags"].append("quality mask retained")
    if "scl" in lower:
        record["flags"].append("SCL retained for cloud/shadow/cirrus review")
    record["qa_status"] = (
        "fail"
        if record["errors"]
        else ("review" if record["warnings"] else "pass")
    )
    return record


def merge_report(path: Path, rows: list[dict]) -> None:
    previous = []
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = []
    merged = {row.get("path"): row for row in previous if row.get("path")}
    merged.update({row["path"]: row for row in rows})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([merged[key] for key in sorted(merged)], indent=2),
        encoding="utf-8",
    )


def update_catalogs(rows: list[dict]) -> None:
    by_scene: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        tags = row.get("tags", {})
        dataset = tags.get("dataset")
        scene_id = tags.get("scene_id")
        if dataset and scene_id:
            by_scene.setdefault((dataset, scene_id), []).append(row["qa_status"])
    for dataset in ("sentinel2", "landsat", "sentinel1"):
        path = Path(f"data/catalog/{dataset}_scenes.csv")
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            catalog = list(csv.DictReader(handle))
            fields = handle.readline if False else None
        changed = False
        for item in catalog:
            statuses = by_scene.get((dataset, item.get("scene_id", "")))
            if statuses:
                item["qa_status"] = (
                    "fail"
                    if "fail" in statuses
                    else ("review" if "review" in statuses else "pass")
                )
                changed = True
        if changed:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=catalog[0].keys(), lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(catalog)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--aoi", default="data/aoi/samut_songkhram_aoi.geojson")
    parser.add_argument("--json", default="data/manifests/raster_validation.json")
    parser.add_argument("--checksums", default="data/manifests/checksums.sha256")
    args = parser.parse_args()

    checksum_path = Path(args.checksums)
    known = existing_checksums(checksum_path)
    aoi = load_aoi(Path(args.aoi))
    rows = [validate(Path(value), aoi, known) for value in args.paths]
    merge_report(Path(args.json), rows)
    update_catalogs(rows)

    # Refresh the complete raster/preview checksum ledger and dataset manifest.
    from download_satellite_data import update_manifests

    update_manifests()
    for row in rows:
        details = "; ".join(row["errors"] + row["warnings"] + row["flags"])
        print(row["qa_status"], row["path"], details)
    raise SystemExit(1 if any(row["errors"] for row in rows) else 0)


if __name__ == "__main__":
    main()
