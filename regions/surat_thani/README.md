# Surat Thani 37-STC coastal-erosion pilot

This branch applies the tested Samut Songkhram free-data workflow to the real project boundary for **37-STC**, Ban Lamet, Lamet Subdistrict, Chaiya District, Surat Thani.

## Grounded project inputs
- Current PDD boundary: **157.55 rai** (`SHP PDD`); EPSG:32647 cross-check = **157.56 rai**.
- Historical/reference record: **200.05 rai** (`ยืนยันกรม`); supplied polygon computes to **196.21 rai**, so both values are preserved rather than silently forced to match.
- Planting end: **2023-10-18**. Species/counts: โกงกางใบใหญ่ 100,000; โกงกางใบเล็ก 40,000; ลำพู 2,232; total **142,232 seedlings**.

## Geometry
- `data/aoi/surat_thani_37_stc_current_aoi.geojson` — current project boundary.
- `data/aoi/surat_thani_37_stc_boundaries.geojson` — current plus historical/reference version.
- `data/aoi/surat_thani_37_stc_analysis_aoi.geojson` — derived envelope around a 2 km buffer for surrounding coast/reference context; **not** a project boundary.

## Satellite workflow
```bash
python scripts/download_satellite_data_surat_thani.py sentinel2 --dry-run
python scripts/download_satellite_data_surat_thani.py landsat --dry-run
python scripts/download_satellite_data_surat_thani.py sentinel1 --dry-run
```
Catalogs are isolated as `data/catalog/surat_thani_<dataset>_scenes.csv`; downloads go under `data/satellite/surat_thani/`.

## Tide reference
Use **Ko Prap / เกาะปราบ (Surat Thani)** as the first tide-screening station (~24.45 km from current AOI centroid). Station predictions are supporting metadata, not observed water level at 37-STC.

## Analysis intent
1. Long-term Landsat context before planting.
2. Sentinel-2 annual/seasonal mangrove-edge and water-edge screening.
3. Post-planting comparison for 2024-2026 against pre-2023 trend.
4. Tide-aware filtering of waterline observations.
5. Add nearby unplanted reference/control segments before comparative-effect claims.

Do not label one image-derived waterline as a surveyed shoreline or attribute erosion reduction to planting without repeat observations, uncertainty checks, tide screening and suitable controls.
