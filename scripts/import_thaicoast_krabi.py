#!/usr/bin/env python3
"""Import the published ThaiCoast Krabi DSAS point dataset from OSF.

Source project: https://osf.io/mxjhk/

The script downloads only the small shapefile sidecars and text export listed in
our verified OSF inventory. It does not download the ~795 MiB personal
gatabase. The output preserves source fields, converts geometry to EPSG:4326,
chooses a published rate field only when one can be identified from the schema,
and records all provenance/validation details.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

import requests
import shapefile  # pyshp
from pyproj import CRS, Transformer
from shapely.geometry import shape as shapely_shape
from shapely.ops import transform as shapely_transform

INVENTORY_DEFAULT = Path(
    "regions/krabi/data/published/thaicoast_osf_inventory.json"
)
OUT_DEFAULT = Path("regions/krabi/web/assets/published")
REQUIRED_NAMES = [
    "Krabi_Points.shp",
    "Krabi_Points.shx",
    "Krabi_Points.dbf",
    "Krabi_Points.prj",
    "Krabi_Points.cpg",
]
OPTIONAL_NAMES = [
    "Krabi_erosion.txt",
    "Krabi_erosion.txt.xml",
    "Krabi_Points.shp.xml",
]
USER_AGENT = "corrosion-thaicoast-krabi-import/1.0"
RATE_PRIORITY = [
    "lrr",
    "wlr",
    "epr",
    "rate",
    "slope",
    "linearregressionrate",
    "endpointrate",
    "nsm",
]
ID_PRIORITY = [
    "transectid",
    "transorder",
    "transect",
    "objectid",
    "fid",
    "id",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "null", "none", "n/a", "na"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def find_inventory_entry(inventory: dict[str, Any], name: str) -> dict[str, Any] | None:
    matches = [
        entry
        for entry in inventory.get("files", [])
        if str(entry.get("name") or "").lower() == name.lower()
        and "krabi" in str(entry.get("materialized_path") or "").lower()
    ]
    if not matches:
        return None
    # Prefer the compact Erosion rates directory rather than duplicate copies.
    matches.sort(
        key=lambda item: (
            0 if "/Erosion rates/" in str(item.get("materialized_path")) else 1,
            len(str(item.get("materialized_path") or "")),
        )
    )
    return matches[0]


def download_entry(session: requests.Session, entry: dict[str, Any], destination: Path) -> dict[str, Any]:
    url = entry.get("download")
    if not url:
        raise ValueError(f"Inventory entry has no download URL: {entry}")
    response = session.get(url, timeout=240, allow_redirects=True)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    expected_size = entry.get("size")
    if expected_size is not None and destination.stat().st_size != int(expected_size):
        raise RuntimeError(
            f"Size mismatch for {destination.name}: got {destination.stat().st_size}, expected {expected_size}"
        )
    digest = sha256(destination)
    expected_sha = entry.get("sha256")
    if expected_sha and digest.lower() != str(expected_sha).lower():
        raise RuntimeError(
            f"SHA-256 mismatch for {destination.name}: got {digest}, expected {expected_sha}"
        )
    return {
        "name": destination.name,
        "source_path": entry.get("materialized_path"),
        "source_download": url,
        "resolved_url": response.url,
        "bytes": destination.stat().st_size,
        "sha256": digest,
        "inventory_sha256": expected_sha,
        "inventory_md5": entry.get("md5"),
    }


def read_encoding(cpg_path: Path) -> str:
    raw = cpg_path.read_text(encoding="ascii", errors="ignore").strip()
    if not raw:
        return "utf-8"
    aliases = {
        "UTF-8": "utf-8",
        "UTF8": "utf-8",
        "1252": "cp1252",
        "WINDOWS-1252": "cp1252",
        "874": "cp874",
        "WINDOWS-874": "cp874",
    }
    return aliases.get(raw.upper(), raw)


def parse_text_export(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    decoded = None
    used_encoding = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            decoded = raw.decode(encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        decoded = raw.decode("latin-1", errors="replace")
        used_encoding = "latin-1-replace"
    nonempty = [line for line in decoded.splitlines() if line.strip()]
    preview = nonempty[:12]
    rows: list[dict[str, Any]] = []
    fieldnames: list[str] = []
    delimiter = None
    if nonempty:
        sample = "\n".join(nonempty[:20])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
            reader = csv.DictReader(nonempty, dialect=dialect)
            fieldnames = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
        except csv.Error:
            delimiter = None
    return {
        "encoding": used_encoding,
        "delimiter": delimiter,
        "fieldnames": fieldnames,
        "row_count": len(rows),
        "preview_lines": preview,
        "rows": rows,
    }


def field_statistics(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    if not records:
        return stats
    for field in records[0].keys():
        values = [as_number(row.get(field)) for row in records]
        numbers = [value for value in values if value is not None]
        nonnull = [row.get(field) for row in records if row.get(field) not in (None, "")]
        unique_preview = []
        seen = set()
        for value in nonnull:
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            unique_preview.append(value)
            if len(unique_preview) >= 8:
                break
        entry: dict[str, Any] = {
            "nonnull_count": len(nonnull),
            "numeric_count": len(numbers),
            "unique_count": len({str(value) for value in nonnull}),
            "sample_values": unique_preview,
        }
        if numbers:
            entry.update(
                {
                    "minimum": min(numbers),
                    "maximum": max(numbers),
                    "mean": mean(numbers),
                    "median": median(numbers),
                    "negative_count": sum(value < 0 for value in numbers),
                    "positive_count": sum(value > 0 for value in numbers),
                    "zero_count": sum(value == 0 for value in numbers),
                }
            )
        stats[field] = entry
    return stats


def select_field(fields: list[str], stats: dict[str, dict[str, Any]], priorities: list[str]) -> str | None:
    normalized = {field: normalize(field) for field in fields}
    for target in priorities:
        exact = [field for field, key in normalized.items() if key == target]
        for field in exact:
            if stats.get(field, {}).get("numeric_count", 0) > 0:
                return field
    for target in priorities:
        partial = [field for field, key in normalized.items() if target in key]
        for field in partial:
            if stats.get(field, {}).get("numeric_count", 0) > 0:
                return field
    return None


def select_id_field(fields: list[str], rows: list[dict[str, Any]]) -> str | None:
    normalized = {field: normalize(field) for field in fields}
    for target in ID_PRIORITY:
        for field, key in normalized.items():
            if key != target and target not in key:
                continue
            values = [str(row.get(field)).strip() for row in rows if row.get(field) not in (None, "")]
            if values and len(set(values)) == len(values):
                return field
    return None


def join_text_rows(
    shape_records: list[dict[str, Any]],
    text_data: dict[str, Any],
) -> dict[str, Any]:
    rows = text_data.get("rows") or []
    if not rows or not shape_records:
        return {"joined": False, "reason": "no parsed text rows"}
    shape_id = select_id_field(list(shape_records[0].keys()), shape_records)
    text_id = select_id_field(list(rows[0].keys()), rows)
    if not shape_id or not text_id:
        if len(rows) == len(shape_records):
            for shape_record, text_row in zip(shape_records, rows):
                for key, value in text_row.items():
                    shape_record.setdefault(f"txt_{key}", value)
            return {
                "joined": True,
                "method": "row_order_equal_length",
                "shape_rows": len(shape_records),
                "text_rows": len(rows),
            }
        return {
            "joined": False,
            "reason": "no unique identifier and row counts differ",
            "shape_rows": len(shape_records),
            "text_rows": len(rows),
            "shape_id_candidate": shape_id,
            "text_id_candidate": text_id,
        }
    lookup = {
        str(row.get(text_id)).strip(): row
        for row in rows
        if row.get(text_id) not in (None, "")
    }
    matched = 0
    for shape_record in shape_records:
        key = str(shape_record.get(shape_id)).strip()
        text_row = lookup.get(key)
        if not text_row:
            continue
        matched += 1
        for field, value in text_row.items():
            shape_record.setdefault(f"txt_{field}", value)
    return {
        "joined": matched > 0,
        "method": "unique_identifier",
        "shape_id": shape_id,
        "text_id": text_id,
        "matched": matched,
        "shape_rows": len(shape_records),
        "text_rows": len(rows),
    }


def rate_class(rate: float | None) -> str:
    if rate is None:
        return "NO_RATE"
    if rate <= -2.0:
        return "STRONG_RETREAT"
    if rate < -0.5:
        return "RETREAT"
    if rate <= 0.5:
        return "RELATIVELY_STABLE"
    if rate < 2.0:
        return "ACCRETION"
    return "STRONG_ACCRETION"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INVENTORY_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--work", type=Path, default=Path(".tmp/thaicoast_krabi"))
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    downloads = []
    entries: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_NAMES + OPTIONAL_NAMES:
        entry = find_inventory_entry(inventory, name)
        if not entry:
            if name in REQUIRED_NAMES:
                raise RuntimeError(f"Required OSF file not found in inventory: {name}")
            continue
        entries[name] = entry
        downloads.append(download_entry(session, entry, args.work / name))

    encoding = read_encoding(args.work / "Krabi_Points.cpg")
    reader = shapefile.Reader(str(args.work / "Krabi_Points"), encoding=encoding)
    field_defs = [
        {
            "name": field[0],
            "type": field[1],
            "size": field[2],
            "decimal": field[3],
        }
        for field in reader.fields[1:]
    ]
    field_names = [field["name"] for field in field_defs]
    records = [dict(zip(field_names, list(record))) for record in reader.records()]
    source_shapes = list(reader.shapes())
    if len(records) != len(source_shapes):
        raise RuntimeError(
            f"Shape/record count mismatch: {len(source_shapes)} vs {len(records)}"
        )

    prj_text = (args.work / "Krabi_Points.prj").read_text(
        encoding="utf-8", errors="replace"
    )
    source_crs = CRS.from_wkt(prj_text)
    target_crs = CRS.from_epsg(4326)
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

    text_data = (
        parse_text_export(args.work / "Krabi_erosion.txt")
        if (args.work / "Krabi_erosion.txt").exists()
        else {"rows": [], "fieldnames": [], "preview_lines": []}
    )
    join_report = join_text_rows(records, text_data)
    stats = field_statistics(records)
    all_fields = list(records[0].keys()) if records else field_names
    primary_rate_field = select_field(all_fields, stats, RATE_PRIORITY)

    features = []
    invalid_geometry = 0
    for index, (source_shape, properties) in enumerate(zip(source_shapes, records), 1):
        geom = shapely_shape(source_shape.__geo_interface__)
        geom = shapely_transform(transformer.transform, geom)
        if geom.is_empty or not geom.is_valid:
            invalid_geometry += 1
            continue
        props = dict(properties)
        rate = as_number(props.get(primary_rate_field)) if primary_rate_field else None
        props.update(
            {
                "source_feature_index": index,
                "published_primary_rate_field": primary_rate_field,
                "published_primary_rate_m_per_year": rate,
                "dashboard_rate_class": rate_class(rate),
                "dashboard_classification_note": (
                    "Display convention only; source numeric value is preserved. "
                    "Not an official DMCR class."
                ),
                "published_period": "1990-2019",
                "published_dataset": "Shoreline ThaiCoast / Krabi_Points",
            }
        )
        features.append(
            {
                "type": "Feature",
                "id": index,
                "properties": props,
                "geometry": geom.__geo_interface__,
            }
        )

    if not features:
        raise RuntimeError("No valid Krabi point geometry was imported")
    coords = [feature["geometry"]["coordinates"] for feature in features]
    lons = [float(coord[0]) for coord in coords]
    lats = [float(coord[1]) for coord in coords]
    bounds = [min(lons), min(lats), max(lons), max(lats)]
    if bounds[0] < 97.5 or bounds[2] > 100.5 or bounds[1] < 6.0 or bounds[3] > 10.0:
        raise RuntimeError(f"Imported points do not plausibly overlap Krabi: {bounds}")

    rate_values = [
        feature["properties"].get("published_primary_rate_m_per_year")
        for feature in features
        if feature["properties"].get("published_primary_rate_m_per_year") is not None
    ]
    class_counts = Counter(
        feature["properties"]["dashboard_rate_class"] for feature in features
    )
    geojson = {
        "type": "FeatureCollection",
        "name": "krabi_published_dsas_points_1990_2019",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    geojson_path = args.out / "krabi_published_dsas_points.geojson"
    geojson_path.write_text(
        json.dumps(geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    summary = {
        "generated_utc": now_utc(),
        "status": "PUBLISHED_HISTORICAL_DSAS_POINTS_IMPORTED",
        "source_project": inventory.get("source_project"),
        "published_period": "1990-2019",
        "feature_count": len(features),
        "invalid_geometry_count": invalid_geometry,
        "source_crs": source_crs.to_string(),
        "target_crs": "EPSG:4326",
        "bounds_wgs84": bounds,
        "primary_rate_field": primary_rate_field,
        "rate_count": len(rate_values),
        "rate_minimum": min(rate_values) if rate_values else None,
        "rate_maximum": max(rate_values) if rate_values else None,
        "rate_mean": mean(rate_values) if rate_values else None,
        "rate_median": median(rate_values) if rate_values else None,
        "dashboard_rate_class_counts": dict(sorted(class_counts.items())),
        "text_join": join_report,
        "interpretation": {
            "valid_for": [
                "published 1990-2019 historical shoreline-rate context",
                "province-scale hotspot screening",
            ],
            "not_valid_for": [
                "claiming current 2026 shoreline status",
                "replacing local tide-normalized monitoring",
            ],
        },
    }
    (args.out / "krabi_published_dsas_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    schema = {
        "shapefile_encoding": encoding,
        "field_definitions": field_defs,
        "field_statistics": stats,
        "text_export": {
            key: value for key, value in text_data.items() if key != "rows"
        },
        "text_join": join_report,
        "selected_primary_rate_field": primary_rate_field,
    }
    (args.out / "krabi_published_dsas_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    source_manifest = {
        "generated_utc": now_utc(),
        "source_project": inventory.get("source_project"),
        "inventory_generated_utc": inventory.get("generated_utc"),
        "downloads": downloads,
        "output": {
            "geojson": geojson_path.name,
            "geojson_sha256": sha256(geojson_path),
            "summary": "krabi_published_dsas_summary.json",
            "schema": "krabi_published_dsas_schema.json",
        },
    }
    (args.out / "krabi_published_dsas_source_manifest.json").write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                **summary,
                "field_names": all_fields,
                "numeric_fields": [
                    field
                    for field, entry in stats.items()
                    if entry.get("numeric_count", 0) > 0
                ],
                "text_fieldnames": text_data.get("fieldnames"),
                "text_preview": text_data.get("preview_lines"),
                "geojson": str(geojson_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
