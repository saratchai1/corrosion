# scripts
Utilities for STAC scene discovery, AOI-only clipping, same-grid composites, preview generation and raster QA/checksums.

- `download_mvp_epochs.py`: downloads historical Landsat snapshots plus three January–April Sentinel-2 acquisitions for every year from 2017–2026.
- `build_coastal_change_mvp.py`: builds 14 province-wide composites and all map imagery, boundaries, vegetation proxies, transects, statistics, and static web data.
- `build_samut_songkhram_project_aoi.py`: extracts only `91–98-STC` and `87-VSD` from the pinned `mangrove-drone-dashboard` sources, unions overlapping rings, and records official versus geometry areas.
- `download_project_impact_epochs.py`: downloads three January–April Sentinel-2 acquisitions for each year 2023–2026 into an AOI-specific local raster root.
- `build_project_impact_analysis.py`: creates 20 m composites, plot NDVI/MNDWI indicators, local matched-context comparisons, and the 2025–2026 plot-crossing boundary summary.
