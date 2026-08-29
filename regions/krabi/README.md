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

## Reuse existing Sentinel-2 products first

A newer processed dataset already exists in:

- repository: `saratchai1/prasae`
- branch: `pdd22-satellite-refetch`
- source coverage table: `data/pdd22_satellite/coverage_report.csv`
- source plot products: `data/pdd22_satellite/plots/{plot_code}/{YYYY-MM}/`

It contains all four Krabi pilot plots with 12 periods each from `2023-09` through `2026-08` (48 observations total). A small provenance-preserving copy of the Krabi coverage/vegetation metrics is stored at:

`regions/krabi/data/reuse/pdd22_krabi_coverage.csv`

The PNG products remain in `prasae`; they are referenced rather than duplicated into this repository.

Use `scripts/download_krabi_satellite_data.py` for:

- older Sentinel-2 history before the reused PDD22 periods;
- future Sentinel-2 refreshes;
- Landsat history;
- Sentinel-1 history;
- any period genuinely missing from the reused dataset.

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
  --start 2016-01-01 --end 2023-08-31 --per-year 4 \
  --download --max-downloads 3
```

Outputs are isolated under:

```text
regions/krabi/data/satellite/
regions/krabi/data/previews/
regions/krabi/data/catalog/
regions/krabi/data/manifests/
```

## Latest reused QA snapshot

Across the 48 reused observations:

- `GOOD`: 29
- `PARTIAL`: 14
- `LOW_QA`: 4
- `NO_DATA`: 1

Current notable low-coverage periods in the latest refetched dataset are:

- `98-VSD / 2023-09`: 34.55% (`LOW_QA`)
- `99-VSD / 2023-09`: 7.52% (`LOW_QA`)
- `99-VSD / 2025-09`: 22.12% (`LOW_QA`)
- `100-VSD / 2023-09`: 2.44% (`NO_DATA`)
- `100-VSD / 2026-08`: 13.08% (`LOW_QA`)

The earlier `99-VSD / 2024-09` gap was resolved by the refetch and is now 100% coverage / `GOOD` in the current source table.

## Scientific use

Initial use is screening, not causal attribution:

- shoreline / water-edge movement;
- mangrove vegetation and canopy change;
- comparison among the four project plots and nearby coastal reference areas;
- acquisition-time preservation for later tide matching.

Do not label a vegetation decline as erosion, mortality, salinity damage, or storm damage without supporting spatial/temporal evidence and field validation.
