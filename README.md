# corrosion — Rayong pilot

Reproducible geospatial workflow for coastal erosion and mangrove-change analysis in Rayong, Thailand.

## Active data branch
`data/rayong-satellite-v1`

## Rayong geometry
- `data/aoi/rayong_planting_plots.geojson` — 14 existing planting-plot polygons from the Rayong GIS dataset already stored in Google Drive; repository copy is simplified for analysis/reproducibility.
- `data/aoi/rayong_coastal_analysis_aoi.geojson` — derived analysis AOI around the plots, expanded to include surrounding shoreline/reference coast. It is an **analysis AOI**, not an official project boundary.
- Plot IDs: `14(1)-STC`, `14-STC`, `14-VSD`, `15-STC`, `15-VSD`, `16-VSD`, `17-VSD`, `18(1)-STC`, `19-STC`, `20-STC`, `22(1)-STC`, `22-STC`, `23(1)-STC`, `23-STC`.

## Satellite scope
- Sentinel-2 Level-2A Surface Reflectance: 4 selected acquisition dates/year, 2016-present.
- Landsat Collection 2 Level-2 Surface Reflectance: 6 selected acquisition dates/year, 1984-present.
- Sentinel-1 GRD VV/VH: 20 selected acquisition dates/year, 2015-present.
- Acquisition time is stored in UTC and Asia/Bangkok.
- Tide metadata remains explicit; unknown tide is kept as `unverified` rather than guessed.
- AOI files are EPSG:4326; raster/distance analysis uses EPSG:32647.

## Run the Rayong workflow
```bash
python scripts/download_satellite_data_rayong.py sentinel2 --dry-run
python scripts/download_satellite_data_rayong.py landsat --dry-run
python scripts/download_satellite_data_rayong.py sentinel1 --dry-run
```

The Rayong runner reuses the tested Samut Songkhram STAC/download core but supplies Rayong-specific AOI validation, catalog names, and image-density defaults. Output catalogs are written as `data/catalog/rayong_<dataset>_scenes.csv` so they do not overwrite the inherited Samut Songkhram catalogs.

## Intended analysis
1. Extract annual/seasonal shoreline proxies and quantify shoreline displacement.
2. Measure mangrove extent/width change around the planting areas.
3. Compare planted plots with surrounding reference coast/mangrove.
4. Join tide observations later and separate tide-driven apparent shoreline movement from persistent change.

The branch currently prepares the geometry and reproducible acquisition workflow. Existing Samut Songkhram preview/catalog files inherited from the source branch should not be interpreted as Rayong results; Rayong outputs use the `rayong_` catalog prefix.
