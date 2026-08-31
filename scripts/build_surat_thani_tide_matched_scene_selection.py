#!/usr/bin/env python3
"""Select one tide-stage-constrained Sentinel-2 scene per year for 2023-2026.

The baseline MVP composites three February-April scenes per year and therefore mixes
rising/falling tide states. This secondary sensitivity analysis keeps the baseline
unchanged and selects a single scene per year, preferring the 2023 pre-intervention
stage: rising tide near the median 2023 relative phase.

2024-02 has official RTN hourly MSL direction but unresolved extrema phase. It can still
win over known falling scenes, but its match strength is explicitly marked weaker.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/catalog/surat_thani_mvp_optical_scenes.csv"
STAGE = ROOT / "data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026.csv"
OUT_CATALOG = ROOT / "data/catalog/surat_thani_tide_matched_optical_scenes.csv"
OUT_EPOCHS = ROOT / "data/catalog/surat_thani_tide_matched_epochs.json"
OUT_SELECTION = ROOT / "data/analysis/surat_thani/tide_matched_scene_selection.json"
YEARS = [2023, 2024, 2025, 2026]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fnum(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def aoi_bad_quality(row: dict[str, str]) -> float:
    text = row.get("selection_reason", "")
    token = "AOI bad-quality="
    if token not in text:
        return 100.0
    try:
        return float(text.split(token, 1)[1].split("%", 1)[0])
    except (ValueError, IndexError):
        return 100.0


def main() -> int:
    catalog = read_csv(CATALOG)
    stage_rows = read_csv(STAGE)
    catalog_by_scene = {r.get("scene_id"): r for r in catalog if r.get("scene_id")}

    pre_phases = [
        fnum(r.get("phase_0_1"))
        for r in stage_rows
        if r.get("year") == "2023" and r.get("stage") == "RISING"
    ]
    pre_phases = [v for v in pre_phases if v is not None]
    if not pre_phases:
        raise SystemExit("no resolved 2023 rising phases")
    target_phase = float(median(pre_phases))
    target_stage = "RISING"

    selected: list[dict[str, object]] = []
    selected_catalog_rows: list[dict[str, str]] = []

    for year in YEARS:
        candidates = [r for r in stage_rows if r.get("year") == str(year)]
        if not candidates:
            raise SystemExit(f"no tide-stage candidates for {year}")
        scored = []
        for row in candidates:
            scene_id = row.get("scene_id", "")
            cat = catalog_by_scene.get(scene_id)
            if cat is None:
                continue
            phase = fnum(row.get("phase_0_1"))
            stage = row.get("stage") or "UNKNOWN"
            direction_penalty = 0.0 if stage == target_stage else 2.0
            phase_penalty = abs(phase - target_phase) if phase is not None else 0.35
            quality_penalty = min(aoi_bad_quality(cat) / 1000.0, 0.2)
            score = direction_penalty + phase_penalty + quality_penalty
            scored.append((score, phase is None, cat.get("acquisition_datetime_bangkok", ""), row, cat))
        if not scored:
            raise SystemExit(f"no catalog-backed tide candidates for {year}")
        scored.sort(key=lambda x: (x[0], x[1], x[2]))
        score, phase_missing, _, tide, cat = scored[0]
        phase = fnum(tide.get("phase_0_1"))
        selected_catalog_rows.append(cat)
        selected.append({
            "year": year,
            "scene_id": tide.get("scene_id"),
            "acquisition_datetime_bangkok": tide.get("acquisition_datetime_bangkok"),
            "stage": tide.get("stage"),
            "phase_0_1": phase,
            "tide_m_msl": fnum(tide.get("tide_m_msl")),
            "match_strength": "DIRECTION_AND_PHASE" if phase is not None else "DIRECTION_ONLY_PHASE_UNRESOLVED",
            "target_stage": target_stage,
            "target_phase_0_1": round(target_phase, 6),
            "selection_score_lower_is_better": round(float(score), 6),
            "aoi_bad_quality_percent": round(aoi_bad_quality(cat), 4),
            "source_url": tide.get("source_url"),
            "selection_reason": (
                "Prefer rising stage; then minimize absolute relative-phase difference from median 2023 rising phase; "
                "use a small AOI quality penalty. An unresolved phase receives a conservative 0.35 phase penalty."
            ),
        })

    OUT_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(catalog[0].keys())
    with OUT_CATALOG.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected_catalog_rows)

    epochs = {
        "description": "Surat Thani 37-STC tide-stage constrained single-scene sensitivity epochs",
        "tide_status": "SCENE_STAGE_CONSTRAINED_NOT_FULLY_TIDE_NORMALIZED",
        "selection_file": str(OUT_SELECTION.relative_to(ROOT)),
        "epochs": [
            {
                "target_year": item["year"],
                "actual_year": item["year"],
                "dataset": "sentinel2",
                "count": 1,
                "start": str(item["acquisition_datetime_bangkok"])[:10],
                "end": str(item["acquisition_datetime_bangkok"])[:10],
            }
            for item in selected
        ],
    }
    OUT_EPOCHS.write_text(json.dumps(epochs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "plot_code": "37-STC",
        "role": "SECONDARY_TIDE_STAGE_SENSITIVITY_ANALYSIS",
        "reference": {
            "year": 2023,
            "representative_intervention_date": "2023-10-18",
            "2023_scene_role": "PRE_INTERVENTION",
            "target_stage": target_stage,
            "target_phase_0_1": round(target_phase, 6),
            "phase_definition": "elapsed fraction between adjacent extrema; timing descriptor only"
        },
        "selected_scenes": selected,
        "limitations": [
            "2024-02 is selected from official hourly RTN MSL direction because its extrema phase is not resolved in the currently retrievable public archive.",
            "A single-scene sensitivity analysis is more tide-stage-specific but less robust to scene-specific spectral noise than the three-scene median baseline.",
            "This is not a surveyed or fully tide-normalized shoreline product."
        ]
    }
    OUT_SELECTION.parent.mkdir(parents=True, exist_ok=True)
    OUT_SELECTION.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "target_stage": target_stage,
        "target_phase": round(target_phase, 6),
        "selected": selected,
        "catalog": str(OUT_CATALOG.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
