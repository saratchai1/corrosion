# Surat Thani 37-STC coastal-erosion pilot

This branch applies the tested Samut Songkhram free-data workflow to the real project boundary for **37-STC**, Ban Lamet, Lamet Subdistrict, Chaiya District, Surat Thani.

## Grounded project inputs
- **Primary/current PDD boundary: 157.55 rai** (`SHP PDD`); EPSG:32647 cross-check = **157.56 rai**. This is the smaller boundary and is used for all primary analysis.
- Historical/reference record: **200.05 rai** (`ยืนยันกรม`); supplied polygon computes to **196.21 rai**. It is retained for boundary history/reference only and is not used as the primary AOI.
- **Representative intervention date: 2023-10-18**, using the planting-end date as the before/after cutoff.
- Species/counts: โกงกางใบใหญ่ 100,000; โกงกางใบเล็ก 40,000; ลำพู 2,232; total **142,232 seedlings**.

## Geometry
- `data/aoi/surat_thani_37_stc_current_aoi.geojson` — **primary project boundary (157.55 rai)** used for plot-level analysis.
- `data/aoi/surat_thani_37_stc_boundaries.geojson` — current plus historical/reference boundary versions.
- `data/aoi/surat_thani_37_stc_analysis_aoi.geojson` — derived envelope around a 2 km buffer for surrounding coast/reference context; **not** a project boundary.

## Satellite workflow
```bash
python scripts/download_satellite_data_surat_thani.py sentinel2 --dry-run
python scripts/download_satellite_data_surat_thani.py landsat --dry-run
python scripts/download_satellite_data_surat_thani.py sentinel1 --dry-run
```
Catalogs are isolated as `data/catalog/surat_thani_<dataset>_scenes.csv`; downloads go under `data/satellite/surat_thani/`.

## Tide reference
Use **Ko Prap / เกาะปราบ (Surat Thani)** as the first tide-screening station. Station predictions are supporting metadata, not observed water level at 37-STC.

## Analysis intent
1. Long-term Landsat context before planting.
2. Sentinel-2 annual/seasonal mangrove-edge and water-edge screening.
3. Treat **2023-10-18** as the representative intervention cutoff; compare post-planting 2024-2026 against pre-intervention history.
4. Tide-aware filtering of waterline observations.
5. Add nearby unplanted reference/control segments before comparative-effect claims.

Do not label one image-derived waterline as a surveyed shoreline or attribute erosion reduction to planting without repeat observations, uncertainty checks, tide screening and suitable controls.
