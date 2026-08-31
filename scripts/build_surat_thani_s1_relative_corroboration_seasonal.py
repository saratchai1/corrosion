#!/usr/bin/env python3
"""Run the Surat Sentinel-1 relative diagnostic with an explicit Feb-Apr filter.

The base diagnostic intentionally keeps its track-selection and within-scene metrics
isolated. This wrapper fixes the first-run catalog-window issue by filtering usable
rows to February-April *before* orbit-family selection and annual scene sampling.
"""
from __future__ import annotations

import build_surat_thani_s1_relative_corroboration as core

_original_catalog_rows = core.catalog_rows


def seasonal_catalog_rows():
    rows = _original_catalog_rows()
    selected = []
    for row in rows:
        dt = row.get("acquisition_datetime_utc", "")
        try:
            month = int(dt[5:7])
        except (TypeError, ValueError):
            continue
        if month in {2, 3, 4}:
            selected.append(row)
    return selected


core.catalog_rows = seasonal_catalog_rows

if __name__ == "__main__":
    raise SystemExit(core.main())
