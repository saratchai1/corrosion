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
python scripts/download_satellite_data.py sentinel2 --per-year 4 --dry-run
python scripts/download_satellite_data.py landsat --per-year 6 --dry-run
python scripts/download_satellite_data.py sentinel1 --per-year 20 --dry-run
```
The commands search one year at a time, follow STAC pagination, check the live collection IDs, and write candidate catalogs. The script is safe by default: omitting both `--dry-run` and `--download` also performs a dry-run. The full-range catalog run used `--quality-pool-multiplier 1` to keep remote QA reads bounded; increase it to 3 when doing a deeper candidate review. Scene cloud percentage is only a ranking hint, not AOI cloud percentage.

The verified providers are Element 84 Earth Search `sentinel-2-l2a` for Sentinel-2 and Microsoft Planetary Computer `landsat-c2-l2` / `sentinel-1-grd` for Landsat and Sentinel-1. The request diagnostic prints endpoint, body, status, response body, dataset, and date range when an API call fails.

## 6. Selection rules
- Sentinel-2: retain about 2-4 acquisition dates per year after AOI-cloud review, with similar season and, when verified tide data exist, comparable tide conditions.
- Landsat: make at least one dry/same-season composite per year; retain QA and sensor metadata.
- Sentinel-1: build quarterly median composites by default. Monthly composites are acceptable only if the total working set remains under 15 GB.
- Never discard a useful candidate only because tide data are missing; keep it as `tide_status=unverified`.

## 7. Download one acquisition per dataset
```bash
python scripts/download_satellite_data.py sentinel2 --start 2025-01-01 --end 2025-12-31 --per-year 1 --download --max-downloads 1
python scripts/download_satellite_data.py landsat --start 2025-01-01 --end 2025-12-31 --per-year 1 --download --max-downloads 1
python scripts/download_satellite_data.py sentinel1 --start 2025-01-01 --end 2025-12-31 --per-year 1 --download --max-downloads 1
```
Use `--overwrite` to recreate existing local COGs; otherwise completed files are reused. The downloader reads remote COG windows and writes AOI-only compressed COGs in EPSG:32647. Sentinel-1 GCPs are passed explicitly to reprojection. Sentinel-2 10 m and 20 m native-resolution products remain separate; visualization previews may be resized but do not change the stored native data.

## 8. Composites
```bash
python scripts/build_composites.py \
  data/satellite/landsat/2020/LC08_*/RED_30m.tif \
  --output data/satellite/landsat/2020/landsat_2020_median_RED.tif
```
Pass one spectral/quality band across multiple same-season acquisitions, not all bands from one scene. Inputs must already have identical grid geometry; the script refuses silent grid harmonization. The output COG, JSON sidecar and SHA-256 are added to the local manifest automatically.

## 9. Validation and checksums
```bash
python scripts/validate_rasters.py data/satellite/sentinel2/2020/*.tif
```
The validator checks readable raster structure, CRS, bounds, resolution, band count, nodata/mask semantics, a broad Samut Songkhram location sanity check, SHA-256 and writes `data/manifests/raster_validation.json` plus `checksums.sha256`.

## 10. Preview generation
Generate RGB and false-color previews only from validated AOI rasters. Recommended Sentinel-2 views are RGB (B4/B3/B2) and vegetation false color (B8/B4/B3). Record source raster/date in the preview filename or sidecar metadata.

## 11. Size control
Before retaining a new year/date, check total working size. Target <=15 GB. If exceeded, reduce dates while preserving year/season distribution. If raster Git/LFS storage cannot be used safely, leave rasters local/object-storage and push only catalogs/manifests/scripts/previews.
