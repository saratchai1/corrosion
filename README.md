# corrosion

Reproducible geospatial data workflow for coastal erosion and mangrove analysis in Samut Songkhram, Thailand.

## Active data branch
`data/samut-songkhram-satellite-v1`

## Scope
- Sentinel-2 Level-2A Surface Reflectance, 2016-present
- Landsat Collection 2 Level-2 Surface Reflectance, 1984-present
- Sentinel-1 GRD VV/VH, 2015-present
- Acquisition time stored in UTC and Asia/Bangkok
- Tide metadata kept explicit; unknown tide remains `unverified`
- AOI files in EPSG:4326; analysis rasters/distances in EPSG:32647

## Important status
The repository initially contained no verified SEG030/project AOI, so `data/aoi/samut_songkhram_aoi.geojson` is **provisional**. The live STAC workflow, catalogs, previews and QA have been tested; local raster COGs are intentionally not committed because authenticated Git LFS upload/quota could not be confirmed. See `docs/DOWNLOAD_AND_REPRODUCE.md` and `docs/DATA_LIMITATIONS.md`.
