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


def patch_json(path: Path, payload_update: dict[str, object]) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(payload_update)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    msl_rows = rows(MSL_MATCH)
    phase_rows = rows(PHASE_2023)
    manifest = json.loads(MSL_MANIFEST.read_text(encoding="utf-8")) if MSL_MANIFEST.exists() else {}

    s2_2026 = [
        r for r in msl_rows
        if r.get("dataset") == "sentinel2"
        and r.get("acquisition_datetime_bangkok", "").startswith("2026-")
        and r.get("tide_status", "").startswith("predicted_")
    ]
    phase_by_scene = {r["scene_id"]: r for r in phase_rows if r.get("scene_id")}

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
            "warning": "Do not mix LLW and MSL heights without an explicit datum treatment."
        },
        "coverage": {
            "2023": {
                "status": "OFFICIAL_EXTREMA_PHASE_FOR_SELECTED_SCENES",
                "datum": "LOWEST_LOW_WATER",
                "selected_scene_count": len(phase_rows),
                "numeric_height_use": "NO_CROSS_YEAR_MSL_COMPARISON",
                "source_url": "https://www.hydro.navy.mi.th/tide66/KP2023.pdf"
            },
            "2024": {"status": "HOURLY_MSL_NOT_YET_REPRODUCIBLY_AVAILABLE"},
            "2025": {"status": "HOURLY_MSL_NOT_YET_REPRODUCIBLY_AVAILABLE"},
            "2026": {
                "status": "OFFICIAL_HOURLY_MSL_MATCHED",
                "datum": "MSL",
                "hourly_rows": manifest.get("row_count", 0),
                "matched_selected_sentinel2_scenes": len(s2_2026),
                "source_url": "https://hydro.navy.mi.th/storage/frontend/article/23019/file/th/KP2026msl.pdf"
            }
        },
        "selected_scene_context": {
            "2023": [
                {
                    "scene_id": r.get("scene_id"),
                    "acquisition_datetime_bangkok": r.get("acquisition_datetime_bangkok"),
                    "stage": r.get("stage"),
                    "phase_0_1": float(r["phase_0_1"]) if r.get("phase_0_1") else None,
                    "previous_extrema_datetime_bangkok": r.get("previous_extrema_datetime_bangkok"),
                    "next_extrema_datetime_bangkok": r.get("next_extrema_datetime_bangkok"),
                    "datum": r.get("datum")
                }
                for r in phase_rows
            ],
            "2026": [
                {
                    "scene_id": r.get("scene_id"),
                    "acquisition_datetime_bangkok": r.get("acquisition_datetime_bangkok"),
                    "tide_m_msl": float(r["tide_level"]) if r.get("tide_level") else None,
                    "match_method": r.get("tide_match_method"),
                    "datum": r.get("tide_datum")
                }
                for r in s2_2026
            ]
        },
        "waterline_gate": {
            "status": "PARTIAL_TIDE_CONTEXT_ONLY",
            "reason": "2023 selected scenes have official LLW tide phase and 2026 selected scenes have official hourly MSL; reproducible hourly MSL is still missing for 2024-2025.",
            "allowed_claim": "Use tide context to screen image-derived waterline observations.",
            "not_allowed_claim": "Do not call the 2023-2026 waterline series fully tide-normalized or attribute shoreline change to planting from tide metadata alone."
        },
        "primary_indicator_note": "Mangrove edge and bank edge remain primary where visible; waterline is supporting only."
    }

    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    patch = {
        "tide_context_file": "tide_context.json",
        "tide_context_status": payload["waterline_gate"]["status"],
        "tide_context_note": payload["waterline_gate"]["reason"],
    }
    for path in [
        ROOT / "data/processed/surat_thani/web/index.json",
        ROOT / "web/public/data/surat_thani/index.json",
        ROOT / "data/processed/surat_thani/web/summary.json",
        ROOT / "web/public/data/surat_thani/summary.json",
    ]:
        patch_json(path, patch)

    print(json.dumps({
        "2023_phase_scenes": len(phase_by_scene),
        "2026_msl_scenes": len(s2_2026),
        "status": payload["waterline_gate"]["status"],
        "outputs": [str(p.relative_to(ROOT)) for p in OUTS],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
