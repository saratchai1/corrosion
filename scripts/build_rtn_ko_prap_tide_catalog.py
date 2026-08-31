#!/usr/bin/env python3
"""Build the Surat Thani Ko Prap hourly MSL tide catalog with the tested RTN parser.

The 2026 Ko Prap MSL table has been independently checked against the user-supplied
`KP2026msl.pdf`. The companion `KP2026.pdf` uses Lowest Low Water / chart datum;
the official table states that Ko Prap Lowest Low Water is 1.43 m below Mean Sea
Level. Do not mix those two height columns without an explicit datum conversion.

Only 2026 is enabled by default because that official MSL download URL is currently
live and reproducible. Historical sources can be added later when a live official
archive (or a preserved project copy) is available.
"""
from __future__ import annotations

from pathlib import Path

import build_rtn_mae_klong_tide_catalog as core


core.DEFAULT_YEARS = (2026,)
core.DEFAULT_OUTPUT = Path("data/tide/surat_thani/ko_prap_hourly_msl.csv")
core.DEFAULT_MANIFEST = Path("data/tide/surat_thani/ko_prap_hourly_msl_manifest.json")
core.DEFAULT_CACHE = Path(".cache/rtn_tides/surat_thani")
core.STATION_NAME = "Ko Prap"
core.DATUM = "MSL"
core.OFFICIAL_LANDING_PAGE = "https://hydro.navy.mi.th/waterlaveltable"


def year_url_candidates(year: int) -> list[str]:
    if year == 2026:
        return [
            "https://hydro.navy.mi.th/storage/frontend/article/23019/file/th/KP2026msl.pdf",
        ]

    # Historical URLs are retained as hints only. They are not in DEFAULT_YEARS
    # because the legacy server currently returns 404 to fresh downloads.
    historical = {
        2025: "https://www.hydro.navy.mi.th/download/Water_lever68/MSL/KP2025%20msl.pdf",
        2024: "https://www.hydro.navy.mi.th/download/Water_lever67/MSL/KP2024%20msl.pdf",
    }
    return [historical[year]] if year in historical else []


core.year_url_candidates = year_url_candidates


if __name__ == "__main__":
    raise SystemExit(core.main())
