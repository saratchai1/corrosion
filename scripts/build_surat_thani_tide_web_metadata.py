#!/usr/bin/env python3
"""Publish conservative Ko Prap tide metadata into the Surat Thani web dataset."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MSL_MATCH = ROOT / "data/catalog/surat_thani_mvp_optical_scenes_tide_msl.csv"
PHASE_2023 = ROOT / "data/tide/surat_thani/ko_prap_2023_selected_scene_phase.csv"
SCENE_STAGE = ROOT / "data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026.csv"
SCENE_STAGE_MANIFEST = ROOT / "data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026_manifest.json"
MSL_MANIFEST = ROOT / "data/tide/surat_thani/ko_prap_hourly_msl_manifest.json"
OUTS = [
    ROOT / "data/processed/surat_thani/web/tide_context.json",
    ROOT / "web/public/data/surat_thani/tide_context.json",
]


def rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fnum(value: str | None):
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def patch_json(path: Path, payload_update: dict[str, object]) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(payload_update)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def stage_context(row: dict[str, str]) -> dict[str, object]:
    return {
        "scene_id": row.get("scene_id"),
        "acquisition_datetime_bangkok": row.get("acquisition_datetime_bangkok"),
        "stage": row.get("stage"),
        "phase_0_1": fnum(row.get("phase_0_1")),
        "phase_status": row.get("phase_status"),
        "previous_extrema_datetime_bangkok": row.get("previous_extrema_datetime_bangkok") or None,
        "next_extrema_datetime_bangkok": row.get("next_extrema_datetime_bangkok") or None,
        "extrema_datum": row.get("extrema_datum") or None,
        "tide_m_msl": fnum(row.get("tide_m_msl")),
        "msl_method": row.get("msl_method") or None,
        "source_type": row.get("source_type"),
        "source_url": row.get("source_url"),
        "source_status": row.get("source_status"),
        "note": row.get("note"),
    }


def main() -> int:
    msl_rows = rows(MSL_MATCH)
    old_phase_rows = rows(PHASE_2023)
    stage_rows = rows(SCENE_STAGE)
    manifest = json.loads(MSL_MANIFEST.read_text(encoding="utf-8")) if MSL_MANIFEST.exists() else {}
    stage_manifest = json.loads(SCENE_STAGE_MANIFEST.read_text(encoding="utf-8")) if SCENE_STAGE_MANIFEST.exists() else {}

    s2_2026 = [
        r for r in msl_rows
        if r.get("dataset") == "sentinel2"
        and r.get("acquisition_datetime_bangkok", "").startswith("2026-")
        and r.get("tide_status", "").startswith("predicted_")
    ]
    by_year = {str(year): [r for r in stage_rows if r.get("year") == str(year)] for year in range(2023, 2027)}

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "station": {
            "name": "Ko Prap",
            "name_th": "เกาะปราบ",
            "coordinates_lon_lat": [99.434444, 9.265],
            "distance_from_project_centroid_km": 23.96,
            "role": "supporting tide-screening reference; not an in-plot gauge"
        },
        "datum_relationship": {
            "lowest_low_water_below_mean_sea_level_m": 1.43,
            "source": "Royal Thai Navy 2026 Tide Tables",
            "warning": "Do not mix Chart Datum/LLW and MSL heights without an explicit datum treatment. The 2025 public extrema are kept as stage context and are not converted to MSL."
        },
        "public_monthly_url_templates": stage_manifest.get("public_url_templates", {}),
        "coverage": {
            "2023": {
                "status": "OFFICIAL_EXTREMA_PHASE_FOR_SELECTED_SCENES",
                "selected_scene_count": len(by_year["2023"]),
                "phase_resolved_count": sum(bool(r.get("phase_0_1")) for r in by_year["2023"]),
                "numeric_height_use": "NO_CROSS_YEAR_MSL_COMPARISON",
                "source_url": "https://www.hydro.navy.mi.th/tide66/KP2023.pdf"
            },
            "2024": {
                "status": "SCENE_LEVEL_OFFICIAL_RTN_MSL_WITH_PARTIAL_EXTREMA_PHASE",
                "selected_scene_count": len(by_year["2024"]),
                "msl_resolved_count": sum(bool(r.get("tide_m_msl")) for r in by_year["2024"]),
                "phase_resolved_count": sum(bool(r.get("phase_0_1")) for r in by_year["2024"]),
                "datum": "MSL for official hourly scene values; Chart Datum only where public extrema are cited",
                "archive_status": "official historical PDF URL is non-live; indexed RTN content retained with explicit provenance"
            },
            "2025": {
                "status": "PUBLIC_EXTREMA_STAGE_PHASE_FOR_SELECTED_SCENES",
                "selected_scene_count": len(by_year["2025"]),
                "phase_resolved_count": sum(bool(r.get("phase_0_1")) for r in by_year["2025"]),
                "extrema_datum": "CHART_DATUM",
                "numeric_height_use": "STAGE_CONTEXT_ONLY_NO_MSL_CONVERSION"
            },
            "2026": {
                "status": "OFFICIAL_HOURLY_MSL_PLUS_PUBLIC_EXTREMA_PHASE",
                "datum": "MSL for official hourly scene values; Chart Datum for public extrema timing",
                "hourly_rows": manifest.get("row_count", 0),
                "matched_selected_sentinel2_scenes": len(s2_2026),
                "phase_resolved_count": sum(bool(r.get("phase_0_1")) for r in by_year["2026"]),
                "source_url": "https://hydro.navy.mi.th/storage/frontend/article/23019/file/th/KP2026msl.pdf"
            }
        },
        "selected_scene_context": {
            year: [stage_context(r) for r in by_year[year]]
            for year in ["2023", "2024", "2025", "2026"]
        },
        "waterline_gate": {
            "status": "SCENE_LEVEL_TIDE_CONTEXT_2023_2026_PARTIAL_MSL",
            "reason": "All selected 2023-2026 Sentinel-2 scenes now have at least tide-stage/direction context. 2024 and 2026 have scene-level official MSL values; 2025 has sourced Chart-Datum extrema phase only, so the series is still not fully MSL-normalized.",
            "allowed_claim": "Use scene-level tide stage to screen/reselect image-derived waterline observations and run a tide-stage sensitivity analysis.",
            "not_allowed_claim": "Do not call the 2023-2026 waterline series fully tide-normalized or attribute shoreline change to planting from tide metadata alone."
        },
        "primary_indicator_note": "Mangrove edge and bank edge remain primary where visible; waterline is supporting only.",
        "provenance_note": "ThailandTideTables station 466 pages label heights as Chart Datum and cite World Tides / Royal Thai Navy Hydrographic Department. CI does not scrape the site; sourced scene-level values are committed with provenance.",
        "legacy_2023_phase_row_count": len(old_phase_rows)
    }

    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    patch = {
        "tide_status": "scene_level_tide_context_partial_msl",
        "tide_context_file": "tide_context.json",
        "tide_context_status": payload["waterline_gate"]["status"],
        "tide_context_note": payload["waterline_gate"]["reason"],
        "tide_disclaimer": "Scene-level tide stage is available for 2023-2026, but the water-land boundary series is not fully MSL-normalized; waterline remains supporting evidence."
    }
    for path in [
        ROOT / "data/processed/surat_thani/web/index.json",
        ROOT / "web/public/data/surat_thani/index.json",
        ROOT / "data/processed/surat_thani/web/summary.json",
        ROOT / "web/public/data/surat_thani/summary.json",
    ]:
        patch_json(path, patch)

    print(json.dumps({
        "scene_stage_counts": {year: len(by_year[year]) for year in by_year},
        "2026_msl_scenes": len(s2_2026),
        "status": payload["waterline_gate"]["status"],
        "outputs": [str(p.relative_to(ROOT)) for p in OUTS],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
