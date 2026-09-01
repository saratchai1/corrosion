# Surat Thani 37-STC — Drone high-resolution baseline

## Source located

Google Drive structure:

- `Final Data / สุราษฎร์ธานี / 20-05-2569 / 37 STC`
- raw: `orthor 37 stc.tif`
- Drive file id: `1WdHWRu-JXFM4xayCbg6KA2-DTZFldBij`
- size: 3,333,103,914 bytes
- lightweight Drive preview also found: `orthor 37 stc.png`

## Evidence status

`HIGH_RESOLUTION_BASELINE`

The folder label `20-05-2569` is retained only as a source label. It is **not** promoted to a verified flight/acquisition date without flight log, EXIF, photogrammetry project metadata, RTK/GCP record, or readable GeoTIFF metadata that confirms acquisition timing.

## Current technical limit

The connected Google Drive file download action has a 256 MB limit. The 3.33 GB GeoTIFF therefore cannot be inspected directly in this session for:

- CRS
- raster transform / bounds
- GSD
- band count / NIR presence
- NoData / alpha
- valid coverage fraction within 37-STC

These remain `PENDING_RAW_METADATA_INSPECTION` rather than being guessed from the PNG preview.

## Web handling

- raw GeoTIFF stays in Drive
- Vercel/GitHub receives only a downsampled WebP preview and machine-readable manifest
- Drone HR is a standalone page; it does not replace the multi-year satellite slider
- cross-sensor alignment is intentionally locked until georeference QA is available
- one epoch cannot be used to calculate a drone-derived erosion rate
