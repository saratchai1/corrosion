# Krabi coastal / mangrove satellite pilot

This branch reuses the tested STAC workflow from `data/samut-songkhram-satellite-v1`, but isolates all Krabi outputs under `regions/krabi/data/`.

## AOI

Canonical analysis geometry:

`regions/krabi/data/aoi/krabi_pdd_plots.geojson`

Google Earth / field-review copy:

`regions/krabi/data/aoi/krabi_pdd_plots.kmz`

Both contain the same four WGS84 plot polygons.

Current pilot plots:

- `97-VSD` — Khlong Thom / Huai Nam Khao
- `98-VSD` — Khlong Thom / Huai Nam Khao
- `99-VSD` — Khlong Thom / Khlong Thom Tai
- `100-VSD` — Khlong Thom / Phela

The polygons are taken from existing project KML-derived geometry and retain the original `source_file` path in GeoJSON feature properties. They are not a fabricated Krabi province boundary.

## Why a wrapper exists

The inherited `scripts/download_satellite_data.py` was written for a single Samut Songkhram AOI and contains a Samut Songkhram location guard. `scripts/download_krabi_satellite_data.py` reuses the same discovery/ranking/download code while:

1. unioning all Krabi plot polygons for STAC queries;
2. validating the union against a broad Krabi coastal working envelope;
3. writing catalogs, previews, rasters, and manifests only under `regions/krabi/data/`.

## Dry-run discovery

From the repository root:

```bash
python scripts/download_krabi_satellite_data.py sentinel2 \
  --start 2016-01-01 --end 2026-08-29 --per-year 4 --dry-run

python scripts/download_krabi_satellite_data.py landsat \
  --start 1984-01-01 --end 2026-08-29 --per-year 6 --dry-run

python scripts/download_krabi_satellite_data.py sentinel1 \
  --start 2015-01-01 --end 2026-08-29 --per-year 20 --dry-run
```

Expected catalogs:

```text
regions/krabi/data/catalog/sentinel2_scenes.csv
regions/krabi/data/catalog/landsat_scenes.csv
regions/krabi/data/catalog/sentinel1_scenes.csv
```

## Download selected AOI-only data

Use the same command with `--download`. Start with `--max-downloads` for a small reproducible smoke test before downloading the full history.

Example:

```bash
python scripts/download_krabi_satellite_data.py sentinel2 \
  --start 2024-01-01 --end 2026-08-29 --per-year 4 \
  --download --max-downloads 3
```

Outputs are isolated under:

```text
regions/krabi/data/satellite/
regions/krabi/data/previews/
regions/krabi/data/catalog/
regions/krabi/data/manifests/
```

## Scientific use

Initial use is screening, not causal attribution:

- shoreline / water-edge movement;
- mangrove vegetation and canopy change;
- comparison among the four project plots and nearby coastal reference areas;
- acquisition-time preservation for later tide matching.

Do not label a vegetation decline as erosion, mortality, salinity damage, or storm damage without supporting spatial/temporal evidence and field validation.

## Known limitation

Krabi is strongly affected by monsoon cloud cover. Previous project processing already found very low valid coverage for `99-VSD` in September 2024 and `100-VSD` in September 2023. Keep such periods as `NO_DATA` / `LOW_QA`; do not replace them silently with imagery from another month.
