# corrosion

Reproducible geospatial data workflows for coastal erosion and mangrove change analysis in Thailand.

## Regional data branches

- `data/samut-songkhram-satellite-v1` — Samut Songkhram STAC/satellite workflow
- `data/krabi-satellite-v1` — Krabi project-plot pilot using existing KML/KMZ-derived boundaries

## Shared satellite scope

- Sentinel-2 Level-2A Surface Reflectance, 2016-present
- Landsat Collection 2 Level-2 Surface Reflectance, 1984-present
- Sentinel-1 GRD VV/VH, 2015-present
- acquisition time stored in UTC and Asia/Bangkok
- tide metadata kept explicit; unknown tide remains `unverified`
- AOI geometry in EPSG:4326; analysis rasters/distances in EPSG:32647

## Krabi pilot

See `regions/krabi/README.md`.

The Krabi pilot currently uses real project boundaries for `97-VSD`, `98-VSD`, `99-VSD`, and `100-VSD` rather than an invented province polygon. The branch includes both canonical GeoJSON and a consolidated KMZ for Google Earth review.

Satellite outputs are isolated under `regions/krabi/data/` so they do not mix with Samut Songkhram catalogs, previews, rasters, or manifests.

## Data quality rule

Cloud/tide/geometry limitations must remain explicit. Do not silently replace low-quality or missing observations with another date/month, and do not infer erosion or tree mortality from a single vegetation signal without supporting evidence.
