# QA workflow

1. Populate scene catalog from STAC.
2. Review AOI cloud from SCL/QA, not scene cloud alone.
3. Join sourced tide metadata when available; otherwise keep `unverified`.
4. Clip only AOI windows, write compressed COGs in EPSG:32647.
5. Validate rasters and write SHA-256 checksums.
6. Visually inspect at least one image per sensor and decade/time block.
7. Treat water-land boundaries as shoreline proxies until tide/field validation.
