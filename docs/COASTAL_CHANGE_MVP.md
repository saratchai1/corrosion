# Samut Songkhram coastal-change MVP

## Interpretation policy

This project maps an **image-derived water-land boundary**. It is not a true, legal, surveyed, or tide-normalized shoreline. Tide observations were unavailable for all selected acquisitions, so every output retains `tide_status=unverified` and `confidence=LOW`. The exposed edge of the Mae Klong/Don Hoi Lot mudflat can move substantially with tide, suspended sediment, waves, season, and acquisition geometry.

## Epochs actually used

| Target epoch | Actual imagery year | Sensor | Scenes | Analysis resolution |
|---:|---:|---|---:|---:|
| 1985 | 1987 | Landsat 5 TM | 2 | 30 m |
| 1990 | 1990 | Landsat 5 TM | 3 | 30 m |
| 2000 | 2000 | Landsat 5 TM | 3 | 30 m |
| 2010 | 2009 | Landsat 5 TM | 3 | 30 m |
| 2018 | 2018 | Sentinel-2A/2B | 3 | 20 m |
| 2020 | 2020 | Sentinel-2A/2B | 3 | 20 m |
| 2025 | 2025 | Sentinel-2A/2C | 3 | 20 m |
| 2026 | 2026 | Sentinel-2A/2B | 3 | 20 m |

The target 1985 epoch uses the nearest usable provider imagery from 1987. The target 2010 epoch uses full-coverage Landsat 5 scenes from 2009; post-2003 Landsat 7 SLC-off scenes were excluded from that composite. Exact scene IDs, dates, AOI cloud metrics, source URLs, licences, paths, sizes, and checksums are recorded in `data/catalog/mvp_optical_scenes.csv`.

## Processing method

1. **Selection and download:** 2–3 same/dry-season acquisitions per epoch, full AOI coverage, low AOI cloud/shadow where available, AOI window reads only. Source reflectance and quality bands remain local under `data/satellite/`.
2. **Composite:** Landsat Collection 2 Level-2 scale/offset and `QA_PIXEL` masking; Sentinel-2 Level-2A scale and `SCL` masking. Invalid, fill, cloud, shadow, cirrus, and snow pixels are excluded before a per-band median. Outputs are five-band float32 COGs in EPSG:32647.
3. **Water-land boundary:** MNDWI is calculated from green and SWIR1. Otsu, fixed-zero, and 60th-percentile candidates are evaluated. Otsu is preferred when the edge-connected ocean fraction is plausible; alternatives are stability guardrails for obvious histogram failures. Conservative morphology removes only small components/holes. The ocean exterior is sampled along a documented provisional coastal corridor to exclude connected fishpond/canal detours. Every retained vertex is snapped to the image-derived exterior.
4. **Vegetation proxy:** NDVI thresholding is constrained to the coastal corridor and image-derived land. It is a spectral coastal vegetation proxy, not a validated mangrove inventory; inland agriculture may not be completely separable without reference/training polygons.
5. **Transects:** the latest image trace is sampled at approximately 100 m. Three-kilometre perpendicular transects are oriented inland-to-seaward. Positive positions/movement mean seaward; negative mean inland. Apparent erosion/accretion requires movement beyond the 30 m early-sensor uncertainty. Endpoint and ordinary least-squares regression rates are stored, but confidence remains LOW while tide is unverified.

## Preliminary MVP results

From 144 classified transects at 100 m spacing:

- apparent erosion-like length: **5.3 km**;
- apparent accretion-like length: **6.0 km**;
- stable within ±30 m: **3.1 km**;
- median net apparent movement (1987–2026): **−3.38 m**;
- mean net apparent movement: **+0.55 m**.

The vegetation proxy changes from 2,293.05 ha in the 1985 target epoch (1987 imagery) to 1,890.17 ha in 2026: **−402.88 ha (−17.57%)**. This is not yet attributable to mangrove loss because sensor differences, mudflat wetness, seasonal vegetation, thresholding, and the provisional corridor affect the proxy.

These figures are exploratory indicators only. They must not be reported as definitive coastal erosion or mangrove-change statistics.

## Outputs and storage

- `data/processed/optical/*.tif`: local five-band COG composites; ignored by Git.
- `data/processed/water_boundary/*.geojson`: per-epoch image-derived boundaries and QA metadata.
- `data/processed/vegetation/*.geojson`: coastal vegetation proxy polygons and area.
- `data/processed/transects/transects.geojson`: geometry and complete per-transect summary properties.
- `data/processed/statistics/transect_yearly.csv`: long-form positions with sensor, resolution, tide, and confidence.
- `data/processed/statistics/transect_summary.geojson`: web/GIS-ready transect classifications and rates.
- `data/processed/statistics/summary.json`: aggregate metrics.
- `web/public/data/`: static JSON, GeoJSON, and WebP assets used by the WebApp.

Source and composite TIFFs are stored on the local hard disk, not in Git. Git contains reproducible code, catalogs/metadata, small derived vectors/tables, and optimized WebP previews.

## Upgrade path to defensible erosion analysis

1. Replace the provisional AOI/corridor with verified coast-segment and mangrove/project polygons.
2. Join acquisition timestamps to a sourced tide station/model with stated datum; select or normalize comparable water levels.
3. Use a seasonally consistent acquisition window and more cloud-free observations per epoch.
4. Validate boundary positions against orthophotos, RTK/GNSS profiles, drone surveys, or official shoreline datasets.
5. Quantify per-epoch horizontal uncertainty from georegistration, pixel size, threshold sensitivity, mudflat slope, and tide error; propagate it into rates and classes.
6. Harmonize Landsat/Sentinel spectral responses and co-register epochs to stable control features.
7. Train and validate a mangrove classifier with verified reference polygons, field observations, and confusion-matrix reporting.
