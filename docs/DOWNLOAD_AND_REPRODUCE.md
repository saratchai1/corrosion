# Download and reproduce

## 1. Clone and select the data branch
```bash
git clone https://github.com/saratchai1/corrosion.git
cd corrosion
git fetch origin
git switch data/samut-songkhram-satellite-v1
```

## 2. Verify Git LFS before adding any raster
```bash
git lfs env
git lfs track
```
`.gitattributes` is already configured for `*.tif`, `*.tiff`, `*.jp2`, and `*.zip`. Do **not** add raster files unless LFS is installed and the repository/account has sufficient no-cost quota. If this cannot be verified, keep rasters outside Git and commit only metadata/scripts/previews.

## 3. Python environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. AOI
`data/aoi/samut_songkhram_aoi.geojson` is provisional (EPSG:4326). Replace it with the verified SEG030/project/planting polygons when those become available. Analysis rasters and distance calculations target EPSG:32647.

## 5. Build candidate catalogs
```bash
python scripts/download_satellite_data.py sentinel2 --per-year 4
python scripts/download_satellite_data.py landsat --per-year 6
python scripts/download_satellite_data.py sentinel1 --per-year 20
```
These commands discover candidates through STAC and write catalogs. They do not claim scene cloud percentage equals cloud percentage over the AOI. AOI cloud must be evaluated from SCL/QA after reading the AOI pixels.

## 6. Selection rules
- Sentinel-2: retain about 2-4 acquisition dates per year after AOI-cloud review, with similar season and, when verified tide data exist, comparable tide conditions.
- Landsat: make at least one dry/same-season composite per year; retain QA and sensor metadata.
- Sentinel-1: build quarterly median composites by default. Monthly composites are acceptable only if the total working set remains under 15 GB.
- Never discard a useful candidate only because tide data are missing; keep it as `tide_status=unverified`.

## 7. AOI clipping / COG
The downloader includes `clip_asset()` for remote COG range/window reading. Extend the selected item/asset loop only after asset keys have been reviewed. Outputs must be AOI-only, compressed COGs in EPSG:32647. Sentinel-2 10 m and 20 m native-resolution products should remain separate unless an explicitly documented resampling step is required.

## 8. Composites
```bash
python scripts/build_composites.py data/satellite/landsat/2020/*.tif --output data/satellite/landsat/2020/landsat_2020_median.tif
```
Inputs must already have identical grid geometry; the script refuses silent grid harmonization.

## 9. Validation and checksums
```bash
python scripts/validate_rasters.py data/satellite/sentinel2/2020/*.tif
```
The validator checks readable raster structure, CRS, bounds, resolution, band count, nodata/mask semantics, a broad Samut Songkhram location sanity check, SHA-256 and writes `data/manifests/raster_validation.json` plus `checksums.sha256`.

## 10. Preview generation
Generate RGB and false-color previews only from validated AOI rasters. Recommended Sentinel-2 views are RGB (B4/B3/B2) and vegetation false color (B8/B4/B3). Record source raster/date in the preview filename or sidecar metadata.

## 11. Size control
Before retaining a new year/date, check total working size. Target <=15 GB. If exceeded, reduce dates while preserving year/season distribution. If raster Git/LFS storage cannot be used safely, leave rasters local/object-storage and push only catalogs/manifests/scripts/previews.
