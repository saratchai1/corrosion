#!/usr/bin/env python3
"""Discover, rank, and optionally download AOI-only satellite COGs.

Searches are split by year and follow STAC next links. Dry-run mode reads only
AOI quality masks and writes catalogs. Download mode reads remote COG windows
and writes EPSG:32647 COGs. Tide stays unverified until sourced data are joined.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
PLANETARY_COMPUTER = "https://planetarycomputer.microsoft.com/api/stac/v1"
BKK = ZoneInfo("Asia/Bangkok")
ANALYSIS_CRS = "EPSG:32647"
MAX_WORKING_BYTES = 15 * 1024**3
DEFAULT_PAGE_SIZE = 100
DRY_MONTHS = {11, 12, 1, 2, 3, 4}

FIELDS = [
    "dataset", "scene_id", "sensor", "acquisition_datetime_utc",
    "acquisition_datetime_bangkok", "cloud_cover_scene", "cloud_cover_aoi",
    "tide_station", "tide_level", "tide_datum", "tide_status", "source_url",
    "source_license", "crs", "resolution_m", "bands", "local_path",
    "file_size_bytes", "sha256", "selection_reason", "qa_status",
]


@dataclass(frozen=True)
class Provider:
    name: str
    endpoint: str
    collection: str
    sign_assets: bool = False


PROVIDERS = {
    "sentinel2": Provider("Element 84 Earth Search", EARTH_SEARCH, "sentinel-2-l2a"),
    "landsat": Provider(
        "Microsoft Planetary Computer", PLANETARY_COMPUTER, "landsat-c2-l2", True
    ),
    "sentinel1": Provider(
        "Microsoft Planetary Computer", PLANETARY_COMPUTER, "sentinel-1-grd", True
    ),
}

LICENSES = {
    "sentinel2": "Copernicus Sentinel Data Legal Notice - free, full and open access",
    "sentinel1": "Copernicus Sentinel Data Legal Notice - free, full and open access",
    "landsat": "USGS Landsat - Public Domain / no restrictions on use",
}

# Output band, STAC asset key, output/native pixel size, categorical.
ASSETS: dict[str, list[tuple[str, str, float, bool]]] = {
    "sentinel2": [
        ("B2", "blue", 10, False), ("B3", "green", 10, False),
        ("B4", "red", 10, False), ("B8", "nir", 10, False),
        ("B5", "rededge1", 20, False), ("B6", "rededge2", 20, False),
        ("B7", "rededge3", 20, False), ("B8A", "nir08", 20, False),
        ("B11", "swir16", 20, False), ("B12", "swir22", 20, False),
        ("SCL", "scl", 20, True),
    ],
    "landsat": [
        ("BLUE", "blue", 30, False), ("GREEN", "green", 30, False),
        ("RED", "red", 30, False), ("NIR", "nir08", 30, False),
        ("SWIR1", "swir16", 30, False), ("SWIR2", "swir22", 30, False),
        ("QA_PIXEL", "qa_pixel", 30, True),
    ],
    "sentinel1": [("VV", "vv", 10, False), ("VH", "vh", 10, False)],
}


@dataclass
class Candidate:
    item: dict[str, Any]
    coverage_fraction: float
    cloud_aoi: float | None = None
    cloud_pixels: int = 0
    valid_pixels: int = 0
    cloud_error: str = ""
    local_paths: list[str] = field(default_factory=list)
    file_bytes: int = 0
    checksums: list[str] = field(default_factory=list)
    qa_status: str = "candidate-unverified"


@dataclass
class Acquisition:
    day: str
    candidates: list[Candidate]
    coverage_fraction: float
    cloud_aoi: float | None = None

    @property
    def dt(self) -> datetime:
        return item_datetime(self.candidates[0].item)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def load_aoi(path: Path) -> tuple[dict[str, Any], Any]:
    from shapely.geometry import shape
    from shapely.validation import explain_validity

    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("type") != "FeatureCollection" or not obj.get("features"):
        raise ValueError(f"AOI must be a non-empty GeoJSON FeatureCollection: {path}")
    geom = obj["features"][0]["geometry"]
    shp = shape(geom)
    if shp.is_empty or shp.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI must contain a non-empty Polygon or MultiPolygon")
    if not shp.is_valid:
        raise ValueError(f"Invalid AOI geometry: {explain_validity(shp)}")
    minx, miny, maxx, maxy = shp.bounds
    if not (-180 <= minx < maxx <= 180 and -90 <= miny < maxy <= 90):
        raise ValueError(f"AOI coordinates are not valid lon/lat bounds: {shp.bounds}")
    if maxx < 99.85 or minx > 100.15 or maxy < 13.20 or miny > 13.55:
        raise ValueError(f"AOI does not intersect Samut Songkhram coast: {shp.bounds}")
    return geom, shp


def parse_cli_date(value: str) -> date:
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO date/datetime: {value}") from exc


def rfc3339_interval(start: date, end: date) -> str:
    """Earth Search rejects date-only intervals, so emit full RFC3339."""
    first = datetime.combine(start, time.min, timezone.utc)
    last = datetime.combine(end, time.max.replace(microsecond=0), timezone.utc)
    return (
        first.isoformat().replace("+00:00", "Z")
        + "/"
        + last.isoformat().replace("+00:00", "Z")
    )


import time as _time

def request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None,
    dataset: str,
    date_range: str,
    timeout: int = 120,
    max_retries: int = 3,
) -> dict[str, Any]:
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.request(method, url, json=body, timeout=timeout)
        except requests.RequestException as exc:
            if attempt < max_retries:
                eprint(f"STAC request transport failure (attempt {attempt}), retrying...")
                _time.sleep(2 ** attempt)
                continue
            eprint("STAC request transport failure")
            eprint("endpoint:", url)
            eprint("dataset:", dataset)
            eprint("date_range:", date_range)
            eprint("request_body:", json.dumps(body, ensure_ascii=False, indent=2))
            raise
        
        if not response.ok:
            if response.status_code >= 500 and attempt < max_retries:
                eprint(f"STAC request failed with {response.status_code} (attempt {attempt}), retrying...")
                _time.sleep(2 ** attempt)
                continue
                
            eprint("STAC request failed")
            eprint("endpoint:", url)
            eprint("dataset:", dataset)
            eprint("date_range:", date_range)
            eprint("request_body:", json.dumps(body, ensure_ascii=False, indent=2))
            eprint("status:", response.status_code)
            eprint("response_body:", response.text)
            response.raise_for_status()
        return response.json()


def check_collection(dataset: str) -> None:
    provider = PROVIDERS[dataset]
    url = f"{provider.endpoint}/collections/{provider.collection}"
    response = requests.get(url, timeout=60)
    if not response.ok:
        eprint("STAC collection check failed")
        eprint("endpoint:", url)
        eprint("dataset:", dataset)
        eprint("status:", response.status_code)
        eprint("response_body:", response.text)
        response.raise_for_status()
    if response.json().get("id") != provider.collection:
        raise RuntimeError(f"Provider returned unexpected collection for {dataset}")


def search_year(
    dataset: str,
    geom: dict[str, Any],
    start: date,
    end: date,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    provider = PROVIDERS[dataset]
    date_range = rfc3339_interval(start, end)
    body: dict[str, Any] = {
        "collections": [provider.collection],
        "intersects": geom,
        "datetime": date_range,
        "limit": page_size,
    }
    method = "POST"
    url = f"{provider.endpoint}/search"
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_pages: set[str] = set()
    while True:
        key = f"{method}:{url}:{json.dumps(body, sort_keys=True)}"
        if key in seen_pages:
            raise RuntimeError(f"STAC pagination loop detected for {dataset} {date_range}")
        seen_pages.add(key)
        page = request_json(
            method, url, body=body if method == "POST" else None,
            dataset=dataset, date_range=date_range,
        )
        for item in page.get("features", []):
            if item.get("id") not in seen_ids:
                items.append(item)
                seen_ids.add(item.get("id"))
        next_link = next(
            (link for link in page.get("links", []) if link.get("rel") == "next"),
            None,
        )
        if not next_link:
            break
        method = next_link.get("method", "GET").upper()
        url = next_link["href"]
        body = next_link.get("body") or body
    return items


def item_datetime(item: dict[str, Any]) -> datetime:
    props = item.get("properties", {})
    value = props.get("datetime") or props.get("start_datetime")
    if not value:
        raise ValueError(f"STAC item has no datetime: {item.get('id')}")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def dtpair(value: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z"), dt.astimezone(BKK).isoformat()


def sensor_name(dataset: str, props: dict[str, Any]) -> str:
    platform = props.get("platform") or props.get("constellation")
    if platform:
        return str(platform)
    return {"sentinel2": "Sentinel-2", "sentinel1": "Sentinel-1"}.get(
        dataset, "Landsat"
    )


def cloud_scene(item: dict[str, Any]) -> float | None:
    value = item.get("properties", {}).get("eo:cloud_cover")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def item_source_url(item: dict[str, Any], dataset: str) -> str:
    self_link = next(
        (x.get("href") for x in item.get("links", []) if x.get("rel") == "self"),
        None,
    )
    if self_link:
        return self_link
    provider = PROVIDERS[dataset]
    return (
        f"{provider.endpoint}/collections/{provider.collection}/items/{item.get('id')}"
    )


def coverage_fraction(item: dict[str, Any], aoi_shape: Any) -> float:
    from shapely.geometry import shape

    if not item.get("geometry"):
        return 0.0
    try:
        return max(
            0.0,
            min(1.0, shape(item["geometry"]).intersection(aoi_shape).area / aoi_shape.area),
        )
    except Exception:
        return 0.0


def acquisition_coverage(candidates: list[Candidate], aoi_shape: Any) -> float:
    from shapely.geometry import shape
    from shapely.ops import unary_union

    geoms = [shape(c.item["geometry"]) for c in candidates if c.item.get("geometry")]
    if not geoms:
        return 0.0
    return max(
        0.0,
        min(1.0, unary_union(geoms).intersection(aoi_shape).area / aoi_shape.area),
    )


def group_acquisitions(items: list[dict[str, Any]], aoi_shape: Any) -> list[Acquisition]:
    from shapely.geometry import shape

    grouped: dict[str, list[Candidate]] = {}
    for item in items:
        day = item_datetime(item).date().isoformat()
        grouped.setdefault(day, []).append(
            Candidate(item=item, coverage_fraction=coverage_fraction(item, aoi_shape))
        )
    acquisitions = []
    for day, candidates in sorted(grouped.items()):
        # Some catalogs return adjacent tiles whose footprints both intersect the
        # AOI even when one tile already covers it completely. Keep the smallest
        # deterministic tile set that materially increases AOI coverage.
        retained: list[Candidate] = []
        covered = None
        for candidate in sorted(
            candidates, key=lambda x: (-x.coverage_fraction, x.item.get("id", ""))
        ):
            geom = shape(candidate.item["geometry"]).intersection(aoi_shape)
            combined = geom if covered is None else covered.union(geom)
            old_fraction = 0.0 if covered is None else covered.area / aoi_shape.area
            new_fraction = combined.area / aoi_shape.area
            if not retained or new_fraction - old_fraction > 0.001:
                retained.append(candidate)
                covered = combined
            if new_fraction >= 0.999:
                break
        acquisitions.append(
            Acquisition(day, retained, acquisition_coverage(retained, aoi_shape))
        )
    return acquisitions


def has_required_assets(dataset: str, item: dict[str, Any]) -> bool:
    available = set(item.get("assets", {}))
    required = {asset_key for _, asset_key, _, _ in ASSETS[dataset]}
    return required <= available


def prefilter_item(dataset: str, item: dict[str, Any]) -> bool:
    if not has_required_assets(dataset, item):
        return False
    props = item.get("properties", {})
    if dataset == "landsat":
        category = str(props.get("landsat:collection_category", ""))
        if category not in {"", "T1"}:
            return False
    if dataset == "sentinel1":
        pols = {str(p).upper() for p in props.get("sar:polarizations", [])}
        if props.get("sar:instrument_mode") not in {None, "IW"}:
            return False
        if not {"VV", "VH"} <= pols:
            return False
    return True


def acquisition_pre_score(dataset: str, acq: Acquisition) -> tuple[Any, ...]:
    values = [x for x in (cloud_scene(c.item) for c in acq.candidates) if x is not None]
    scene_cloud = sum(values) / len(values) if values else 1000.0
    season_penalty = 0 if dataset == "sentinel1" or acq.dt.month in DRY_MONTHS else 1
    return (season_penalty, scene_cloud, -acq.coverage_fraction, acq.day)


def sign_item(item: dict[str, Any], dataset: str) -> dict[str, Any]:
    if not PROVIDERS[dataset].sign_assets:
        return item
    import planetary_computer
    import pystac

    return planetary_computer.sign(pystac.Item.from_dict(item)).to_dict()


def raster_env() -> dict[str, str]:
    return {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.TIF,.TIFF,.jp2",
        "AWS_NO_SIGN_REQUEST": "YES",
    }


def quality_counts(
    dataset: str, candidate: Candidate, geom4326: dict[str, Any]
) -> tuple[int, int]:
    if dataset == "sentinel1":
        return 0, 0
    import numpy as np
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    key = "scl" if dataset == "sentinel2" else "qa_pixel"
    signed = sign_item(candidate.item, dataset)
    asset = signed.get("assets", {}).get(key)
    if not asset:
        raise KeyError(f"{candidate.item.get('id')} has no {key!r} asset")
    with rasterio.Env(**raster_env()):
        with rasterio.open(asset["href"]) as src:
            if not src.crs:
                raise ValueError(f"quality asset has no CRS: {asset['href']}")
            geom_src = transform_geom("EPSG:4326", src.crs, geom4326)
            arr, _ = mask(src, [geom_src], crop=True, indexes=1, filled=False)
    data = np.asarray(arr.data)
    masked = np.ma.getmaskarray(arr)
    if dataset == "sentinel2":
        valid = (~masked) & (data != 0)
        bad = valid & np.isin(data, [1, 3, 8, 9, 10])
    else:
        valid = (~masked) & ((data & 1) == 0)
        bad_bits = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
        bad = valid & ((data & bad_bits) != 0)
    return int(bad.sum()), int(valid.sum())


def assess_aoi_quality(
    dataset: str, acquisitions: list[Acquisition], geom4326: dict[str, Any]
) -> None:
    if dataset == "sentinel1":
        return
    for acq in acquisitions:
        bad_total = 0
        valid_total = 0
        for candidate in acq.candidates:
            try:
                bad, valid = quality_counts(dataset, candidate, geom4326)
                candidate.cloud_pixels = bad
                candidate.valid_pixels = valid
                candidate.cloud_aoi = 100.0 * bad / valid if valid else None
                candidate.qa_status = (
                    "candidate-aoi-quality-reviewed"
                    if valid
                    else "candidate-no-valid-aoi"
                )
                bad_total += bad
                valid_total += valid
            except Exception as exc:
                candidate.cloud_error = f"{type(exc).__name__}: {exc}"
                candidate.qa_status = "candidate-aoi-quality-error"
                eprint(
                    f"AOI quality read failed dataset={dataset} "
                    f"scene={candidate.item.get('id')}: {candidate.cloud_error}"
                )
        acq.cloud_aoi = 100.0 * bad_total / valid_total if valid_total else None


def final_score(dataset: str, acq: Acquisition) -> tuple[Any, ...]:
    missing = acq.cloud_aoi is None and dataset != "sentinel1"
    aoi_cloud = acq.cloud_aoi if acq.cloud_aoi is not None else 1000.0
    return (
        0 if dataset == "sentinel1" or acq.dt.month in DRY_MONTHS else 1,
        missing, aoi_cloud, -acq.coverage_fraction,
        acquisition_pre_score(dataset, acq)[1], acq.day,
    )


def choose_with_spacing(
    dataset: str, acquisitions: list[Acquisition], per_year: int
) -> list[Acquisition]:
    if len(acquisitions) <= per_year:
        return sorted(acquisitions, key=lambda x: x.day)
    if dataset == "sentinel1":
        ordered = sorted(acquisitions, key=lambda x: x.day)
        indexes = (
            {
                round(i * (len(ordered) - 1) / (per_year - 1))
                for i in range(per_year)
            }
            if per_year > 1
            else {len(ordered) // 2}
        )
        return [ordered[i] for i in sorted(indexes)]
    ranked = sorted(acquisitions, key=lambda x: final_score(dataset, x))
    chosen: list[Acquisition] = []
    for candidate in ranked:
        if all(abs((candidate.dt.date() - x.dt.date()).days) >= 20 for x in chosen):
            chosen.append(candidate)
        if len(chosen) == per_year:
            break
    if len(chosen) < per_year:
        for candidate in ranked:
            if candidate not in chosen:
                chosen.append(candidate)
            if len(chosen) == per_year:
                break
    return sorted(chosen, key=lambda x: x.day)


def select_year(
    dataset: str,
    items: list[dict[str, Any]],
    aoi_shape: Any,
    geom4326: dict[str, Any],
    per_year: int,
    quality_pool_multiplier: int,
) -> list[Acquisition]:
    filtered = [item for item in items if prefilter_item(dataset, item)]
    groups = group_acquisitions(filtered, aoi_shape)
    if dataset == "sentinel1":
        return choose_with_spacing(dataset, groups, per_year)
    pool_size = max(per_year * quality_pool_multiplier, per_year)
    pool = sorted(groups, key=lambda x: acquisition_pre_score(dataset, x))[:pool_size]
    assess_aoi_quality(dataset, pool, geom4326)
    return choose_with_spacing(dataset, pool, per_year)


def discovery(
    dataset: str,
    geom4326: dict[str, Any],
    aoi_shape: Any,
    start: date,
    end: date,
    per_year: int,
    page_size: int,
    quality_pool_multiplier: int,
) -> tuple[list[Acquisition], int]:
    check_collection(dataset)
    selected: list[Acquisition] = []
    total_items = 0
    for year in range(start.year, end.year + 1):
        year_start = max(start, date(year, 1, 1))
        year_end = min(end, date(year, 12, 31))
        if year_start > year_end:
            continue
        items = search_year(dataset, geom4326, year_start, year_end, page_size)
        total_items += len(items)
        year_selected = select_year(
            dataset, items, aoi_shape, geom4326, per_year, quality_pool_multiplier
        )
        selected.extend(year_selected)
        print(
            f"{dataset} {year}: discovered={len(items)} "
            f"selected_dates={len(year_selected)} "
            f"selected_scenes={sum(len(x.candidates) for x in year_selected)}"
        )
    return selected, total_items


def is_landsat7_slc_off(item: dict[str, Any]) -> bool:
    props = item.get("properties", {})
    return (
        str(props.get("platform", "")).lower() == "landsat-7"
        and item_datetime(item).date() >= date(2003, 5, 31)
    )


def flatten(acquisitions: Iterable[Acquisition]) -> list[Candidate]:
    return [candidate for acq in acquisitions for candidate in acq.candidates]


def read_existing_catalog(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["scene_id"]: row
            for row in csv.DictReader(handle)
            if row.get("scene_id")
        }


def candidate_row(dataset: str, candidate: Candidate) -> dict[str, Any]:
    item = candidate.item
    props = item.get("properties", {})
    value = props.get("datetime") or props.get("start_datetime")
    utc, bkk = dtpair(value)
    provider = PROVIDERS[dataset]
    flags = [
        f"provider={provider.name}",
        "yearly paginated STAC search",
        f"AOI coverage={candidate.coverage_fraction:.3f}",
    ]
    if dataset in {"sentinel2", "landsat"}:
        flags.append("dry/same-season preference")
        if candidate.cloud_aoi is not None:
            flags.append(f"AOI bad-quality={candidate.cloud_aoi:.2f}%")
        elif candidate.cloud_error:
            flags.append(f"AOI quality unavailable: {candidate.cloud_error}")
    if is_landsat7_slc_off(item):
        flags.append("Landsat-7 SLC-off: gap review required")
        if candidate.qa_status.startswith("candidate"):
            candidate.qa_status = "candidate-slc-off-review"
    scene_cloud = cloud_scene(item)
    return {
        "dataset": dataset,
        "scene_id": item.get("id", ""),
        "sensor": sensor_name(dataset, props),
        "acquisition_datetime_utc": utc,
        "acquisition_datetime_bangkok": bkk,
        "cloud_cover_scene": "" if scene_cloud is None else f"{scene_cloud:.4f}",
        "cloud_cover_aoi": (
            "" if candidate.cloud_aoi is None else f"{candidate.cloud_aoi:.4f}"
        ),
        "tide_station": "",
        "tide_level": "",
        "tide_datum": "",
        "tide_status": "unverified",
        "source_url": item_source_url(item, dataset),
        "source_license": LICENSES[dataset],
        "crs": ANALYSIS_CRS,
        "resolution_m": (
            "10/20"
            if dataset == "sentinel2"
            else ("30" if dataset == "landsat" else "10 pixel spacing (GRD)")
        ),
        "bands": ";".join(x[0] for x in ASSETS[dataset]),
        "local_path": ";".join(candidate.local_paths),
        "file_size_bytes": candidate.file_bytes or "",
        "sha256": ";".join(candidate.checksums),
        "selection_reason": "; ".join(flags),
        "qa_status": candidate.qa_status,
    }


def write_catalog(dataset: str, candidates: list[Candidate], path: Path) -> None:
    previous = read_existing_catalog(path)
    rows = []
    current_ids = set()
    for candidate in candidates:
        row = candidate_row(dataset, candidate)
        current_ids.add(row["scene_id"])
        old = previous.get(row["scene_id"])
        if old and not row["local_path"] and old.get("local_path"):
            for key in ("local_path", "file_size_bytes", "sha256"):
                row[key] = old.get(key, "")
            if old.get("qa_status", "").startswith(("downloaded", "pass", "review")):
                row["qa_status"] = old["qa_status"]
        rows.append(row)
    # Keep metadata for a previously downloaded local sample even when a
    # later narrower search selects a different set of candidate dates. This
    # makes repeated QA/download commands append-safe without retaining every
    # unselected remote candidate forever.
    for scene_id, old in previous.items():
        if scene_id not in current_ids and old.get("local_path"):
            rows.append(old)
    rows.sort(key=lambda x: (x["acquisition_datetime_utc"], x["scene_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapped_grid(
    geom_dst: dict[str, Any], resolution: float
) -> tuple[Any, int, int]:
    from rasterio.transform import from_origin
    from shapely.geometry import shape

    minx, miny, maxx, maxy = shape(geom_dst).bounds
    left = math.floor(minx / resolution) * resolution
    bottom = math.floor(miny / resolution) * resolution
    right = math.ceil(maxx / resolution) * resolution
    top = math.ceil(maxy / resolution) * resolution
    width = max(1, int(round((right - left) / resolution)))
    height = max(1, int(round((top - bottom) / resolution)))
    return from_origin(left, top, resolution, resolution), width, height


def clip_asset(
    href: str,
    geom4326: dict[str, Any],
    outpath: Path,
    *,
    resolution: float,
    categorical: bool,
    tags: dict[str, str],
    dst_crs: str = ANALYSIS_CRS,
) -> Path:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import reproject, transform_geom

    outpath.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(**raster_env()):
        with rasterio.open(href) as src:
            # Sentinel-1 GRD measurement TIFFs commonly carry EPSG:4326 GCPs
            # instead of a dataset-level CRS/affine transform. The branch
            # below passes those GCPs explicitly to rasterio.warp.reproject.
            gcps = None
            gcp_crs = None
            if not src.crs:
                gcps, gcp_crs = src.gcps
                if not gcps or not gcp_crs:
                    raise ValueError(
                        f"Remote asset has neither CRS nor usable GCPs: {href}"
                    )
            geom_dst = transform_geom("EPSG:4326", dst_crs, geom4326)
            transform, width, height = snapped_grid(geom_dst, resolution)
            resampling = Resampling.nearest if categorical else Resampling.bilinear
            nodata = src.nodata if src.nodata is not None else 0
            if gcps:
                # Explicitly pass the GCP grid. Letting WarpedVRT infer a
                # source transform for Sentinel-1 can silently produce a
                # geometrically plausible COG containing scan-line ramps.
                data = np.full((height, width), nodata, dtype=src.dtypes[0])
                reproject(
                    rasterio.band(src, 1),
                    data,
                    gcps=gcps,
                    src_crs=gcp_crs,
                    src_nodata=nodata,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    dst_nodata=nodata,
                    resampling=resampling,
                )
                arr = np.ma.masked_equal(data, nodata)
            else:
                with WarpedVRT(
                    src,
                    crs=dst_crs,
                    transform=transform,
                    width=width,
                    height=height,
                    resampling=resampling,
                    nodata=nodata,
                ) as vrt:
                    arr = vrt.read(1, masked=True)
            inside = geometry_mask(
                [geom_dst], out_shape=(height, width), transform=transform, invert=True
            )
            mask = np.ma.getmaskarray(arr) | ~inside
            data = np.asarray(arr.data).copy()
            data[mask] = nodata
            profile = {
                "driver": "COG",
                "height": height,
                "width": width,
                "count": 1,
                "dtype": src.dtypes[0],
                "crs": dst_crs,
                "transform": transform,
                "nodata": nodata,
                "compress": "DEFLATE",
                "blocksize": 512,
                "overview_resampling": "nearest" if categorical else "average",
                "bigtiff": "IF_SAFER",
            }
            with rasterio.open(outpath, "w", **profile) as dst:
                dst.write(data, 1)
                dst.update_tags(**tags)
    return outpath


def write_preview_sidecar(
    output: Path, dataset: str, item: dict[str, Any], paths: Iterable[Path]
) -> None:
    props = item.get("properties", {})
    value = props.get("datetime") or props.get("start_datetime")
    payload = {
        "dataset": dataset,
        "scene_id": item.get("id"),
        "acquisition_datetime_utc": dtpair(value)[0],
        "source_rasters": [str(x) for x in paths],
        "preview": str(output),
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def preview_outputs(
    dataset: str, candidate: Candidate, band_paths: dict[str, Path]
) -> list[Path]:
    from build_previews import preview

    item = candidate.item
    root = Path("data/previews") / dataset / str(item_datetime(item).year)
    root.mkdir(parents=True, exist_ok=True)
    scene = item["id"]
    outputs: list[Path] = []
    if dataset in {"sentinel2", "landsat"}:
        if dataset == "sentinel2":
            views = {
                "rgb": [band_paths["B4"], band_paths["B3"], band_paths["B2"]],
                "false_color_nir": [
                    band_paths["B8"], band_paths["B4"], band_paths["B3"]
                ],
            }
        else:
            views = {
                "rgb": [
                    band_paths["RED"], band_paths["GREEN"], band_paths["BLUE"]
                ],
                "false_color_nir": [
                    band_paths["NIR"], band_paths["RED"], band_paths["GREEN"]
                ],
            }
        for kind, paths in views.items():
            output = root / f"{scene}_{kind}.png"
            preview([str(x) for x in paths], str(output))
            write_preview_sidecar(output, dataset, item, paths)
            outputs.extend([output, output.with_suffix(output.suffix + ".json")])
    else:
        for band in ("VV", "VH"):
            output = root / f"{scene}_{band.lower()}.png"
            preview([str(band_paths[band])], str(output))
            write_preview_sidecar(output, dataset, item, [band_paths[band]])
            outputs.extend([output, output.with_suffix(output.suffix + ".json")])
    return outputs


def download_acquisitions(
    dataset: str,
    acquisitions: list[Acquisition],
    geom4326: dict[str, Any],
    max_downloads: int | None,
    overwrite: bool = False,
) -> list[Path]:
    selected = acquisitions[:max_downloads] if max_downloads else acquisitions
    downloaded: list[Path] = []
    for index, acq in enumerate(selected, 1):
        print(
            f"download acquisition {index}/{len(selected)} dataset={dataset} "
            f"date={acq.day} scenes={len(acq.candidates)}"
        )
        for candidate in acq.candidates:
            item = sign_item(candidate.item, dataset)
            props = item.get("properties", {})
            value = props.get("datetime") or props.get("start_datetime")
            utc, _ = dtpair(value)
            year = str(item_datetime(item).year)
            scene_dir = Path("data/satellite") / dataset / year / item["id"]
            band_paths: dict[str, Path] = {}
            for band_name, asset_key, resolution, categorical in ASSETS[dataset]:
                asset = item.get("assets", {}).get(asset_key)
                if not asset:
                    raise KeyError(f"Missing asset {asset_key!r} in {item.get('id')}")
                outpath = scene_dir / f"{band_name}_{int(resolution)}m.tif"
                if outpath.exists() and outpath.stat().st_size > 0 and not overwrite:
                    print(f"  {item['id']} {band_name}: reuse existing {outpath}")
                else:
                    print(f"  {item['id']} {band_name}: AOI window -> {outpath}")
                    clip_asset(
                        asset["href"],
                        geom4326,
                        outpath,
                        resolution=resolution,
                        categorical=categorical,
                        tags={
                            "dataset": dataset,
                            "scene_id": item["id"],
                            "band": band_name,
                            "acquisition_datetime_utc": utc,
                            "native_resolution_m": str(int(resolution)),
                            "source_url": item_source_url(candidate.item, dataset),
                            "source_license": LICENSES[dataset],
                            "tide_status": "unverified",
                        },
                    )
                digest = sha256(outpath)
                candidate.local_paths.append(str(outpath))
                candidate.checksums.append(f"{outpath.name}:{digest}")
                candidate.file_bytes += outpath.stat().st_size
                band_paths[band_name] = outpath
                downloaded.append(outpath)
            downloaded.extend(preview_outputs(dataset, candidate, band_paths))
            candidate.qa_status = "downloaded-pending-raster-validation"
    return downloaded


def estimate_bytes(
    dataset: str, acquisitions: list[Acquisition], aoi_shape: Any
) -> int:
    from pyproj import Transformer
    from shapely.ops import transform

    project = Transformer.from_crs(
        "EPSG:4326", ANALYSIS_CRS, always_xy=True
    ).transform
    area_m2 = transform(project, aoi_shape).area
    per_acquisition = sum(
        area_m2 / (resolution * resolution) * 2
        for _, _, resolution, _ in ASSETS[dataset]
    )
    factor = sum(
        max(1.0, sum(c.coverage_fraction for c in acq.candidates))
        for acq in acquisitions
    )
    return int(per_acquisition * factor)


def output_files() -> list[Path]:
    paths: list[Path] = []
    for root in (Path("data/satellite"), Path("data/previews")):
        if root.exists():
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.name.lower() not in {"readme.md", ".ds_store"}
            )
    return sorted(paths)


def update_manifests(git_lfs_status: str | None = None) -> None:
    manifest_path = Path("data/manifests/dataset_manifest.json")
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    records = []
    checksums = []
    total = 0
    for path in output_files():
        digest = sha256(path)
        size = path.stat().st_size
        total += size
        records.append({"path": str(path), "size_bytes": size, "sha256": digest})
        checksums.append(f"{digest}  {path}\n")
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    manifest["local_dataset_bytes"] = total
    manifest["files"] = records
    if git_lfs_status is not None:
        manifest["git_lfs_status"] = git_lfs_status
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    Path("data/manifests/checksums.sha256").write_text(
        "".join(checksums), encoding="utf-8"
    )


def default_start(dataset: str) -> date:
    return {
        "sentinel2": date(2016, 1, 1),
        "landsat": date(1984, 1, 1),
        "sentinel1": date(2015, 1, 1),
    }[dataset]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Yearly paginated STAC discovery and AOI-only COG acquisition"
    )
    parser.add_argument("dataset", choices=PROVIDERS)
    parser.add_argument("--aoi", default="data/aoi/samut_songkhram_aoi.geojson")
    parser.add_argument("--start", type=parse_cli_date)
    parser.add_argument(
        "--end", type=parse_cli_date, default=datetime.now(timezone.utc).date()
    )
    parser.add_argument("--per-year", type=int, default=4)
    parser.add_argument("--catalog")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--quality-pool-multiplier", type=int, default=3)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Search/rank/catalog only")
    mode.add_argument("--download", action="store_true", help="Download selected AOI bands")
    parser.add_argument(
        "--max-downloads",
        type=int,
        help="Maximum acquisition dates; all required intersecting tiles are retained",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recreate existing AOI COGs instead of resuming from them",
    )
    args = parser.parse_args()
    if args.per_year < 1:
        parser.error("--per-year must be >= 1")
    if not 1 <= args.page_size <= 1000:
        parser.error("--page-size must be between 1 and 1000")
    if args.quality_pool_multiplier < 1:
        parser.error("--quality-pool-multiplier must be >= 1")
    if args.max_downloads is not None and args.max_downloads < 1:
        parser.error("--max-downloads must be >= 1")

    dry_run = args.dry_run or not args.download
    start = args.start or default_start(args.dataset)
    end = args.end
    if start > end:
        parser.error("--start must not be after --end")

    geom4326, aoi_shape = load_aoi(Path(args.aoi))
    provider = PROVIDERS[args.dataset]
    print(
        f"dataset={args.dataset} provider={provider.name} "
        f"collection={provider.collection} mode={'dry-run' if dry_run else 'download'}"
    )
    acquisitions, discovered = discovery(
        args.dataset,
        geom4326,
        aoi_shape,
        start,
        end,
        args.per_year,
        args.page_size,
        args.quality_pool_multiplier,
    )
    estimate = estimate_bytes(args.dataset, acquisitions, aoi_shape)
    print(
        f"estimated_uncompressed_AOI_bytes={estimate} "
        f"({estimate / 1024**3:.2f} GiB) "
        f"target_limit={MAX_WORKING_BYTES / 1024**3:.0f} GiB"
    )
    if not dry_run and estimate > MAX_WORKING_BYTES and not args.max_downloads:
        raise SystemExit(
            "Estimated working set exceeds 15 GiB. "
            "Reduce --per-year or use --max-downloads."
        )
    if not dry_run:
        download_acquisitions(
            args.dataset,
            acquisitions,
            geom4326,
            args.max_downloads,
            overwrite=args.overwrite,
        )
        update_manifests()

    candidates = flatten(acquisitions)
    catalog = Path(args.catalog or f"data/catalog/{args.dataset}_scenes.csv")
    write_catalog(args.dataset, candidates, catalog)
    print(
        f"{args.dataset}: discovered={discovered} "
        f"selected_dates={len(acquisitions)} selected_scenes={len(candidates)} "
        f"catalog={catalog}"
    )
    if dry_run:
        print("Dry-run complete: no raster downloaded; tide_status remains unverified.")


if __name__ == "__main__":
    main()
