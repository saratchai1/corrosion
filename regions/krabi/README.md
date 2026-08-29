# Krabi coastal / mangrove satellite pilot

This pilot provides a reproducible satellite-screening workflow for four project plots in Krabi. It separates three questions that must not be conflated:

1. **Vegetation condition** — plot-level NDVI/NDRE/MNDWI screening.
2. **Water-edge change** — cloud-masked multi-scene water classification and epoch comparison.
3. **Engineering coastal erosion** — intentionally **not estimated** until tide and field shoreline controls are available.

The operational branch is `data/krabi-satellite-v1`. Krabi outputs are isolated under `regions/krabi/` and are not mixed with Samut Songkhram data.

## Final pilot status — 29 August 2026

The automated workflow completed successfully with the following retained evidence:

- 4 project plots: `97-VSD`, `98-VSD`, `99-VSD`, `100-VSD`.
- Sentinel-2 Collection 1 L2A: 27 selected scenes from 2018–2026.
- 25 scenes passed the minimum valid-grid threshold.
- 2 scenes were excluded before trend/consensus analysis because valid coverage was below 10%:
  - `2018-01-22`
  - `2022-03-22`
- At least 2 usable scenes remained in every analyzed year.
- Median MNDWI/SCL water-class consistency across usable scenes:
  - water IoU: `0.7501`
  - overall agreement: `0.9772`
  - Cohen's kappa: `0.8458`

### Executive interpretation

- **Vegetation:** none of the four plots has a clear persistent linear NDVI decline under the conservative slope/R² rule.
- **Water:** the multi-scene epoch comparison does not show a large persistent water-gain signal inside any project plot.
- **Field priority:** inspect `97-VSD` first because a `GOOD`-QA NDVI dip occurred in June 2025 (`0.5179 → 0.3494`) and recovered by December 2025 (`0.5518`).
- **Erosion rate:** not calculated because tide remains unverified and no field shoreline control has been applied.

### Multi-scene epoch comparison

The default comparison pools the first three and last three analyzed years:

- baseline epoch: 2018–2020
- latest epoch: 2024–2026
- comparable corridor area: `10,784,400 m²`
- candidate water gain: `10,000 m²` (`0.09%`)
- candidate water loss: `55,300 m²` (`0.51%`)
- net candidate water gain: `-45,300 m²` (`-0.42%`)

These are classification-screening areas, not erosion/accretion quantities. Water gain may reflect inundation, tide, classification uncertainty, or erosion; water loss may reflect drying, accretion, tide, or classification uncertainty.

Inside the four project polygons, all plots are flagged `NO_LARGE_WATER_GAIN_SIGNAL`. The only non-zero candidate change at plot scale is `98-VSD`: `100 m²` water gain and `100 m²` water loss, equal to one 10 m Sentinel-2 pixel in each direction and therefore below a defensible engineering interpretation threshold.

## AOI

Canonical project geometry:

```text
regions/krabi/data/aoi/krabi_pdd_plots.geojson
```

Google Earth / field-review copy:

```text
regions/krabi/data/aoi/krabi_pdd_plots.kmz
```

Both contain the same four WGS84 plot polygons:

- `97-VSD` — Khlong Thom / Huai Nam Khao
- `98-VSD` — Khlong Thom / Huai Nam Khao
- `99-VSD` — Khlong Thom / Khlong Thom Tai
- `100-VSD` — Khlong Thom / Phela

The shoreline-screening workflow generates a 500 m buffer around the plot union:

```text
regions/krabi/data/aoi/krabi_shoreline_corridor_500m.geojson
```

The project polygons are monitoring boundaries, not an official coastline or administrative boundary.

## Data sources and calibration policy

### Sentinel-2 water history

The Krabi wrapper uses Earth Search:

```text
collection: sentinel-2-c1-l2a
analysis CRS: EPSG:32647
```

Collection 1 is used to avoid mixing the old and new Sentinel-2 processing baselines in one time series. Each selected scene's `raster:bands` scale/offset is read from STAC metadata and audited against the source GeoTIFF metadata captured during clipping.

### Existing vegetation products

The pilot reuses the latest PDD22 plot metrics from `saratchai1/prasae`, branch `pdd22-satellite-refetch`. A provenance-preserving coverage table is stored at:

```text
regions/krabi/data/reuse/pdd22_krabi_coverage.csv
```

It contains 48 plot-period observations from September 2023 through August 2026.

## Processing chain

The final workflow performs:

1. validate plot GeoJSON/KMZ;
2. generate the 500 m projected analysis corridor;
3. discover and rank three Sentinel-2 Collection 1 scenes per year;
4. clip AOI-only native-resolution bands to EPSG:32647 COGs;
5. validate CRS, COG structure, AOI overlap, nodata, metadata, checksums, and previews;
6. apply scene-specific radiometric calibration;
7. mask cloud, cloud shadow, cirrus, snow/ice, saturation, and nodata with SCL;
8. calculate MNDWI and classify water;
9. reject whole scenes with less than 10% valid grid coverage;
10. require at least two usable scenes per year;
11. generate annual water-frequency, consensus, and uncertainty rasters;
12. compare early and recent multi-year epochs;
13. summarize candidate change by plot;
14. cross-check MNDWI water against SCL class 6;
15. combine water and vegetation evidence into executive JSON/Markdown;
16. package a static dashboard with maps, charts, QA, previews, and downloadable outputs.

## Run the complete workflow locally

From the repository root:

```bash
python -m pip install -r requirements.txt

python scripts/build_analysis_corridor.py \
  --input regions/krabi/data/aoi/krabi_pdd_plots.geojson \
  --output regions/krabi/data/aoi/krabi_shoreline_corridor_500m.geojson \
  --buffer-m 500

python scripts/download_krabi_satellite_data.py sentinel2 \
  --aoi data/aoi/krabi_shoreline_corridor_500m.geojson \
  --start 2016-01-01 --end 2026-08-29 \
  --per-year 3 --download
```

The wrapper changes its working directory internally, so the `--aoi` value above is resolved under `regions/krabi/`.

Then process the downloaded scenes:

```bash
cd regions/krabi

python ../../scripts/validate_rasters.py \
  $(find data/satellite/sentinel2 -type f -name '*.tif' | sort) \
  --aoi data/aoi/krabi_shoreline_corridor_500m.geojson \
  --json data/manifests/sentinel2_history_raster_validation.json

python ../../scripts/process_sentinel2_water_history.py \
  --catalog data/catalog/sentinel2_scenes.csv \
  --satellite-root data/satellite/sentinel2 \
  --out-root data/analysis/water_history \
  --tide-status unverified

python ../../scripts/summarize_water_history.py \
  --root data/analysis/water_history \
  --csv analysis/water_history.csv \
  --json analysis/water_history_summary.json \
  --min-valid-fraction-grid 0.10

python ../../scripts/audit_sentinel2_water.py \
  --catalog data/catalog/sentinel2_scenes.csv \
  --satellite-root data/satellite/sentinel2 \
  --water-root data/analysis/water_history \
  --csv analysis/scl_water_audit.csv \
  --json analysis/scl_water_audit.json \
  --min-valid-fraction-grid 0.10

python ../../scripts/build_water_consensus.py \
  --root data/analysis/water_history \
  --out analysis/water_consensus \
  --plots data/aoi/krabi_pdd_plots.geojson \
  --threshold 0.5 \
  --min-valid-fraction 0.66 \
  --min-scene-valid-fraction 0.10 \
  --min-scenes-per-year 2 \
  --min-area-m2 100
```

Build the executive summary and static site:

```bash
cd ../..

python scripts/build_krabi_pilot_summary.py \
  --vegetation regions/krabi/analysis/vegetation_trends.csv \
  --events regions/krabi/analysis/events.csv \
  --water-scene-summary regions/krabi/analysis/water_history_summary.json \
  --water-consensus regions/krabi/analysis/water_consensus/summary.json \
  --scl-audit regions/krabi/analysis/scl_water_audit.json \
  --out-json regions/krabi/analysis/pilot_summary.json \
  --out-md regions/krabi/analysis/pilot_summary.md

python scripts/prepare_krabi_site.py \
  --region regions/krabi \
  --out regions/krabi/site

python -m http.server 8000 --directory regions/krabi/site
```

Open `http://localhost:8000`.

## Automated run

GitHub Actions workflow:

```text
.github/workflows/krabi-history-screening.yml
```

The workflow uploads `krabi-final-pilot-package-2018-2026`, containing:

- packaged static dashboard;
- executive JSON and Markdown;
- vegetation trend/event tables;
- scene-level water history;
- annual/epoch consensus COGs and GeoJSON;
- per-plot change tables;
- SCL consistency audit;
- calibration audit;
- raster validation report;
- scene catalog and analysis corridor.

## Required next field controls

To promote this screening result to engineering shoreline analysis:

1. obtain or predict water level at each acquisition time from the Pak Nam Krabi tide station or an approved local datum;
2. retain only tide-matched acquisitions or normalize shoreline position to a reference water level;
3. survey stable shoreline/elevation control points with RTK GNSS;
4. quantify positional uncertainty from pixel resolution, classification, georegistration, tide, and shoreline definition;
5. calculate shoreline displacement along transects rather than interpreting gross polygon area alone;
6. verify the `97-VSD` vegetation event in the field.

Until these controls are complete, all water-change products must retain the status:

```text
MULTI_SCENE_TIDE_UNVERIFIED_SCREENING
```
