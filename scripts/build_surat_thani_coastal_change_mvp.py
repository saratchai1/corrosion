#!/usr/bin/env python3
"""Run the tested coastal-change engine for Surat Thani 37-STC without overwriting Samut Songkhram outputs."""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import LineString

import build_coastal_change_mvp as core


ROOT = Path(__file__).resolve().parents[1]
PUBLISH_ROOT = ROOT / "web/public/data/surat_thani"

# Reuse the tested Samut Songkhram processing engine, but isolate every Surat input/output.
core.AOI_PATH = ROOT / "data/aoi/surat_thani_37_stc_analysis_aoi.geojson"
core.CATALOG_PATH = ROOT / "data/catalog/surat_thani_mvp_optical_scenes.csv"
core.EPOCH_PATH = ROOT / "data/catalog/surat_thani_mvp_epochs.json"
core.OUT = ROOT / "data/processed/surat_thani"
core.WEB_DATA = core.OUT / "web"
core.TIDE_STATUS = "unverified"

# Provisional guide follows the exposed Chaiya coast through/around 37-STC.
# It only helps isolate the open-coast boundary from inland channels; extracted
# boundary positions still come from imagery and remain image-derived proxies.
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

# The core publishes to web/public/data by default. Route only that final copy
# into a province namespace so the existing Samut Songkhram dashboard data is untouched.
_original_copytree = core.shutil.copytree


def _routed_copytree(src, dst, *args, **kwargs):
    if Path(dst) == ROOT / "web/public/data":
        dst = PUBLISH_ROOT
    return _original_copytree(src, dst, *args, **kwargs)


core.shutil.copytree = _routed_copytree


def patch_json(path: Path, *, index: bool = False) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if index:
        payload["title"] = "Surat Thani 37-STC Coastal Change MVP"
        payload["aoi"] = "37-STC and surrounding Chaiya coast (derived analytical AOI)"
    else:
        payload["title"] = "Surat Thani 37-STC image-derived coastal change MVP"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def patch_labels() -> None:
    for root in [core.OUT / "statistics", core.WEB_DATA, PUBLISH_ROOT]:
        patch_json(root / "summary.json")
    for root in [core.WEB_DATA, PUBLISH_ROOT]:
        patch_json(root / "index.json", index=True)


def publish_project_context() -> None:
    target = PUBLISH_ROOT / "project"
    target.mkdir(parents=True, exist_ok=True)
    (target / "plots.geojson").write_text(
        (ROOT / "data/aoi/surat_thani_37_stc_current_aoi.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (target / "boundary_history.geojson").write_text(
        (ROOT / "data/aoi/surat_thani_37_stc_boundaries.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (target / "planting.json").write_text(
        (ROOT / "data/metadata/surat_thani_37_stc_planting.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def main() -> None:
    core.main()
    patch_labels()
    publish_project_context()


if __name__ == "__main__":
    main()
