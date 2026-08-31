#!/usr/bin/env python3
"""Build the Surat Thani Ko Prap hourly MSL tide catalog using the tested RTN PDF parser."""
from __future__ import annotations

from pathlib import Path

import build_rtn_mae_klong_tide_catalog as core


core.DEFAULT_YEARS = (2023, 2024, 2025, 2026)
core.DEFAULT_OUTPUT = Path("data/tide/surat_thani/ko_prap_hourly_msl.csv")
core.DEFAULT_MANIFEST = Path("data/tide/surat_thani/ko_prap_hourly_msl_manifest.json")
core.DEFAULT_CACHE = Path(".cache/rtn_tides/surat_thani")
core.STATION_NAME = "Ko Prap"
core.DATUM = "MSL"
core.OFFICIAL_LANDING_PAGE = "https://hydro.navy.mi.th/waterlaveltable"


def year_url_candidates(year: int) -> list[str]:
    known = {
        2026: [
            "https://hydro.navy.mi.th/storage/frontend/article/23019/file/th/KP2026msl.pdf",
            "https://www.hydro.navy.mi.th/download/Water_lever69/MSL/KP2026msl.pdf",
        ],
        2025: [
            "https://www.hydro.navy.mi.th/download/Water_lever68/MSL/KP2025%20msl.pdf",
            "https://www.hydro.navy.mi.th/download/Water_lever68/MSL/KP2025msl.pdf",
        ],
        2024: [
            "https://www.hydro.navy.mi.th/download/Water_lever67/MSL/KP2024%20msl.pdf",
            "https://www.hydro.navy.mi.th/download/Water_lever67/MSL/KP2024msl.pdf",
        ],
        2023: [
            "https://www.hydro.navy.mi.th/download/Water_lever66/MSL/KP2023%20msl.pdf",
            "https://www.hydro.navy.mi.th/download/Water_lever66/MSL/KP2023msl.pdf",
        ],
    }
    urls = list(known.get(year, []))
    short = year - 1957
    for host in ("www.hydro.navy.mi.th", "hydro.navy.mi.th"):
        for folder in ("Water_lever", "Water_level"):
            for datum in ("MSL", "msl"):
                for filename in (
                    f"KP{year}%20msl.pdf",
                    f"KP{year}%20MSL.pdf",
                    f"KP{year}msl.pdf",
                    f"KP{year}MSL.pdf",
                    f"KP{year}.pdf",
                ):
                    urls.append(
                        f"https://{host}/download/{folder}{short:02d}/{datum}/{filename}"
                    )
    return list(dict.fromkeys(urls))


core.year_url_candidates = year_url_candidates


if __name__ == "__main__":
    raise SystemExit(core.main())
