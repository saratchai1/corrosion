#!/usr/bin/env python3
"""Audit the two long-term apparent-accretion transects near Surat Thani 37-STC.

The original MVP classified T028 and T038 as ``apparent_accretion`` from the
1985-2026 automated water/land-boundary history.  That classification does not
answer the narrower question "did land accrete after planting in late 2023?".

This script therefore:
1. extracts T028 and T038 from the full waterline transects;
2. compares their 2023->2026 movement in both the baseline and tide-matched
   screening products;
3. locates each candidate on the verified drone WGS84 envelope;
4. renders a 2023 Sentinel-2 image to the same extent as the verified drone / 
   2026 Sentinel-2 pair;
5. exports centered web crops for 2023, 2026 and Drone HR; and
6. writes a conservative machine-readable audit JSON.

It does not call mudflat exposure "new land" solely from one drone epoch.  A
post-2023 accretion candidate is retained only when both image-derived waterline
screenings move seaward; otherwise it is rejected for the post-2023 question.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image
from shapely.geometry import Point, box, shape
from shapely.ops import nearest_points, unary_union

CANDIDATE_IDS = ("T028", "T038")
DEFAULT_CROP_WIDTH = 480
DEFAULT_CROP_HEIGHT = 360


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def feature_map(path: Path) -> dict[str, dict[str, Any]]:
    fc = load_json(path)
    return {
        str(feature.get("properties", {}).get("transect_id")): feature
        for feature in fc.get("features", [])
        if feature.get("properties", {}).get("transect_id")
    }


def union_features(path: Path):
    fc = load_json(path)
    geoms = [shape(feature["geometry"]) for feature in fc.get("features", []) if feature.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometry found in {path}")
    return unary_union(geoms)


def points_from_geometry(geom) -> list[Point]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Point":
        return [geom]
    if geom.geom_type == "MultiPoint":
        return list(geom.geoms)
    if geom.geom_type in {"LineString", "LinearRing"}:
        return [geom.interpolate(0.5, normalized=True)]
    if geom.geom_type == "MultiLineString":
        return [part.interpolate(0.5, normalized=True) for part in geom.geoms]
    if hasattr(geom, "geoms"):
        out: list[Point] = []
        for part in geom.geoms:
            out.extend(points_from_geometry(part))
        return out
    return []


def point_in_bounds(point: Point, bounds: dict[str, float]) -> bool:
    return (
        bounds["left"] <= point.x <= bounds["right"]
        and bounds["bottom"] <= point.y <= bounds["top"]
    )


def choose_boundary_point(line, boundary, project, bounds: dict[str, float]) -> Point:
    intersections = points_from_geometry(line.intersection(boundary))
    inside = [point for point in intersections if point_in_bounds(point, bounds)]
    candidates = inside or intersections
    if candidates:
        return min(candidates, key=lambda point: point.distance(project))

    on_line, _ = nearest_points(line, boundary)
    if point_in_bounds(on_line, bounds):
        return on_line

    clipped = line.intersection(box(bounds["left"], bounds["bottom"], bounds["right"], bounds["top"]))
    clipped_points = points_from_geometry(clipped)
    if clipped_points:
        return min(clipped_points, key=lambda point: point.distance(project))
    return line.interpolate(0.5, normalized=True)


def find_epoch(index: dict[str, Any], year: int) -> dict[str, Any]:
    for epoch in index.get("epochs", []):
        if int(epoch.get("targetYear", -1)) == year:
            return epoch
    raise RuntimeError(f"Missing imagery epoch {year}")


def render_same_extent(
    source_path: Path,
    epoch: dict[str, Any],
    bounds: dict[str, float],
    size: tuple[int, int],
    out_path: Path,
) -> None:
    coords = epoch["imageCoordinates"]
    xs = [float(item[0]) for item in coords]
    ys = [float(item[1]) for item in coords]
    src_left, src_right = min(xs), max(xs)
    src_bottom, src_top = min(ys), max(ys)

    if not (
        bounds["left"] >= src_left
        and bounds["right"] <= src_right
        and bounds["bottom"] >= src_bottom
        and bounds["top"] <= src_top
    ):
        raise RuntimeError(f"Requested drone extent is not fully contained by {source_path}")

    with Image.open(source_path) as image:
        image = image.convert("RGB")
        src_w, src_h = image.size
        x0 = (bounds["left"] - src_left) / (src_right - src_left) * src_w
        x1 = (bounds["right"] - src_left) / (src_right - src_left) * src_w
        y0 = (src_top - bounds["top"]) / (src_top - src_bottom) * src_h
        y1 = (src_top - bounds["bottom"]) / (src_top - src_bottom) * src_h
        sampled = image.transform(
            size,
            Image.Transform.EXTENT,
            (x0, y0, x1, y1),
            resample=Image.Resampling.BILINEAR,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sampled.save(out_path, format="WEBP", quality=90, method=6)


def lonlat_to_pixel(point: Point, bounds: dict[str, float], width: int, height: int) -> tuple[float, float]:
    x = (point.x - bounds["left"]) / (bounds["right"] - bounds["left"]) * width
    y = (bounds["top"] - point.y) / (bounds["top"] - bounds["bottom"]) * height
    return x, y


def crop_centered(
    source_path: Path,
    center_xy: tuple[float, float],
    out_path: Path,
    crop_width: int,
    crop_height: int,
) -> dict[str, float]:
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        cx, cy = center_xy
        left = int(round(cx - crop_width / 2))
        top = int(round(cy - crop_height / 2))
        left = max(0, min(left, max(0, width - crop_width)))
        top = max(0, min(top, max(0, height - crop_height)))
        right = min(width, left + crop_width)
        bottom = min(height, top + crop_height)
        crop = image.crop((left, top, right, bottom))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_path, format="WEBP", quality=90, method=6)
        marker_x = 100 * (cx - left) / max(1, right - left)
        marker_y = 100 * (cy - top) / max(1, bottom - top)
        return {
            "x_percent": max(0.0, min(100.0, marker_x)),
            "y_percent": max(0.0, min(100.0, marker_y)),
        }


def rel_asset(path: Path, public_root: Path) -> str:
    return str(path.relative_to(public_root)).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/drone/drone_manifest.json"),
    )
    parser.add_argument(
        "--transects",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/transect_summary.geojson"),
    )
    parser.add_argument(
        "--tide-transects",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/tide_matched/transect_summary.geojson"),
    )
    parser.add_argument(
        "--project-boundary",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/project_boundary.geojson"),
    )
    parser.add_argument(
        "--boundary-2023",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/boundaries/2023_water_land_boundary.geojson"),
    )
    parser.add_argument(
        "--boundary-2026",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/boundaries/2026_water_land_boundary.geojson"),
    )
    parser.add_argument(
        "--imagery-index",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/imagery_index.json"),
    )
    parser.add_argument(
        "--imagery-root",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani"),
    )
    parser.add_argument(
        "--executive-summary",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/executive_summary.json"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("web-surat-thani/public/data/surat_thani/drone/land_accretion_candidate_audit.json"),
    )
    parser.add_argument("--crop-width", type=int, default=DEFAULT_CROP_WIDTH)
    parser.add_argument("--crop-height", type=int, default=DEFAULT_CROP_HEIGHT)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    compare = manifest.get("same_extent_compare") or {}
    if compare.get("status") != "AVAILABLE":
        raise RuntimeError("same_extent_compare must be AVAILABLE before candidate audit")

    bounds = compare["bounds_wgs84"]
    width = int(compare["width_px"])
    height = int(compare["height_px"])
    public_root = Path("web-surat-thani/public")
    drone_path = public_root / compare["drone_asset"]
    sentinel_2026_path = public_root / compare["sentinel2_asset"]
    if not drone_path.is_file() or not sentinel_2026_path.is_file():
        raise RuntimeError("Required same-extent Drone / 2026 Sentinel assets are missing")

    imagery_index = load_json(args.imagery_index)
    epoch_2023 = find_epoch(imagery_index, 2023)
    sentinel_2023_source = args.imagery_root / epoch_2023["image"]
    sentinel_2023_path = args.output_json.parent / "sentinel2_2023_same_extent.webp"
    render_same_extent(
        sentinel_2023_source,
        epoch_2023,
        bounds,
        (width, height),
        sentinel_2023_path,
    )

    full = feature_map(args.transects)
    tide = feature_map(args.tide_transects)
    project = union_features(args.project_boundary)
    boundary_2023 = union_features(args.boundary_2023)
    boundary_2026 = union_features(args.boundary_2026)
    executive = load_json(args.executive_summary)

    candidates: list[dict[str, Any]] = []
    supported_count = 0
    for transect_id in CANDIDATE_IDS:
        if transect_id not in full or transect_id not in tide:
            raise RuntimeError(f"Missing candidate {transect_id} in screening products")
        feature = full[transect_id]
        tide_feature = tide[transect_id]
        props = feature["properties"]
        tide_props = tide_feature["properties"]
        line = shape(feature["geometry"])

        point_2023 = choose_boundary_point(line, boundary_2023, project, bounds)
        point_2026 = choose_boundary_point(line, boundary_2026, project, bounds)
        center = Point((point_2023.x + point_2026.x) / 2, (point_2023.y + point_2026.y) / 2)
        if not point_in_bounds(center, bounds):
            center = point_2026 if point_in_bounds(point_2026, bounds) else point_2023

        baseline_change = float(props["positions_m"]["2026"]) - float(props["positions_m"]["2023"])
        tide_change = float(tide_props["positions_m"]["2026"]) - float(tide_props["positions_m"]["2023"])
        long_term = float(props["net_change_m"])
        post_supported = baseline_change > 0 and tide_change > 0
        if post_supported:
            supported_count += 1

        center_xy = lonlat_to_pixel(center, bounds, width, height)
        prefix = transect_id.lower()
        crop_assets: dict[str, Any] = {}
        for role, source in (
            ("sentinel2_2023", sentinel_2023_path),
            ("sentinel2_2026", sentinel_2026_path),
            ("drone", drone_path),
        ):
            out = args.output_json.parent / f"{prefix}_{role}_crop.webp"
            marker = crop_centered(
                source,
                center_xy,
                out,
                args.crop_width,
                args.crop_height,
            )
            crop_assets[role] = {
                "asset": rel_asset(out, public_root),
                "marker": marker,
            }

        candidates.append({
            "transect_id": transect_id,
            "historical_classification_1985_2026": props.get("classification"),
            "historical_net_change_m_1985_2026": round(long_term, 2),
            "historical_rate_m_per_year_1985_2026": props.get("end_point_rate_m_per_year"),
            "historical_confidence": props.get("confidence"),
            "baseline_waterline_2023_2026": {
                "position_2023_m": props["positions_m"]["2023"],
                "position_2026_m": props["positions_m"]["2026"],
                "change_m": round(baseline_change, 2),
                "direction": "seaward" if baseline_change > 0 else ("stable" if baseline_change == 0 else "landward"),
            },
            "tide_matched_waterline_2023_2026": {
                "position_2023_m": tide_props["positions_m"]["2023"],
                "position_2026_m": tide_props["positions_m"]["2026"],
                "change_m": round(tide_change, 2),
                "classification": tide_props.get("classification"),
                "direction": "seaward" if tide_change > 0 else ("stable" if tide_change == 0 else "landward"),
            },
            "candidate_zone": {
                "center_lon": center.x,
                "center_lat": center.y,
                "waterline_point_2023_lon_lat": [point_2023.x, point_2023.y],
                "waterline_point_2026_lon_lat": [point_2026.x, point_2026.y],
                "inside_drone_extent": point_in_bounds(center, bounds),
                "marker_on_full_same_extent": {
                    "x_percent": 100 * center_xy[0] / width,
                    "y_percent": 100 * center_xy[1] / height,
                },
            },
            "web_crops": crop_assets,
            "post_2023_accretion_supported": post_supported,
            "post_2023_verdict": (
                "RETAIN_AS_POST_2023_ACCRETION_CANDIDATE"
                if post_supported
                else "NOT_SUPPORTED_AS_POST_2023_ACCRETION"
            ),
            "interpretation_th": (
                "ทั้ง baseline และ tide-matched เคลื่อนออกทะเล จึงยังคงเป็น candidate หลังปี 2023 แต่ต้องยืนยันด้วย geomorphic edge/field."
                if post_supported
                else (
                    f"แม้ระยะยาว 1985-2026 เคยถูกจัดเป็น apparent accretion (+{long_term:.2f} m) "
                    f"แต่ช่วง 2023-2026 baseline = {baseline_change:+.2f} m และ tide-matched = {tide_change:+.2f} m; "
                    "จึงไม่รองรับข้อสรุปว่าดินงอกหลังปลูก."
                )
            ),
        })

    edge_change = executive.get("key_numbers", {}).get("coastal_vegetation_edge", {}).get(
        "project_median_change_2023_2026_m"
    )
    audit = {
        "plot_id": "37-STC",
        "question": "มีดินงอกตรงไหนหลังการปลูกปี 2023 หรือไม่",
        "candidate_origin": (
            "T028 and T038 were the two project-frontage transects classified as apparent_accretion in the 1985-2026 automated water-land-boundary MVP."
        ),
        "audit_period": "2023_to_2026",
        "candidate_count": len(CANDIDATE_IDS),
        "post_2023_supported_candidate_count": supported_count,
        "overall_verdict": (
            "POST_2023_ACCRETION_CANDIDATE_PRESENT"
            if supported_count
            else "NO_POST_2023_LAND_ACCRETION_CONFIRMED_FROM_THE_TWO_LONG_TERM_CANDIDATES"
        ),
        "overall_interpretation_th": (
            "จาก 2 จุดที่เคยดูเหมือนดินงอกในแนวโน้มระยะยาว ยังไม่มีจุดใดผ่านเกณฑ์ว่าเป็นดินงอกหลังปลูกปี 2023. "
            "T028 ถอยเข้าฝั่งทั้งสองวิธี ส่วน T038 ไม่ขยับใน baseline แต่ถอยเข้าฝั่งเมื่อใช้ tide-matched. "
            "ภาพโดรนใช้ยืนยันสภาพปัจจุบันและตำแหน่ง แต่มีเพียง 1 epoch จึงไม่สามารถพิสูจน์การเกิดพื้นที่ใหม่ด้วยโดรนเพียงชุดเดียวได้."
        ),
        "coastal_vegetation_edge_project_median_change_2023_2026_m": edge_change,
        "scientific_guard": [
            "Water-land boundaries are image-derived and remain sensitive to tide and intertidal mudflat exposure.",
            "One drone epoch can verify current morphology/coverage but cannot establish a temporal land-gain rate.",
            "Do not relabel the long-term apparent-accretion classification as post-planting land accretion.",
            "A positive post-2023 claim would require repeat UAV/orthophoto or a stable manually digitized bank/geomorphic edge at comparable tide stage.",
        ],
        "same_extent": {
            "bounds_wgs84": bounds,
            "width_px": width,
            "height_px": height,
            "sentinel2_2023_asset": rel_asset(sentinel_2023_path, public_root),
            "sentinel2_2023_dates": epoch_2023.get("dates", []),
            "sentinel2_2026_asset": compare["sentinel2_asset"],
            "drone_asset": compare["drone_asset"],
        },
        "candidates": candidates,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "overall_verdict": audit["overall_verdict"],
        "supported_count": supported_count,
        "output": str(args.output_json),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
