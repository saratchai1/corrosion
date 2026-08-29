# Samut Songkhram Coastal Change

Reproducible geospatial workflow and static WebApp for exploring apparent coastal change in Samut Songkhram, Thailand. The province-wide MVP covers eight target epochs from 1985–2026 using Landsat and Sentinel-2 imagery. A project-focused assessment additionally covers the nine verified planting plots `91–98-STC` and `87-VSD` before, during, and after the reported 2024 planting year.

The displayed line is an **image-derived water-land boundary**, not a surveyed or tide-normalized shoreline. Every current epoch has `tide_status=unverified`; rates and classes therefore have `LOW` confidence and must not be described as definitive erosion rates.

## MVP outputs

- Quality-masked median surface-reflectance composites in EPSG:32647 COG format (local only)
- MNDWI water-land boundary for eight epochs
- Coastal vegetation spectral proxy and area statistics
- 100 m transects, yearly positions, endpoint and regression rates, and resolution-aware classes
- React + TypeScript + Vite + MapLibre static WebApp with timeline, synchronized comparison, layer controls, transect graph, and responsive layout
- Verified 9-plot overlay and January–April Sentinel-2 indicators for 2023–2026, including local observational controls

## 2024 planting assessment

The project-focused result is **not demonstrated** for reduced coastal erosion, with `LOW` confidence. Plot greenness increased from mean NDVI **0.403** in 2023 to **0.472** in 2026, but nearby matched context increased by almost the same amount; the 2026 NDVI difference-in-differences is only **+0.005**. For the 43 existing province-wide transects crossing `91–98-STC`, 34 stayed within ±20 m in 2025–2026, 5 moved inland by more than 20 m, and 4 moved seaward by more than 20 m. This suggests mostly stable recent image-derived water–land positions, but does not establish that planting caused the stability. `87-VSD` has plot spectral metrics but lies outside the existing province-wide transect coverage.

See [project impact methodology and results](docs/PROJECT_IMPACT_ANALYSIS.md).

The active implementation branch is `feature/coastal-change-webapp`, based on `data/samut-songkhram-satellite-v1`.

## Reproduce the MVP

### 1. Environment and data selection

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_mvp_epochs.py
```

The bounded download selects 2–3 full-AOI optical acquisitions per epoch and stores AOI-only source COGs under `data/satellite/`. The tested local working set is about 355 MB, below the 15 GB ceiling. Source and processed TIFFs remain local because Git LFS quota is not verified.

For the nine planting plots, build/refresh the verified AOI, download the 2023–2026 same-season subset, and calculate indicators with:

```bash
python scripts/build_samut_songkhram_project_aoi.py
python scripts/download_project_impact_epochs.py
python scripts/build_project_impact_analysis.py
```

The additional source COGs use about 62 MB and remain local under `data/satellite/project_samut_songkhram/`.

### 2. Build composites, boundaries, vegetation, transects, statistics, and web assets

```bash
python scripts/build_coastal_change_mvp.py
```

This one reproducible command performs steps 2–5 of the analytical workflow:

1. builds per-epoch optical median composites using Landsat `QA_PIXEL` or Sentinel-2 `SCL` masks;
2. compares Otsu, fixed-zero, and percentile MNDWI thresholds, applies conservative cleanup, and extracts a continuous water-land trace;
3. calculates a coastal NDVI vegetation proxy;
4. creates perpendicular transects and change statistics; and
5. prepares WebP/GeoJSON/CSV/JSON assets under `data/processed/web/` and `web/public/data/`.

### 3. Run and build the WebApp

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173`. Create the production bundle with:

```bash
npm run build
```

The deployable static bundle is written to `web/dist/`.

## Data and documentation

- [MVP methodology and results](docs/COASTAL_CHANGE_MVP.md)
- [Download and full data workflow](docs/DOWNLOAD_AND_REPRODUCE.md)
- [Scientific and operational limitations](docs/DATA_LIMITATIONS.md)
- [Data sources](docs/DATA_SOURCES.md)

The province-wide AOI in `data/aoi/samut_songkhram_aoi.geojson` remains provisional. The nine project polygons in `data/aoi/samut_songkhram_project_plots.geojson` are selected from the pinned dashboard source, while the surrounding 2.5 km analytical buffer is explicitly not an official project boundary.
