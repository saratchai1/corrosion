# Surat Thani 37-STC — Drone high-resolution baseline

## Source located and verified at file level

Google Drive structure:

- `Final Data / สุราษฎร์ธานี / 20-05-2569 / 37 STC`
- raw: `orthor 37 stc.tif`
- Drive file id: `1WdHWRu-JXFM4xayCbg6KA2-DTZFldBij`
- size: 3,333,103,914 bytes
- MIME: `image/tiff`
- Drive created time: `2026-05-20T08:52:30.171Z`
- Drive modified time: `2026-05-20T08:33:26.000Z`
- lightweight source preview: `orthor 37 stc.png`

The PNG was inspected and is accepted as a **visual orthomosaic preview**. It is not used as georeferenced evidence because the PNG does not carry the raw TIFF transform/CRS needed for spatial QA.

## Evidence status

`HIGH_RESOLUTION_BASELINE`

One orthomosaic epoch is spatial baseline evidence only. It is not a drone-derived before/after erosion rate.

The folder label `20-05-2569` is retained only as a source label. It is **not** promoted to a verified flight/acquisition date without acquisition metadata.

## Project geometry reference

The known project geometry uses `EPSG:32647` and the primary analysis boundary is 157.55 rai. This is a reference for plausibility checking only. **The raw TIFF is not assigned EPSG:32647 until its own GeoTIFF metadata is read.**

## Raw GeoTIFF hard gate

The connected Google Drive raw-content action has a 256 MiB (`268,435,456` byte) limit. The 3.33 GB TIFF returns HTTP 413 through that path, so this environment cannot currently inspect the TIFF itself for:

- CRS
- raster transform / bounds
- GSD
- band count / NIR presence
- NoData / alpha semantics
- valid imagery coverage fraction

No sidecar, flight log, GCP/RTK file, or photogrammetry metadata was found in the source folder. These values therefore remain unverified rather than being guessed.

A reproducible inspector is now committed at:

`scripts/inspect_surat_thani_37_stc_geotiff.py`

It reads metadata directly with Rasterio, calculates coverage block-by-block to avoid loading the 3.33 GB raster into RAM, writes a machine-readable QA JSON, writes a WGS84 footprint GeoJSON, checks the raw CRS against the known project-geometry CRS, and keeps the flight date unverified.

## Legacy Drone ↔ Sentinel comparison audit

An older Drive folder named `drone_satellite_mosaic_compare_app_37_stc` was inspected. It is **not accepted** as georeferenced Drone ↔ Sentinel evidence because:

- the HTML explicitly labels the drone side `Drone boundary (placeholder)` / `Drone Placeholder`
- its `drone_mosaic.webp` contains a boundary-only placeholder rather than orthomosaic pixels

Audit status:

`REJECTED_PLACEHOLDER_NOT_DRONE_IMAGERY`

This prevents a visually convincing but scientifically false same-extent comparison from being promoted into the current web app.

## Web handling

- raw GeoTIFF remains in Drive
- GitHub/Vercel serves only the lightweight confirmed visual preview and machine-readable manifest
- Drone HR remains a standalone page; it does not replace the multi-year satellite history slider
- project geometry CRS is shown separately from raw TIFF CRS
- same-extent Drone ↔ Sentinel alignment remains locked until raw CRS/transform QA passes
- current page reports the exact access blocker instead of calling metadata merely “pending”

## Claim guard

Current drone evidence may be used to inspect visible canopy/mudflat/channel/structures and to plan field validation. It must not be used to claim a drone-derived erosion rate, to infer a flight date from the folder label, to assume a NIR band, or to attribute coastal change causally to planting.
