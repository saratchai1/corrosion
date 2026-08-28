# Data sources

This project uses only free/open satellite sources and records the upstream provider in each catalog row.

## Sentinel-2 Level-2A
- Product: atmospherically corrected Surface Reflectance (Level-2A).
- Target period: 2016-present.
- Required assets: B2, B3, B4, B8 (10 m); B5, B6, B7, B8A, B11, B12 and SCL (20 m/native quality semantics).
- Provider/API used by the scripts: Element 84 Earth Search STAC v1 (`https://earth-search.aws.element84.com/v1`), collection `sentinel-2-l2a`.
- Original dataset/licence: Copernicus Sentinel Data; free, full and open access under the Copernicus Sentinel Data Legal Notice.
- Important: resampling a 20 m band to a 10 m grid does not create true 10 m information. Native resolution must remain recorded in metadata.

## Landsat Collection 2 Level-2
- Product: Collection 2 Level-2 Surface Reflectance.
- Target period: 1984-present using Landsat 5 TM, Landsat 7 ETM+, Landsat 8 OLI and Landsat 9 OLI-2 as available.
- Analysis role: long-term 30 m coastal/mangrove trend; not confirmation of small planting plots.
- Provider/API used by scripts: Microsoft Planetary Computer STAC v1 (`https://planetarycomputer.microsoft.com/api/stac/v1`), collection `landsat-c2-l2`. Earth Search exposes the collection, but its Landsat assets are requester-pays for anonymous reads; Planetary Computer provides free signed cloud-native assets for this workflow. The original dataset is USGS Landsat Collection 2 Level-2.
- Licence: Landsat products are public domain/no restrictions on use; dataset citation should still be retained.

## Sentinel-1 GRD
- Product: GRD, VV and VH.
- Target period: 2015-present.
- Provider/API used by scripts: Microsoft Planetary Computer STAC v1 (`https://planetarycomputer.microsoft.com/api/stac/v1`), collection `sentinel-1-grd`. Sentinel-1 GRD measurement TIFFs may use EPSG:4326 GCPs rather than a dataset-level affine CRS; the downloader warps from those GCPs explicitly.
- Original dataset/licence: Copernicus Sentinel Data; free, full and open access.
- Analysis role: supplemental evidence during cloudy periods and for water/mudflat characterization. It is not used as the sole shoreline evidence.

## Access policy
The workflow uses STAC and range/window reads from cloud-hosted raster assets. It does not scrape download pages and is designed to clip to the AOI rather than downloading many full scenes.

## Tide data
No tide station is fabricated. Until a sourced station/datum/predicted-or-observed record is joined to acquisition timestamps, catalog rows must use `tide_status=unverified` and leave `tide_level` blank.
